"""Disposable read-only query process. No credentials, media files or network client."""
import json
from pathlib import Path
import sqlite3
import sys
import time


MAX_SOURCE = 50000
MAX_ROWS = 10000
MAX_BYTES = 8 * 1024 * 1024


def send(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('数据源尚未建立')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
    db.execute('PRAGMA query_only=ON')
    return db


def snapshot(watch, evidence):
    """Project explicit fields into an isolated snapshot; never copy image/credential data."""
    db = sqlite3.connect(':memory:')
    coverage = {}

    def copy(name, columns, rows, total):
        db.execute(f'CREATE TABLE {name} ({columns})')
        names = [x[1] for x in db.execute(f'PRAGMA table_info({name})')]
        count = 0
        for row in rows:
            db.execute(f'INSERT INTO {name} VALUES ({",".join("?" for _ in names)})', row)
            count += 1
        coverage[name] = {'rows': count, 'total': total, 'limited': count < total}

    with readonly(watch) as source:
        source.execute('BEGIN')
        for name, fields in (
            ('cases','id,group_id,user_id,rule,created,confidence,reason,resolution,note,decision_at'),
            ('registered_groups','group_id,platform,name'),
            ('members','group_id,user_id,nickname,card,level,join_time,last_sent_time,updated_at')):
            info = {r[1]:r[2] for r in source.execute(f'PRAGMA table_info({name})')}
            copy(name, ','.join(f'{f} {info[f]}' for f in fields.split(',')),
                 source.execute(f'SELECT {fields} FROM {name} LIMIT 50000'),source.execute(f'SELECT count(*) FROM {name}').fetchone()[0])
    with readonly(evidence) as source:
        source.execute('BEGIN')
        for name, fields in (
            ('records','id,member_id,group_id,nickname,card,event_date,reason,punishment,penalty_text,operator,notes,nickname_status,nickname_at,avatar_status,avatar_at,created_at,updated_at'),
            ('rules','id,reason,steps,notes')):
            info = {r[1]:r[2] for r in source.execute(f'PRAGMA table_info({name})')}
            copy(name, ','.join(f'{f} {info[f]}' for f in fields.split(',')),
                 source.execute(f'SELECT {fields} FROM {name} LIMIT 50000'),source.execute(f'SELECT count(*) FROM {name}').fetchone()[0])
    db.commit()
    schema = {name: [dict(name=row[1], type=row[2]) for row in db.execute(f'PRAGMA table_info({name})')] for name in coverage}
    db.execute('PRAGMA query_only=ON')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
    db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20000)
    db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 80)
    db.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20)
    return db, schema, coverage


def execute(db, sql):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    def authorize(action, first, second, database, trigger):
        if action == sqlite3.SQLITE_FUNCTION and str(second).lower() in {'load_extension', 'writefile', 'readfile'}:
            return sqlite3.SQLITE_DENY
        # SQLite reports database=None for the implicit read in COUNT(*).
        if action == sqlite3.SQLITE_READ and (database not in {'main', None} or first not in {'cases', 'records', 'rules', 'registered_groups', 'members'}):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    db.set_authorizer(authorize)
    started = time.monotonic()
    db.set_progress_handler(lambda: int(time.monotonic() - started > 6), 10000)
    cursor = db.execute(sql)
    if not cursor.description:
        raise ValueError('仅支持返回表格的只读查询')
    columns = [x[0] for x in cursor.description]
    rows, size, truncated = [], 0, False
    for row in cursor:
        values = [str(x)[:2000] if isinstance(x, (str, bytes)) else x for x in row]
        encoded = json.dumps(values, ensure_ascii=False).encode('utf-8')
        if len(rows) >= MAX_ROWS or size + len(encoded) > MAX_BYTES:
            truncated = True
            break
        rows.append(values)
        size += len(encoded)
    return dict(sql=sql, columns=columns, rows=rows, truncated=truncated, cell_limit=2000)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        # SQLite aggregate/sort allocations are bounded even before the timeout fires.
        with sqlite3.connect(':memory:') as limits:
            limits.execute('PRAGMA hard_heap_limit=100663296')
        config = json.loads(sys.stdin.readline())
        db, schema, coverage = snapshot(config['watch'], config['evidence'])
        send(dict(schema=schema, coverage=coverage, as_of=time.time()))
        for line in sys.stdin:
            try:
                sql = json.loads(line)['sql']
                result = execute(db, sql)
                send(result)
            except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                send({'error': str(exc)[:250]})
    except Exception as exc:
        send({'error': '查询快照创建失败：' + type(exc).__name__})
    finally:
        if 'db' in locals():
            db.close()


if __name__ == '__main__':
    main()
