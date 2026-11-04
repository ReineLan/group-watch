"""Durable confirmed cases and bounded process-local detection state."""
from group_watch.monitoring.window import MessageWindow
from group_watch.utils.sqlite import connect
from group_watch.sources.members import SCHEMA as MEMBERS_SCHEMA
import json
import time
from pathlib import Path

MONITORED_CASE = 'NOT EXISTS (SELECT 1 FROM monitor_shared_whitelist w WHERE w.user_id=cases.user_id)'


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = connect(path, check_same_thread=False)
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS registered_groups (
          group_id INTEGER PRIMARY KEY CHECK(group_id!=0), platform TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS cases (
          id TEXT PRIMARY KEY, group_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
          rule TEXT NOT NULL, created REAL NOT NULL, evidence TEXT NOT NULL,
          context TEXT NOT NULL,
          reason TEXT DEFAULT '', confidence REAL NOT NULL CHECK(confidence>=0.8 AND confidence<=1),
          notified INTEGER DEFAULT 0, notify_attempts INTEGER DEFAULT 0,
          notify_next REAL DEFAULT 0, resolution TEXT DEFAULT '', note TEXT DEFAULT '',
          decision_at REAL);
        CREATE INDEX IF NOT EXISTS case_created ON cases(created);
        CREATE TABLE IF NOT EXISTS case_resources (
          case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          position TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
          status INTEGER NOT NULL DEFAULT 0 CHECK(status IN (0,1,2)),
          at TEXT, url TEXT, PRIMARY KEY(case_id,position));
        CREATE TABLE IF NOT EXISTS broadcast_delivery (
          case_id TEXT, kind TEXT, target TEXT, status TEXT, created REAL, error TEXT,
          PRIMARY KEY(case_id,kind,target));
        CREATE TABLE IF NOT EXISTS monitor_shared_whitelist (
          user_id INTEGER PRIMARY KEY CHECK(user_id!=0), nickname TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS moderation_feedback (
          source TEXT PRIMARY KEY, rule TEXT, verdict TEXT, summary TEXT, updated REAL,
          edited INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS feedback_jobs (
          source TEXT PRIMARY KEY, rule TEXT, verdict TEXT, payload TEXT, revision TEXT,
          updated REAL, attempts INTEGER DEFAULT 0, next_try REAL DEFAULT 0, error TEXT DEFAULT '');
        ''')
        self.window_state = MessageWindow()
        self.db.executescript(MEMBERS_SCHEMA)

    def whitelist(self):
        return [dict(row) for row in self.db.execute('SELECT user_id,nickname FROM monitor_shared_whitelist ORDER BY user_id')]

    def save_whitelist(self, members):
        with self.db:
            self.db.execute('DELETE FROM monitor_shared_whitelist')
            self.db.executemany('INSERT INTO monitor_shared_whitelist VALUES(?,?)',
                                [(int(row['user_id']),row.get('nickname','')) for row in members])

    def whitelist_nickname(self, user, nickname):
        with self.db:
            self.db.execute('UPDATE monitor_shared_whitelist SET nickname=? WHERE user_id=?',(nickname,user))

    def is_whitelisted(self, group, user):
        return bool(self.db.execute('SELECT 1 FROM monitor_shared_whitelist WHERE user_id=?',(user,)).fetchone())

    def monitored_cases(self, where='1=1', args=(), limit=100, order='created DESC', offset=0):
        return self.cases(f'({where}) AND {MONITORED_CASE}',args,limit,order,offset)


    def due(self, now, delay, limit):
        self.window_state._prune_memory(now)
        return [dict(c) for c in self.window_state.candidates.values() if c['next_try']<=now and c['created']<=now-delay
                and not self.is_whitelisted(c['group_id'],c['user_id'])][:limit]

    def cases(self, where='1=1', args=(), limit=100, order='created DESC', offset=0):
        rows=self.db.execute(f'SELECT * FROM cases WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?',(*args,limit,offset))
        output=[]
        for row in rows:
            item=dict(row)
            item['state']='violation'
            for key in ('evidence','context'):
                item[key]=json.loads(item[key])
            output.append(item)
        return output

    def update(self, case_id, **fields):
        candidate=self.window_state.candidates.get(case_id)
        if candidate is not None:
            candidate.update(fields)
            if fields.get('state') in ('clear','unsure'):
                self.window_state.candidates.pop(case_id,None)
            elif fields.get('state')=='violation':
                own={m['message_id'] for m in candidate['context'] if m['user_id']==candidate['user_id']}
                if candidate.get('confidence',0)>=.8 and candidate['evidence'] and set(candidate['evidence'])<=own:
                    columns=('id','group_id','user_id','rule','created','evidence','context','reason','confidence')
                    with self.db:
                        self.db.execute(f'INSERT OR IGNORE INTO cases({",".join(columns)}) VALUES({",".join("?" for _ in columns)})',
                            [dumps(candidate[k]) if k in ('evidence','context') else candidate[k] for k in columns])
                self.window_state.candidates.pop(case_id,None)
            return
        allowed={'reason','confidence','notified','notify_attempts','notify_next','resolution','note','decision_at'}
        if not fields or not fields.keys()<=allowed:
            raise ValueError('Invalid case update')
        with self.db:
            self.db.execute('UPDATE cases SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?',(*fields.values(),case_id))

    def counts(self):
        return {'violation':self.db.execute(f'SELECT count(*) FROM cases WHERE {MONITORED_CASE}').fetchone()[0], 'pending':sum(not self.is_whitelisted(c['group_id'],c['user_id']) for c in self.window_state.candidates.values())}


    def prune(self, days):
        self.window_state._prune_memory(time.time())
