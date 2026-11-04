import asyncio
import importlib.util
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

import pytest

from group_watch.evidence.store import RecordStore
from group_watch import maintenance
import group_watch.query.worker as query_worker
from group_watch.query.service import QueryError
from group_watch.query.service import QueryService
from group_watch.settings import Settings
from group_watch.monitoring.store import Store


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES', '0')
    cfg = Settings(db_path=str(tmp_path/'watch.sqlite3'), local_env=str(tmp_path/'.env'), query_calls_hour=2)
    store = Store(cfg.db_path)
    event = dict(group_id=100000001, message_id='1', user_id=123456, time=time.time(), text='已保存文本', name='测试', media=['image'])
    store.window_state.insert_message(event, time.time())
    evidence = RecordStore(tmp_path/'evidence')
    evidence.initialize(evidence.data)
    evidence.save_records(dict(nickname='测试', member_id='123456', group_id=100000001, event_date='2026-10-27', reason='人工记录', punishment='警告', operator='测试', images=[]))
    # Keep repository database and SQLite URI guards intact; substitute only the
    # read-only source factory with temp-file connections in this unit process.
    def temp_source(path):
        path = Path(path).resolve()
        assert path.is_relative_to(tmp_path.resolve())
        db = sqlite3.connect(path)
        db.execute('PRAGMA query_only=ON')
        return db
    monkeypatch.setattr(query_worker, 'readonly', temp_source)
    yield cfg, store, evidence
    evidence.get_profiles().close()
    evidence.profiles = None
    store.db.close()


def test_snapshot_denies_writes_and_private_fields(sources):
    cfg, store, evidence = sources
    db, schema, coverage = query_worker.snapshot(cfg.db_path, evidence.data/'evidence.sqlite3')
    try:
        assert set(schema) == {'cases','registered_groups','records','rules','members'}
        assert coverage['records']['rows'] == 1
        assert not {'images', 'payload', 'media'} & {x['name'] for values in schema.values() for x in values}
        assert query_worker.execute(db, 'SELECT count(*) FROM records')['rows'] == [[1]]
        for sql in ["DELETE FROM records", "ATTACH DATABASE ':memory:' AS other", "PRAGMA writable_schema=ON", "SELECT name FROM sqlite_master", "SELECT load_extension('x')", "SELECT 1; SELECT 2"]:
            with pytest.raises((sqlite3.Error, ValueError)):
                query_worker.execute(db, sql)
        assert len(evidence.get_records()) == 1
    finally:
        db.close()


def test_member_snapshot_query_keeps_record_nickname_independent(sources):
    from group_watch.sources.members import Members
    cfg, store, evidence = sources
    Members(cfg.db_path).save(100000001, [dict(user_id=123456,nickname='新昵称',card='新名片',level='0',join_time=100,last_sent_time=200)])
    db, _, coverage = query_worker.snapshot(cfg.db_path, evidence.db_path)
    try:
        result = query_worker.execute(db, '''SELECT m.nickname,m.card,r.nickname FROM members m
            JOIN records r ON m.group_id=r.group_id AND m.user_id=CAST(r.member_id AS INTEGER)''')
        assert result['rows'] == [['新昵称','新名片','测试']]
        assert coverage['members']['rows'] == 1
    finally:
        db.close()


def test_query_process_and_no_usage_table(sources):
    cfg,store,evidence=sources;service=QueryService(cfg,evidence.db_path)
    result=asyncio.run(service.run('SELECT count(*) AS n FROM records'))
    assert result['tables'][0]['rows']==[[1]] and service.active==0
    assert 'query_usage' not in {r[0] for r in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert asyncio.run(service.run('WITH count AS (SELECT count(*) n FROM records) SELECT * FROM count'))['tables'][0]['rows']==[[1]]


def test_query_snapshot_preserves_null_empty_and_whitespace_names(sources):
    cfg,store,evidence=sources
    for name in (None,'','   ','留档昵称'):
        with evidence.connect() as source:source.execute('UPDATE records SET nickname=?',(name,))
        db,_,_=query_worker.snapshot(cfg.db_path,evidence.db_path)
        try:assert query_worker.execute(db,'SELECT nickname FROM records')['rows']==[[name]]
        finally:db.close()


def test_query_presents_only_final_joined_table(sources, monkeypatch):
    import httpx
    from pydantic import SecretStr
    cfg, store, evidence = sources
    cfg.ds_key = SecretStr('test-only');cfg.query_calls_hour = 10
    service = QueryService(cfg, evidence.data/'evidence.sqlite3')
    actual_client = httpx.AsyncClient
    sqls = ['SELECT count(*) FROM records', 'SELECT nickname,member_id FROM records ORDER BY member_id']
    requests = []
    def response(request):
        requests.append(json.loads(request.content))
        final = len(requests) == 2
        args = {'sql':sqls[int(final)]}
        if final:
            args['summary'] = '测试（123456）有一条人工记录。'
        return httpx.Response(200, json={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':str(len(requests)), 'type':'function','function':{'name':'present_result' if final else 'query_sql','arguments':json.dumps(args)}}]}}]})
    monkeypatch.setattr('group_watch.query.service.httpx.AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(response), **kwargs))
    result = asyncio.run(service.run('哪些成员有人工记录？'))
    assert len(result['tables']) == 1
    assert result['tables'][0]['sql'] == sqls[1]
    assert result['tables'][0]['rows'] == [['测试','123456']]
    assert '123456' in result['answer'] and len(requests) == 2
    logs=sorted((Path(cfg.db_path).parent/'logs'/'ds-requests').rglob('*.json'))
    assert len(logs)==2
    assert [json.loads(p.read_text(encoding='utf-8'))['input'] for p in logs]==requests


def test_query_snapshot_reads_merged_records_in_one_query(sources, monkeypatch):
    cfg,store,evidence=sources
    with evidence.connect() as source:
        columns=[r[1] for r in source.execute('PRAGMA table_info(records)')];original=dict(source.execute('SELECT * FROM records').fetchone())
        for index in range(30):
            row=original|dict(id='bulk-'+str(index),member_id=str(200000+index),nickname='成员'+str(index))
            source.execute('INSERT INTO records VALUES ('+','.join('?' for _ in columns)+')',[row[key] for key in columns])
    statements=[];original_open=query_worker.readonly
    def traced(path):
        db=original_open(path);db.set_trace_callback(statements.append);return db
    monkeypatch.setattr(query_worker,'readonly',traced)
    db,_,coverage=query_worker.snapshot(cfg.db_path,evidence.db_path)
    try:
        assert coverage['records']['rows']==31
        assert query_worker.execute(db,"SELECT nickname FROM records WHERE id='bulk-29'")['rows']==[['成员29']]
        assert len([s for s in statements if s.startswith('SELECT id,') and 'FROM records' in s])==1
    finally:db.close()


def test_record_edit_uses_stable_id_without_obsolete_source(sources):
    cfg,store,evidence=sources;row=evidence.get_records()[0]
    evidence.save_records(row|{'reason':'编辑事实'})
    assert len(evidence.get_records())==1 and evidence.get_records()[0]['reason']=='编辑事实'
    assert 'source' not in evidence.get_records()[0]


def test_backup_restore_rotation_and_failure(sources, tmp_path, monkeypatch):
    cfg, store, evidence = sources
    task = maintenance.Maintenance(cfg, evidence)
    evidence_backups = evidence.data/'backups'
    evidence_backups.mkdir(exist_ok=True)
    for day in range(20, 28):
        (evidence_backups/f'202610{day}-120000-before-edit-12345678.tar.zst').write_bytes(b'existing')
    original_evidence = {p.name for p in evidence_backups.iterdir()}
    for _ in range(8):
        task.backup()
    assert {p.name for p in evidence_backups.iterdir()} == original_evidence
    archives = list(task.folder.glob('auto-*.tar.zst'))
    assert len(archives) == 5
    assert archives[0].read_bytes()[:4] == b'\x28\xb5\x2f\xfd'
    manual = task.folder/'manual-keep.txt'
    manual.write_text('preserve', encoding='utf-8')
    path = Path(__file__).resolve().parents[1]/'tools/restore-group-workbench.py'
    spec = importlib.util.spec_from_file_location('restore_workbench_test', path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    destination = tmp_path/'restored'
    tool.restore(archives[-1], destination)
    assert not (destination/'group-watch.sqlite3').exists()
    with sqlite3.connect(destination/'group-evidence/evidence.sqlite3') as restored:
        assert restored.execute('SELECT count(*) FROM records').fetchone()[0] == 1
    with pytest.raises(ValueError, match='已存在'):
        tool.restore(archives[-1], destination)
    before = {p.name for p in task.folder.iterdir()}
    monkeypatch.setattr(maintenance, 'verify_backup', lambda _: (_ for _ in ()).throw(ValueError('verification failed')))
    with pytest.raises(ValueError):
        task.backup()
    assert {p.name for p in task.folder.iterdir()} == before
    assert manual.read_text('utf-8') == 'preserve'


def test_supervisor_update_protocol_is_ascii(tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1]/'tools/group-watch-update.py'
    spec = importlib.util.spec_from_file_location('update_workbench_test', path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    monkeypatch.setattr(tool, 'STATE', tmp_path/'update.json')
    tool.write('准备更新', before='a', target='b')
    output = capsys.readouterr().out
    assert output.isascii()
    assert json.loads(output)['ready'] is True
    assert json.loads(tool.STATE.read_text('utf-8'))['status'] == '准备更新'
    tool.write('跳过：有未提交修改')
    assert json.loads(capsys.readouterr().out)['ready'] is False


def test_evidence_rotation_keeps_today_and_five_older(tmp_path, monkeypatch):
    from datetime import datetime
    from group_watch.evidence import archives
    monkeypatch.setattr(archives, 'now', lambda: datetime(2026, 11, 2, 12))
    folder = tmp_path/'backups'
    folder.mkdir()
    for day in range(20, 29):
        (folder/f'202610{day}-120000-before-edit-12345678.tar.zst').write_bytes(b'archive')
    today = folder/'20261102-090000-before-edit-12345678.tar.zst'
    today.write_bytes(b'today')
    legacy = folder/'before-profile-backfill-20261020-173444.sqlite3'
    legacy.write_bytes(b'legacy')
    unknown = folder/'manual.zip'
    unknown.write_bytes(b'unknown')
    assert len(archives.rotate_backups(tmp_path)) == 4
    assert sorted(p.name[6:8] for p in folder.glob('202610*')) == ['24','25','26','27','28']
    assert today.read_bytes() == b'today'
    assert legacy.read_bytes() == b'legacy'
    assert unknown.read_bytes() == b'unknown'


def test_rollback_compensates_failure_with_safety_backup(sources, monkeypatch):
    cfg,watch,evidence=sources;snapshot=evidence.backup();original=evidence.get_records()[0]
    evidence.save_records(original|{'reason':'修改后'})
    result=evidence.rollback(snapshot.name)
    assert result['ok'] and evidence.backup_path(result['backup']).is_file()
    assert evidence.get_records()==[original] and len(watch.window_state.messages)==1
    assert len(list((evidence.data/'backups').glob('*.tar.zst')))==4
    before=evidence.get_records()
    monkeypatch.setattr(evidence,'audit',lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('模拟提交失败')))
    with pytest.raises(RuntimeError,match='模拟提交失败'):evidence.rollback(snapshot.name)
    assert evidence.get_records()==before
    for name in ('../evidence.sqlite3',snapshot.name+'/x'):
        with pytest.raises(ValueError):evidence.rollback(name)


def test_fresh_full_backup_has_raw_inner_tar_and_counts_operation_backups(sources):
    from io import BytesIO
    import tarfile
    from group_watch.evidence.archive_container import Archive
    cfg, watch, evidence = sources
    manager = maintenance.Maintenance(cfg, evidence)
    operation = evidence.backup()
    first = manager.backup()
    next(iter(watch.window_state.messages.values()))[1]['text']='新修改'
    latest = manager.backup()
    assert first != latest
    with Archive(latest) as archive:
        assert set(archive.namelist()) == {'evidence.tar', 'manifest.json'}
        with tarfile.open(fileobj=BytesIO(archive.read('evidence.tar')), mode='r:') as inner:
            assert 'evidence.sqlite3' in inner.getnames()
        assert 'watch.sqlite3' not in archive.namelist()
    status = manager.status(SimpleNamespace(active=0, last_error=''))
    assert status['operation_backup_bytes'] == sum(p.stat().st_size for p in (evidence.data/'backups').glob('*.tar.zst'))
    assert status['backup_bytes'] == first.stat().st_size + latest.stat().st_size + status['operation_backup_bytes']
    assert not list((evidence.data/'backups').glob('*workbench-auto*'))


def test_only_canonical_review_budget_is_accepted():
    from group_watch.settings import RuleSettings
    from pydantic import ValidationError
    assert Settings(query_calls_hour=2).query_calls_hour == 2
    assert RuleSettings(query_calls_hour=3).query_calls_hour == 3
    for model in (Settings, RuleSettings):
        with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
            model(max_ds_calls_hour=7)
