"""Repeatable offline benchmark. Reads production only to create SQLite snapshots.

Run with the project's Python: tools/benchmark-workbench.py --prepare --label before
Then rerun --label after against the SAME seeds. All writes stay in tmp/performance-*.
No QQ/DS/notifications are connected. Results contain timings/counts, not messages.
"""
import argparse
import asyncio
from contextlib import closing
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import statistics
import threading
import time

import httpx
import psutil

from group_watch.app import create_app
from group_watch.maintenance import Maintenance
from group_watch.maintenance import verify_backup
from group_watch.paths import ROOT
from group_watch.paths import resolve_path
from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings


def snapshot(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as db, closing(sqlite3.connect(target)) as out:
        db.backup(out)


def prepare(folder):
    seed = folder / 'seed'
    if seed.exists():
        raise ValueError('Frozen seed already exists; reuse it without --prepare')
    cfg = json.loads((ROOT/'config/config.json').read_text('utf-8-sig'))
    watch = resolve_path(cfg.get('db_path', 'data/group-watch.sqlite3'), base=ROOT)
    evidence = resolve_path(cfg.get('evidence_data') or str(watch.parent/'group-evidence'), base=ROOT)
    snapshot(watch, seed/'watch.sqlite3')
    snapshot(evidence/'evidence.sqlite3', seed/'evidence/evidence.sqlite3')
    for name in ('uploads', 'avatars'):
        if (evidence/name).exists():
            shutil.copytree(evidence/name, seed/'evidence'/name)
    print('Frozen snapshots and evidence files copied', flush=True)


def duplicate(db, table, identity, multiplier):
    columns = [r[1] for r in db.execute(f'PRAGMA table_info({table})')]
    rows = db.execute(f'SELECT * FROM {table}').fetchall()
    at = columns.index(identity)
    for copy in range(1, multiplier):
        output = []
        for original in rows:
            row = list(original)
            row[at] = f'bench-{copy}-{row[at]}'
            output.append(row)
        db.executemany(f'INSERT INTO {table} VALUES('+','.join('?' for _ in columns)+')', output)


def stats(values):
    ordered = sorted(values)
    return {'p50_ms': round(statistics.median(values), 3), 'p95_ms': round(ordered[math.ceil(len(ordered)*.95)-1], 3),
            'max_ms': round(max(values), 3), 'samples': len(values)}


async def measure(client, path, rounds=20):
    values = []
    for _ in range(rounds+1):
        start = time.perf_counter()
        response = await client.get(path)
        response.raise_for_status()
        values.append((time.perf_counter()-start)*1000)
    return {**stats(values[1:]), 'first_ms': round(values[0], 3), 'decoded_bytes': len(response.content),
            'wire_bytes': response.num_bytes_downloaded,
            'cache_control': response.headers.get('cache-control'), 'encoding': response.headers.get('content-encoding')}


def file_hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


async def run_scale(folder, label, multiplier):
    work = folder/f'{label}-{multiplier}x'
    if work.exists():
        raise ValueError(f'Result directory already exists: {work.name}')
    work.mkdir()
    shutil.copytree(folder/'seed/evidence', work/'evidence')
    snapshot(folder/'seed/watch.sqlite3', work/'watch.sqlite3')
    with closing(sqlite3.connect(work/'watch.sqlite3')) as db, db:
        duplicate(db, 'cases', 'id', multiplier)
    with closing(sqlite3.connect(work/'evidence/evidence.sqlite3')) as db, db:
        duplicate(db, 'records', 'id', multiplier)
    cfg = Settings(db_path=str(work/'watch.sqlite3'), evidence_data=str(work/'evidence'),
                   local_env=str(work/'.env'), settings_file=str(work/'settings.json'),
                   evidence_tokens=['offline-benchmark-only'], automatic_updates=False)
    monitor = Monitor(cfg)
    app = create_app(cfg, monitor)
    evidence = app.state.evidence
    evidence.init_db()
    result = {'multiplier': multiplier, 'messages': len(monitor.store.window_state.messages),
              'cases': monitor.store.db.execute('SELECT count(*) FROM cases').fetchone()[0],
              'records': len(evidence.get_records()), 'endpoints': {}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1',
                                 headers={'Authorization': 'Bearer offline-benchmark-only'}) as client:
        for path in ['/api/status', '/api/cases?state=attention&resolution=open', '/api/cases?search=bench-missing',
                     '/evidence/api/records', '/evidence/api/overview', '/api/maintenance']:
            result['endpoints'][path] = await measure(client, path)
        result['activity_storage'] = 'bounded process memory'
        asset = next((ROOT/'frontend/dist/assets').glob('*.js'))
        result['static_js'] = await measure(client, '/ui/assets/'+asset.name, rounds=8)
        tag = (await client.get('/ui/assets/'+asset.name)).headers.get('etag')
        conditional = await client.get('/ui/assets/'+asset.name, headers={'If-None-Match': tag or ''})
        result['conditional_js_status'] = conditional.status_code
        # Fixed identities; timestamps use the current clock for the 24h queries.
        stamp = time.time()
        group = cfg.groups[0]
        async def ingest():
            latency = []
            for index in range(300):
                started = time.perf_counter()
                monitor.ingest(dict(post_type='message', message_type='group', group_id=group,
                                    user_id=800000000+index, time=stamp, message_id=f'load-{index}',
                                    message=[{'type':'text','data':{'text':'隔离性能测试消息'}}]), now=stamp)
                latency.append((time.perf_counter()-started)*1000)
                await asyncio.sleep(0)
            return stats(latency)
        async def reads():
            output = []
            for _ in range(40):
                start = time.perf_counter()
                (await client.get('/api/status')).raise_for_status()
                output.append((time.perf_counter()-start)*1000)
            return stats(output)
        result['ingest'], result['concurrent_status'] = await asyncio.gather(ingest(), reads())
        if multiplier == 10:
            # Boundary violations and a read burst only touch this isolated copy.
            rows_before = len(monitor.store.window_state.messages)
            started = time.perf_counter()
            for _ in range(100):
                for event in ({}, {'post_type':'message', 'message_type':'group', 'group_id':'bad'},
                              dict(post_type='message', message_type='group', group_id=group,
                                   user_id=800000000, time=stamp-3600, message_id='stale')):
                    assert monitor.ingest(event, now=stamp) == 0
            assert len(monitor.store.window_state.messages) == rows_before
            result['abnormal'] = {'rejected_events':300, 'reject_ms':round((time.perf_counter()-started)*1000, 3)}
            for path in ['/api/cases?limit=51', '/api/cases?offset=1000001', '/api/cases?search='+('x'*201)]:
                response = await client.get(path)
                assert response.status_code == 400
                assert response.headers['cache-control'] == 'no-store'
            result['abnormal']['invalid_filters_rejected'] = 3
            result['abnormal']['max_search'] = await measure(client, '/api/cases?search='+('x'*200), rounds=8)
            async def burst_read(index):
                started = time.perf_counter()
                path = ['/api/status', '/evidence/api/overview', '/api/cases?state=attention'][index%3]
                (await client.get(path)).raise_for_status()
                return (time.perf_counter()-started)*1000
            result['abnormal']['burst_30'] = stats(await asyncio.gather(*(burst_read(i) for i in range(30))))
    if multiplier == 10:
        start = time.perf_counter()
        maintenance = Maintenance(cfg, evidence)
        maintenance.backup()
        result['backup_ms'] = round((time.perf_counter()-start)*1000, 3)
        archive = maintenance.folder/maintenance.state['backup']
        verify_backup(archive)
        result['backup_bytes'] = archive.stat().st_size
        spec = importlib.util.spec_from_file_location('bench_restore', ROOT/'tools/restore-group-workbench.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        restored = work/'restored'
        start = time.perf_counter()
        module.restore(archive, restored)
        result['restore_ms'] = round((time.perf_counter()-start)*1000, 3)
        with closing(sqlite3.connect(restored/'group-watch.sqlite3')) as restored_db:
            assert restored_db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            for table in ('cases',):
                assert restored_db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == monitor.store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        with closing(sqlite3.connect(restored/'group-evidence/evidence.sqlite3')) as restored_db:
            assert restored_db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            assert restored_db.execute('SELECT count(*) FROM records').fetchone()[0] == result['records']
        for name in ('uploads', 'avatars'):
            assert file_hashes(restored/'group-evidence'/name) == file_hashes(work/'evidence'/name)
        result['restore_integrity'] = 'Both SQLite quick_check, row counts, uploads and avatars SHA256 passed'
    result['watch_bytes'] = sum(p.stat().st_size for p in work.glob('watch.sqlite3*'))
    result['pending'] = monitor.store.counts()
    evidence.close()
    monitor.store.db.close()
    print(json.dumps({'label':label, 'scale':multiplier, 'status_p95_ms':result['endpoints']['/api/status']['p95_ms'],
                      'overview_p95_ms':result['endpoints']['/evidence/api/overview']['p95_ms']}, ensure_ascii=False), flush=True)
    return result


async def main(args):
    folder = args.output.resolve()
    if not folder.is_relative_to(ROOT/'tmp'):
        raise ValueError('Benchmark output must be under the project tmp directory')
    folder.mkdir(parents=True, exist_ok=True)
    if args.prepare:
        prepare(folder)
    os.environ['GROUP_EVIDENCE_PROFILES'] = '0'
    # Fail closed if future code accidentally tries an external request.
    def blocked(*_args, **_kwargs):
        raise RuntimeError('Offline benchmark forbids external network connections')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    process = psutil.Process()
    rss = []
    done = threading.Event()
    def sample():
        while not done.wait(.02):
            rss.append(process.memory_info().rss)
    worker = threading.Thread(target=sample, daemon=True)
    worker.start()
    start, cpu = time.perf_counter(), time.process_time()
    try:
        scales = [await run_scale(folder, args.label, multiplier) for multiplier in (1, 5, 10)]
    finally:
        done.set()
        worker.join()
    report = {'label':args.label, 'wall_seconds':round(time.perf_counter()-start, 3),
              'cpu_seconds':round(time.process_time()-cpu, 3), 'peak_rss_bytes':max(rss, default=0), 'scales':scales}
    (folder/(args.label+'.json')).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='scales'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'tmp/performance-20261030')
    asyncio.run(main(parser.parse_args()))
