"""Keep private authentication and archived identities durable across startup."""
from contextlib import closing
import json
import sqlite3

from dotenv import dotenv_values

from group_watch.evidence.profiles import ProfileCache
from group_watch.settings import evidence_tokens
from group_watch.settings import load_settings


def test_evidence_token_survives_restart_in_owned_environment(tmp_path):
    env = tmp_path / '.env'
    env.write_text("OTHER_SECRET='unchanged'\n", encoding='utf-8')
    first = evidence_tokens(env)
    assert first == evidence_tokens(env)
    assert len(first[0]) >= 32
    assert dotenv_values(env, interpolate=False)['OTHER_SECRET'] == 'unchanged'
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'local_env': str(env)}), encoding='utf-8')
    assert [token.get_secret_value() for token in load_settings(config).evidence_tokens] == first
    assert list(tmp_path.glob('*.txt')) == []


def test_profiles_read_merged_columns_without_retiring_legacy_files(tmp_path,monkeypatch):
    from group_watch.evidence.store import RecordStore
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    legacy=tmp_path/'record-profiles.json';legacy.write_text('{}',encoding='utf-8')
    store=RecordStore(tmp_path);store.initialize(tmp_path)
    key=store.save_records(dict(member_id='123456',group_id=100000001,nickname='  ',card='',event_date='2026-10-29',reason='证据',punishment='警告'))['id']
    assert store.get_profiles().snapshot()[key]['nickname']=='  '
    store.close();store.initialize(tmp_path)
    assert store.get_profiles().snapshot()[key]['nickname']=='  ' and legacy.read_text(encoding='utf-8')=='{}'
    with closing(sqlite3.connect(store.db_path)) as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'records','rules','audit','sqlite_sequence'}
    store.close()
