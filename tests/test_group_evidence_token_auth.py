"""Shared workspace authentication on the native ASGI application."""
import re
import time
import pytest
from fastapi.testclient import TestClient
from group_watch.app import create_app
from group_watch.settings import Settings
from group_watch.monitoring.service import Monitor
from group_watch.paths import ROOT

TOKEN='fixture-token-'+'x'*32

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    cfg=Settings(db_path=str(tmp_path/'watch.sqlite3'),local_env=str(tmp_path/'.env'),evidence_tokens=[TOKEN])
    monitor=Monitor(cfg)
    async def start(): pass
    async def stop():
        if monitor.client: await monitor.client.aclose()
        monitor.store.db.close()
    monitor.start,monitor.stop=start,stop
    with TestClient(create_app(cfg,monitor),base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as client:
        yield client


def test_private_resources_require_shared_session(client):
    for path in ['api/records','api/backup','uploads/example.png','avatars/example.png','styles.css']:
        assert client.get('/evidence/'+path).status_code==401
    assert client.post('/evidence/api/records',json={}).status_code==401
    page=client.get('/')
    assert 'set-cookie' not in page.headers
    assert client.get('/api/auth/session').json()=={'authenticated':False}
    for path in ['/api/status','/api/cases','/api/settings/rules','/api/maintenance','/evidence/api/records']:
        assert client.get(path).status_code==401
    response=client.post('/api/auth/login',json={'token':TOKEN})
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Path=/;' in response.headers['set-cookie']
    assert client.get('/evidence/api/records').json()==[]
    assert 'group_session' not in client.cookies
    status = client.get('/api/status')
    assert status.status_code == 200
    assert 'project_root' not in status.json()
    assert 'open' not in status.json()['counts']


def test_legacy_supervisor_status_requires_direct_local_connection(client):
    client.app.state.legacy_supervisor = True
    assert client.get('/api/status').json() == {'project_root': str(ROOT)}
    proxy_headers = {'X-Forwarded-For': '203.0.113.1'}
    assert client.get('/api/status', headers=proxy_headers).status_code == 401
    assert client.get('/api/maintenance/update-token', headers=proxy_headers).status_code == 403


def test_login_logout_bearer_and_csrf(client):
    assert client.post('/api/auth/login',json={'token':'invalid'}).status_code==401
    response=client.post('/api/auth/login',json={'token':TOKEN})
    assert response.status_code==200 and 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/evidence/api/records').json()==[]
    assert client.post('/evidence/api/records',json={}).status_code==403
    page=client.get('/')
    csrf=re.search(r'name="csrf-token" content="([^"]+)',page.text)[1]
    assert client.post('/api/auth/logout',json={},headers={'x-csrf-token':csrf}).status_code==200
    assert client.get('/evidence/api/records').status_code==401
    assert client.get('/evidence/api/records',headers={'Authorization':'Bearer '+TOKEN}).status_code==200


def test_origin_content_type_and_rate_limit(client):
    assert client.post('/api/auth/login',json={},headers={'Origin':'http://evil.test'}).status_code==403
    assert client.post('/api/auth/login',content='invalid',headers={'Content-Type':'text/plain'}).status_code==400
    for _ in range(9): client.post('/api/auth/login',json={'token':'bad'})
    assert client.post('/api/auth/login',json={'token':TOKEN}).status_code==429
    assert client.get('/',headers={'Host':'evil.test'}).status_code==403


def test_shutdown_rejects_busy_work_and_accepts_drained_instance(client):
    page=client.get('/')
    csrf=re.search(r'name="csrf-token" content="([^"]+)',page.text)[1]
    client.headers['x-csrf-token']=csrf
    client.app.state.shutdown=lambda:None
    maintenance=client.app.state.maintenance
    maintenance.busy=True
    assert client.post('/api/maintenance/shutdown').status_code==409
    maintenance.busy=False
    maintenance.draining=True
    assert client.post('/api/maintenance/shutdown').status_code==200


def test_update_waits_for_pending_review_and_allows_retry(client):
    app = client.app
    app.state.supervisor_instance = 'fixture-instance'
    app.state.shutdown = lambda: None
    control = client.get('/api/maintenance/update-token').json()
    assert control['instance'] == 'fixture-instance'
    client.headers['x-csrf-token'] = control['token']
    maintenance = app.state.maintenance
    maintenance.last_activity = time.time() - 121
    candidates = app.state.monitor.store.window_state.candidates
    candidate = {'id': 'test', 'group_id': 123456, 'user_id': 7654321}

    candidates['test'] = candidate
    assert client.post('/api/maintenance/drain').status_code == 409
    assert not maintenance.draining

    candidates.clear()
    assert client.post('/api/maintenance/drain').status_code == 200
    candidates['test'] = candidate
    assert client.post('/api/maintenance/restart').status_code == 409
    assert not maintenance.draining

    candidates.clear()
    assert client.post('/api/maintenance/drain').status_code == 200
    assert client.post('/api/maintenance/restart').status_code == 200


def test_chinese_password_and_expired_session(client):
    password='群管理工作台中文密码'
    client.app.state.auth.configure_tokens([password])
    assert client.post('/api/auth/login',json={'token':password}).status_code==200
    assert client.get('/api/auth/session').json()=={'authenticated':True}
    client.app.state.auth.sessions.clear()
    assert client.get('/api/cases').status_code==401
    assert client.get('/api/auth/session').json()=={'authenticated':False}


def test_fingerprinted_assets_compress_and_cache_without_caching_private_data(client):
    from group_watch.resources import frontend_dist
    asset = next((frontend_dist()/'assets').glob('*.js'))
    path = '/ui/assets/'+asset.name
    compressed = client.get(path, headers={'Accept-Encoding':'gzip'})
    plain = client.get(path, headers={'Accept-Encoding':'identity'})
    assert compressed.content == plain.content == asset.read_bytes()
    assert compressed.headers['content-encoding'] == 'gzip'
    assert 0 < compressed.num_bytes_downloaded < len(plain.content)
    assert compressed.headers['cache-control'] == 'public, max-age=31536000, immutable'
    conditional = client.get(path, headers={'If-None-Match':compressed.headers['etag']})
    assert conditional.status_code == 304
    assert 'immutable' in conditional.headers['cache-control']
    assert client.get('/ui/assets/missing-12345678.js').headers['cache-control'] == 'no-store'
    client.headers['Authorization'] = 'Bearer '+TOKEN
    status = client.get('/api/status')
    assert status.headers['cache-control'] == 'no-store'
    assert status.headers['content-encoding'] == 'gzip'
    assert client.get('/').headers['cache-control'] == 'no-store'
    assert client.get('/api/auth/session').headers['cache-control'] == 'no-store'
    assert client.get('/evidence/avatars/123456789.png').headers['cache-control'] == 'no-store'


def test_rejected_auth_and_origin_responses_are_never_cached(client):
    for response in [client.get('/api/cases'), client.get('/evidence/api/records'),
                     client.get('/api/status', headers={'Origin':'http://evil.test'}),
                     client.post('/api/auth/login', json={'token':'invalid'})]:
        assert response.status_code in (401, 403)
        assert response.headers['cache-control'] == 'no-store'
