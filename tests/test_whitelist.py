def case_rows(store):
    return list(store.window_state.candidates.values())+store.cases()

import asyncio
import json
import time

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from group_watch.settings import PushRecipient
from group_watch.app import create_app
from group_watch.monitoring.service import Monitor
from group_watch.monitoring.store import Store
from group_watch.monitoring.whitelist import Whitelist
from test_group_watch import config, event, signed_client


def test_whitelist_is_shared_persistent_and_keeps_conversation_context(tmp_path):
    monitor = Monitor(config(tmp_path))
    group, other = monitor.cfg.groups[:2]
    user = 1234567
    monitor.store.save_whitelist([dict(user_id=user,nickname='成员甲')])
    assert monitor.ingest(event('ignored',text='123456',group=group,user=user)) == 0
    messages = monitor.store.window_state.window(group,time.time()-60,time.time()+1)
    assert [row['message_id'] for row in messages] == ['ignored']
    assert monitor.ingest(event('other',text='123456',group=other,user=user)) == 0
    monitor.store.db.close()
    store = Store(monitor.cfg.db_path)
    assert store.is_whitelisted(group,user)
    assert store.is_whitelisted(other,user)
    assert store.is_whitelisted(-group,user)
    assert not store.is_whitelisted(group,-user)
    store.save_whitelist([])
    assert not store.is_whitelisted(group,user)
    store.db.close()


def test_whitelist_api_uses_qq_nickname_validation_auth_and_shared_replacement(tmp_path):
    monitor = Monitor(config(tmp_path,ws_url='ws://example.invalid'))
    group, other = monitor.cfg.groups[:2]
    monitor.directory.members[group] = {'1234567':dict(name='群名片',card='群名片',nickname='QQ昵称')}
    monitor.store.save_whitelist([dict(user_id='7777777',nickname='另一群成员')])
    async def lookup(*args):
        await asyncio.sleep(30)
    monitor.qq.call = lookup
    app = create_app(monitor.cfg,monitor)
    anonymous = TestClient(app)
    assert anonymous.get('/api/settings/whitelist').status_code == 401
    anonymous.close()
    client = signed_client(app)
    headers = {'X-CSRF-Token':client.get('/').text.split("const token='")[1].split("'")[0]}
    url = '/api/settings/whitelist'
    body = dict(accounts=['1234567','8888888','1234567'])
    assert client.post(url,json=body).status_code == 403
    start = time.monotonic()
    saved = client.post(url,json=body,headers=headers)
    assert time.monotonic()-start < 2
    assert saved.status_code == 200
    assert saved.json()['members'] == [dict(user_id='1234567',nickname='QQ昵称'),dict(user_id='8888888',nickname='')]
    assert monitor.store.is_whitelisted(other,8888888)
    assert not monitor.store.is_whitelisted(other,7777777)
    for invalid in [dict(accounts=['１２３４５']),dict(accounts=['0012345']),dict(accounts=['0'])]:
        assert client.post(url,json=invalid,headers=headers).status_code == 400
    assert client.post(url,json=dict(accounts=['1234567']*201),headers=headers).status_code == 422
    assert len(monitor.store.whitelist()) == 2
    assert client.post(url,json=dict(accounts=[]),headers=headers).status_code == 200
    assert not monitor.store.whitelist()
    client.close();monitor.store.db.close()


def test_whitelisted_candidates_are_filtered_and_handled_cases_stay_queryable(tmp_path):
    monitor=Monitor(config(tmp_path));group=monitor.cfg.groups[0]
    for user in (1234567,7654321):
        monitor.ingest(event(str(user),text='123456',user=user))
    ignored=next(c for c in monitor.store.window_state.candidates.values() if c['user_id']==1234567)
    monitor.store.update(ignored['id'],state='violation',confidence=.95,resolution='dismissed')
    monitor.store.update(ignored['id'],resolution='dismissed')
    monitor.store.save_whitelist([dict(user_id=1234567)])
    assert [c['user_id'] for c in monitor.store.due(time.time(),0,1)]==[7654321]
    assert monitor.store.counts()=={'violation':0,'pending':1}
    client=signed_client(create_app(monitor.cfg,monitor))
    assert client.get('/api/cases').json()==[]
    assert client.get('/api/cases?resolution=handled').json()[0]['id']==ignored['id']
    client.close();monitor.store.db.close()


def test_whitelisted_candidates_never_call_review_push_or_broadcast(tmp_path):
    async def run():
        cfg = config(tmp_path,ds_key=SecretStr('fake'),pushplus_recipients=[PushRecipient(token=SecretStr('fake'))],
                     broadcast_targets=[dict(kind='group',id='100000010')])
        monitor = Monitor(cfg)
        monitor.ingest(event('pending',text='123456',user=1234567))
        monitor.ingest(event('violation',text='123456',user=7654321))
        case = next(c for c in monitor.store.window_state.candidates.values() if c['user_id']==7654321)
        monitor.store.update(case['id'],state='violation',confidence=.99)
        monitor.store.save_whitelist([dict(user_id=user) for user in (1234567,7654321)])
        def forbidden(request):
            raise AssertionError('Whitelisted members must not trigger remote actions')
        async def qq_forbidden(*args):
            raise AssertionError('Whitelisted members must not trigger QQ broadcasts')
        monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden))
        monitor.qq.call = qq_forbidden
        await monitor.review_once();await monitor.notify_once();await monitor.broadcast_once()
        assert monitor.quota.calls_hour(time.time()) == 0
        assert monitor.store.db.execute('SELECT count(*) FROM broadcast_delivery').fetchone()[0] == 0
        await monitor.stop()
    asyncio.run(run())


def test_whitelisting_during_review_prevents_late_result_application(tmp_path):
    async def run():
        monitor = Monitor(config(tmp_path,ds_key=SecretStr('fake')))
        monitor.ingest(event(text='123456',user=1234567))
        case = case_rows(monitor.store)[0]
        def handler(request):
            monitor.store.save_whitelist([dict(user_id=case['user_id'])])
            result = dict(id=case['id'],verdict='violation',confidence=.99,reason='说明',evidence_ids=['1'])
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[result]})}}]})
        monitor.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once()
        assert case_rows(monitor.store)==[]
        assert not monitor.store.due(time.time(),0,10)
        await monitor.stop()
    asyncio.run(run())


def test_signed_shared_whitelist_removals_are_durable(tmp_path):
    path=tmp_path/'watch.db';store=Store(path)
    store.save_whitelist([dict(user_id=12345,nickname='QQ'),dict(user_id=-12345,nickname='直播')])
    store.db.close();store=Store(path)
    assert {r['user_id'] for r in store.whitelist()}=={12345,-12345}
    store.save_whitelist([]);store.db.close();store=Store(path)
    assert store.whitelist()==[];store.db.close()


def test_background_lookup_failure_does_not_undo_save_and_late_names_do_not_restore_removed_members(tmp_path):
    async def run():
        monitor = Monitor(config(tmp_path,ws_url='ws://example.invalid'))
        whitelist = Whitelist(monitor)
        entered,release = asyncio.Event(),asyncio.Event()
        async def lookup(action,params):
            entered.set()
            await release.wait()
            if params['user_id'] == 1234567:
                raise TimeoutError('QQ lookup failed')
            return dict(user_id=params['user_id'],nickname='QQ昵称',card='群名片')
        monitor.qq.call = lookup
        whitelist.save(['1234567','7654321'])
        await entered.wait()
        assert monitor.store.is_whitelisted(monitor.cfg.groups[1],1234567)
        whitelist.save(['1234567'])
        release.set()
        await whitelist.task
        assert [r['user_id'] for r in monitor.store.whitelist()]==[1234567]
        whitelist.attempted.clear()
        whitelist.save(['7654321'])
        await whitelist.task
        assert whitelist.snapshot()['members'] == [dict(user_id='7654321',nickname='QQ昵称')]
        await whitelist.close()
        monitor.store.db.close()
    asyncio.run(run())
