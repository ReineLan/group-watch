"""Portable settings and an explicitly allowed reverse proxy, using only temporary data."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from group_watch import __main__ as cli
from group_watch import maintenance
from group_watch import settings
from group_watch.app import create_app
from group_watch.paths import resolve_path
from group_watch.monitoring.service import Monitor


def test_configuration_paths_survive_directory_move_and_backslashes(tmp_path, monkeypatch):
    root = tmp_path / '移动后的项目'
    root.mkdir()
    monkeypatch.setattr(settings, 'ROOT', root)
    monkeypatch.chdir(tmp_path)
    config = root / 'settings.json'
    config.write_text(json.dumps({
        'local_env': r'config\.env', 'db_path': r'data\数据库.sqlite3',
        'evidence_data': 'data/evidence',
    }), encoding='utf-8')
    cfg = settings.load_settings(config)
    assert Path(cfg.db_path) == root / 'data/数据库.sqlite3'
    assert Path(cfg.local_env) == root / 'config/.env'
    assert Path(cfg.evidence_data) == root / 'data/evidence'
    assert resolve_path(r'移动后的项目\settings.json', base=tmp_path) == config
    assert resolve_path(root / 'data', base=tmp_path) == root / 'data'


@pytest.mark.parametrize('foreign', [r'E:\old\data.sqlite3', r'\\server\share\data.sqlite3'] if os.name != 'nt' else ['/srv/old/data.sqlite3', 'E:relative.sqlite3', r'\rooted.sqlite3'])
def test_foreign_absolute_path_fails_instead_of_creating_wrong_database(tmp_path, foreign):
    with pytest.raises(ValueError, match='路径'):
        resolve_path(foreign, base=tmp_path)


def test_update_state_does_not_depend_on_database_directory(tmp_path, monkeypatch):
    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'update.json').write_text('{"status":"已是最新版本"}', encoding='utf-8')
    monkeypatch.setattr(maintenance, 'LOGS', logs)
    cfg = SimpleNamespace(db_path=str(tmp_path / 'external-storage/watch.sqlite3'), automatic_updates=True,
                          retention_days=14, query_calls_hour=10)
    status = maintenance.Maintenance(cfg, None).status(SimpleNamespace(active=False, last_error=''))
    assert status['update']['status'] == '已是最新版本'


def test_web_command_uses_external_gateway_without_supervisor(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, 'worker', lambda config, port: calls.append((config, port)))
    cli.main(['web', '--config', str(tmp_path / 'config.json'), '--port', '8067'])
    assert calls == [(tmp_path / 'config.json', 8067)]


@pytest.mark.parametrize('address', ['https://example.test/subpath', 'https://user:secret@example.test',
                                     'https://example.test?q=1', 'ftp://example.test', 'https://example.test:bad'])
def test_public_url_rejects_non_origin_configuration(address):
    with pytest.raises(ValueError):
        settings.Settings(public_url=address)


def test_public_proxy_keeps_authentication_origin_and_local_maintenance_guards(tmp_path, monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES', '0')
    cfg = settings.Settings(db_path=str(tmp_path / 'watch.sqlite3'), local_env=str(tmp_path / '.env'),
                            evidence_tokens=['cloud-fixture-password'], public_url='https://fan.example.test/')
    monitor = Monitor(cfg)
    async def start():
        pass
    async def stop():
        if monitor.client:
            await monitor.client.aclose()
        monitor.store.db.close()
    async def no_backup_loop(self):
        pass
    monitor.start, monitor.stop = start, stop
    with TestClient(create_app(cfg, monitor), base_url='https://fan.example.test') as client:
        assert client.get('/').status_code == 200
        assert client.get('/api/cases').status_code == 401
        assert client.get('/', headers={'Host': 'evil.test'}).status_code == 403
        assert client.post('/api/auth/login', json={'token': 'cloud-fixture-password'},
                           headers={'Origin': 'https://evil.test'}).status_code == 403
        for path in ['update-token', 'drain', 'restart', 'shutdown']:
            assert client.request('GET' if path == 'update-token' else 'POST', '/api/maintenance/' + path).status_code == 403
        response = client.post('/api/auth/login', json={'token': 'cloud-fixture-password'},
                               headers={'Origin': cfg.public_url})
        assert response.status_code == 200
        assert '; Secure' in response.headers['set-cookie']
        assert client.get('/api/cases').status_code == 200
        assert client.get('/api/maintenance/update-token', headers={'Host': '127.0.0.1'}).status_code == 200
