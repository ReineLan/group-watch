"""Last known QQ membership, retained after a member leaves the group."""
from group_watch.utils.sqlite import connect
from group_watch.utils.time import now


SCHEMA = '''
CREATE TABLE IF NOT EXISTS members (
  group_id INTEGER NOT NULL CHECK(group_id>0),
  user_id INTEGER NOT NULL CHECK(user_id>0),
  nickname TEXT, card TEXT, level TEXT,
  join_time INTEGER, last_sent_time INTEGER, updated_at TEXT NOT NULL,
  PRIMARY KEY(group_id,user_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS members_user ON members(user_id);
'''


class Members:
    def __init__(self, path):
        self.path = path

    def rows(self, group):
        with connect(self.path, close_on_exit=True) as db:
            return [dict(row) for row in db.execute('SELECT * FROM members WHERE group_id=?', (group,))]

    def get(self, group, user):
        with connect(self.path, close_on_exit=True) as db:
            row = db.execute('SELECT * FROM members WHERE group_id=? AND user_id=?', (group, user)).fetchone()
            return dict(row) if row else None

    def save(self, group, rows):
        """Validate the whole response before atomically upserting; never delete absentees."""
        if group <= 0 or not isinstance(rows, list):
            raise ValueError('群成员列表无效')
        stamp, values, seen = now().isoformat(), [], set()
        for row in rows:
            user = int(row['user_id'])
            if user <= 0 or int(row.get('group_id', group)) != group or user in seen:
                raise ValueError('群成员身份无效或重复')
            seen.add(user)
            strings = [row.get(k) if isinstance(row.get(k), str) else None for k in ('nickname', 'card')]
            level = str(row['level']) if row.get('level') is not None else None
            times = [int(row[k]) if row.get(k) is not None else None for k in ('join_time', 'last_sent_time')]
            values.append((group, user, *strings, level, *times, stamp))
        with connect(self.path, close_on_exit=True) as db:
            db.executemany('''INSERT INTO members VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(group_id,user_id) DO UPDATE SET
                nickname=excluded.nickname,card=excluded.card,level=excluded.level,
                join_time=excluded.join_time,last_sent_time=excluded.last_sent_time,updated_at=excluded.updated_at''', values)
