import base64
from io import BytesIO
import json
from group_watch.evidence.archive_container import Archive

from fastapi.testclient import TestClient
import pytest

from group_watch.app import create_app
from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES', '0')
    cfg = Settings(db_path=str(tmp_path / 'watch.sqlite3'), local_env=str(tmp_path / 'config/.env'))
    monitor = Monitor(cfg)

    async def start():
        pass

    async def stop():
        monitor.store.db.close()

    monkeypatch.setattr(monitor, 'start', start)
    monkeypatch.setattr(monitor, 'stop', stop)
    app = create_app(cfg, monitor)
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        app.state.evidence.tokens = [token for token in cfg.evidence_tokens] or [__import__('dotenv').dotenv_values(cfg.local_env)['GROUP_EVIDENCE_TOKENS']]
        yield client, app.state.evidence


def login(client, evidence):
    response = client.post('/evidence/auth/login', json={'token': evidence.tokens[0]})
    assert response.status_code == 200
    assert 'Path=/;' in response.headers['set-cookie']
    page = client.get('/')
    client.headers['x-csrf-token'] = __import__('re').search(r'name="csrf-token" content="([^"]+)', page.text)[1]


def test_mounted_auth_origin_and_monitor_boundaries(desk):
    client, evidence = desk
    for path in ('api/records', 'api/backup', 'styles.css', 'uploads/any.png'):
        assert client.get('/evidence/' + path).status_code == 401
    assert client.post('/evidence/auth/login', json={'token': 'bad'}).status_code == 401
    assert client.post('/evidence/auth/login', json={}, headers={'Origin': 'https://evil.test'}).status_code == 403
    login(client, evidence)
    page = client.get('/')
    assert '处罚档案' in page.text and 'evidence-gate' not in page.text
    assert '__EVIDENCE__' not in page.text
    assert 'lan_workspace' in client.cookies
    assert client.get('/evidence/', follow_redirects=False).headers['location']=='/#records'
    assert '<div id="app"></div>' in page.text
    assert '/ui/assets/' in page.text
    css = __import__('re').search(r'href="(/ui/assets/[^"]+\.css)"', page.text)
    assert css and client.get(css[1]).status_code == 200
    assert client.get('/evidence/changelog.md').status_code == 404
    assert client.get('/evidence/api/records').json() == []
    assert client.post('/api/settings/rules', json={}, headers={'x-csrf-token':''}).status_code == 403
    assert client.post('/evidence/api/rules', json={'rules': []}, headers={'Origin': 'http://evil.test'}).status_code == 403
    assert client.get('/evidence/%2e%2e/server.py').status_code == 404
    response = client.get('/evidence/')
    assert "img-src 'self' data: blob:" in response.headers['content-security-policy']
    client.headers['x-csrf-token'] = __import__('re').search(r'name="csrf-token" content="([^"]+)', page.text)[1]
    assert client.post('/evidence/auth/logout', json={}).status_code == 200
    client.cookies.clear()
    assert client.get('/evidence/api/records').status_code == 401


def test_mounted_records_images_rules_and_backup(desk):
    client, evidence = desk
    login(client, evidence)
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGZkAAAAASUVORK5CYII=')
    body = dict(group_id=100000001, event_date='2026-10-26', reason='人工核对', punishment='警告',
                operator='测试', nickname='测试成员', member_id='123456',
                images=[dict(data=base64.b64encode(png).decode(), name='证据.png')])
    saved = client.post('/evidence/api/records', json=body)
    assert saved.status_code == 200, saved.text
    records = client.get('/evidence/api/records').json()
    assert len(records) == 1 and records[0]['id'] == saved.json()['id']
    image=client.get('/evidence' + records[0]['images'][0]['url']).content
    assert image[:4]==b'RIFF' and image[8:12]==b'WEBP'
    rules = [{'reason': '测试行为', 'steps': ['警告', '禁言1天'], 'notes': '人工决定'}]
    assert client.post('/evidence/api/rules', json={'rules': rules}).status_code == 200
    assert client.get('/api/settings/rules').json()['query_calls_hour'] == 5
    archive = client.get('/evidence/api/backup')
    assert archive.status_code == 200
    target = evidence.data / 'test-download.tar.zst'
    target.write_bytes(archive.content)
    assert archive.content[:4] == bytes.fromhex('28b52ffd')
    with Archive(target) as zipped:
        assert 'evidence.sqlite3' in zipped.namelist()
        assert any(name.startswith('uploads/') for name in zipped.namelist())
    assert client.request('DELETE', '/evidence/api/records/' + saved.json()['id'], content=json.dumps({}),
                         headers={'Content-Type': 'application/json'}).status_code == 200
    assert client.get('/evidence/api/records').json() == []


def test_full_backup_download_and_rollback_require_session_and_csrf(desk, monkeypatch, tmp_path):
    import sqlite3
    from group_watch import maintenance
    client, evidence = desk
    assert client.post('/api/maintenance/backup', json={}).status_code in (401,403)
    assert client.post('/evidence/api/rollback', json={}).status_code in (401,403)
    login(client, evidence)
    csrf = client.headers.pop('x-csrf-token')
    assert client.post('/api/maintenance/backup', json={}).status_code == 403
    assert client.post('/evidence/api/rollback', json={}).status_code == 403
    client.headers['x-csrf-token'] = csrf
    snapshot = evidence.backup()
    evidence.save_records(dict(nickname='测试', member_id='888888', group_id=100000001, event_date='2026-10-28', reason='新增', punishment='警告', images=[]))
    response = client.post('/api/maintenance/backup', json={})
    assert response.status_code == 200, response.text
    package = client.get(response.json()['url'])
    assert package.status_code == 200
    target = tmp_path/'download.tar.zst'
    target.write_bytes(package.content)
    maintenance.verify_backup(target)
    restored = client.post('/evidence/api/rollback', json={'backup':snapshot.name})
    assert restored.status_code == 200, restored.text
    assert evidence.get_records() == []
    assert client.post('/evidence/api/rollback', json={'backup':'../x'}).status_code == 400
    client.cookies.clear()
    assert client.get(response.json()['url']).status_code == 401
