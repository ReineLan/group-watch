def case_rows(store):
    return list(store.window_state.candidates.values())+store.cases()

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from group_watch.app import create_app
from group_watch.monitoring.rules import detect
from group_watch.monitoring.rules import message_content
from group_watch.monitoring.service import Monitor
from group_watch.monitoring.service import validate_results
from group_watch.monitoring.service import review_payload
from group_watch.settings import Settings
from group_watch.settings import PushRecipient
from group_watch.settings import load_settings
from group_watch.settings import save_push_recipients
from group_watch.settings import save_rules
from group_watch.settings import rule_settings


def config(tmp_path, **kwargs):
    return Settings(db_path=str(tmp_path/'watch.db'), local_env=str(tmp_path/'.env'), settings_file=str(tmp_path/'rules.json'), **kwargs)


def event(mid='1', text='你好', group=100000001, user=123, stamp=None):
    return dict(post_type='message', message_type='group', group_id=group, user_id=user,
                message_id=mid, time=stamp or time.time(), message=text, sender={'nickname':'<script>evil</script>'})



def signed_client(app):
    # Domain endpoint tests use an explicit cookie login; CSRF checks stay active.
    app.state.auth.configure_tokens(['domain-fixture-password'])
    client = TestClient(app)
    assert client.post('/api/auth/login', json={'token':'domain-fixture-password'}).status_code == 200
    return client

def test_rules_dedupe_scope_and_snapshots(tmp_path):
    monitor = Monitor(config(tmp_path))
    now = time.time()
    assert not monitor.ingest(event(group=123456, text='123456'), now)
    assert not monitor.ingest(event(stamp=now-400, text='123456'), now)
    assert monitor.ingest(event(text='１２３４５６'), now) == 1
    assert not monitor.ingest(event(text='１２３４５６'), now)
    c = case_rows(monitor.store)[0]
    assert c['rule'] == 'protected_group' and c['state'] == 'pending'
    assert c['context'][0]['text'] == '１２３４５６'
    assert not monitor.ingest(event(mid='2',text='123456'),now)
    monitor.store.prune(1)
    assert case_rows(monitor.store)[0]['evidence'] == ['1']
    monitor.store.db.close()


def test_mentions_repeat_and_flood(tmp_path):
    monitor = Monitor(config(tmp_path, flood_count=4))
    now = time.time()
    for i in range(4):
        monitor.ingest(event(str(i), stamp=now+i, text='正常接龙'), now+i)
    assert {c['rule'] for c in case_rows(monitor.store)} == {'repeat','flood'}
    monitor.ingest(event('at', text=[{'type':'at','data':{'qq':'100000003'}}], user=456), now)
    assert 'mention' in {c['rule'] for c in case_rows(monitor.store)}
    assert message_content('[CQ:at,qq=100000003] hi[CQ:image,file=private]') == (' hi',['100000003'],['image'])
    monitor.store.db.close()


def test_configured_protected_identifiers(tmp_path):
    cfg = config(tmp_path, protected_qq=100000009, protected_groups=[100000008])

    def hits(text='', mentions=()):
        return detect(cfg, dict(text=text, mentions=list(mentions), user_id=123,
                                message_id='protected', time=time.time()), [])

    assert set(hits('账号：１０００００００９')) == {'privacy'}
    assert set(hits(mentions=['100000009'])) == {'mention'}
    assert set(hits('１０００００００８')) == {'protected_group'}
    assert not hits('100000003 123456', ['100000003'])


def case():
    return dict(id='a', evidence=['1'], user_id=1, context=[dict(message_id='1', user_id=1),dict(message_id='2',user_id=2)])


def result(**changes):
    return dict(id='a', verdict='violation', confidence=.95, reason='证据说明', evidence_ids=['1']) | changes


@pytest.mark.parametrize('changes',[{'evidence_ids':['2']},{'evidence_ids':[]},{'id':'other'},
                                  {'confidence':float('nan')},{'confidence':True},{'reason':''},{'verdict':'ban'}])
def test_reject_invalid_ai(changes):
    with pytest.raises(ValueError):
        validate_results(json.dumps({'results':[result(**changes)]}),[case()])


def test_low_confidence_is_unresolved():
    assert validate_results(json.dumps({'results':[result(confidence=.6)]}),[case()])['a']['state']=='unsure'


def test_snowluma_status_guard(tmp_path):
    onebot=tmp_path/'onebot.json'
    cfg=tmp_path/'config.json'
    cfg.write_text(json.dumps({'snowluma_config':str(onebot),'lan_env':str(tmp_path/'none')}),encoding='utf-8')
    onebot.write_text(json.dumps({'statusCommand':{'enabled':True}}),encoding='utf-8')
    with pytest.raises(ValueError,match='statusCommand'):
        load_settings(cfg)


@pytest.mark.parametrize('verdict,confidence', [('unsure', .95), ('violation', .6)])
def test_insufficient_review_discards_case_and_its_resources(tmp_path, verdict, confidence):
    async def run():
        monitor=Monitor(config(tmp_path,ds_key=SecretStr('fake')))
        monitor.ingest(event(text='123456'));candidate=next(iter(monitor.store.window_state.candidates.values()))
        def handler(request):
            row=result(id=candidate['id'],verdict=verdict,confidence=confidence)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[row]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once()
        assert not monitor.store.window_state.candidates and not monitor.store.cases()
        assert monitor.store.db.execute('SELECT count(*) FROM case_resources').fetchone()[0]==0
        assert len(list((tmp_path/'logs'/'ds-requests').rglob('*.json')))==1
        await monitor.stop()
    asyncio.run(run())


def test_review_and_notification(tmp_path):
    async def run():
        sent=[]
        monitor=Monitor(config(tmp_path, ds_key=SecretStr('fake'), pushplus_recipients=[PushRecipient(token=SecretStr('fake'))]))
        monitor.ingest(event(text='123456'))
        c=case_rows(monitor.store)[0]
        with monitor.store.db:
            [row.update(created=time.time()-30) for row in monitor.store.window_state.candidates.values()]
        def handler(req):
            body=json.loads(req.content)
            if 'deepseek' in req.url.host:
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[result(id=c['id'])]})}}], 'usage':{'prompt_tokens':50,'completion_tokens':20}})
            sent.append(body)
            return httpx.Response(200,json={'code':200})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once()
        assert case_rows(monitor.store)[0]['state']=='violation'
        await monitor.notify_once()
        await monitor.notify_once()
        assert len(sent)==1 and '&lt;script&gt;' in sent[0]['content']
        assert monitor.quota.calls_hour(time.time())==1
        await monitor.stop()
    asyncio.run(run())


def test_failures_retry_budget_and_push_business_error(tmp_path):
    async def run():
        monitor=Monitor(config(tmp_path, ds_key=SecretStr('fake'), pushplus_recipients=[PushRecipient(token=SecretStr('fake'))],query_calls_hour=1))
        monitor.ingest(event(text='123456'))
        c=case_rows(monitor.store)[0]
        with monitor.store.db:
            [row.update(created=time.time()-30) for row in monitor.store.window_state.candidates.values()]
        calls=[]
        def handler(req):
            calls.append(req.url.host)
            return httpx.Response(200,json={'code':500})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once()
        assert case_rows(monitor.store)[0]['attempts']==1
        assert case_rows(monitor.store)[0]['state']=='pending'
        monitor.store.update(c['id'],next_try=0)
        await monitor.review_once()
        assert len(calls)==1
        monitor.store.update(c['id'],state='violation',confidence=.95)
        await monitor.notify_once()
        assert case_rows(monitor.store)[0]['notified']==0
        assert case_rows(monitor.store)[0]['notify_attempts']==1
        await monitor.stop()
    asyncio.run(run())


@pytest.mark.parametrize('failure,expected',[
    ('timeout','DS请求超时'),
    ('http','HTTP 429'),
    ('length','DS输出达到长度上限'),
    ('json','不是有效 JSON'),
    ('evidence','DS引用不存在或非本人证据'),
    ('shape','DS返回结构不符合复核要求'),
])
def test_review_failure_diagnostics_keep_evidence_pending_and_redact_secrets(tmp_path,failure,expected):
    async def run():
        monitor=Monitor(config(tmp_path,ds_key=SecretStr('private-secret')))
        monitor.ingest(event(text='123456'))
        case=case_rows(monitor.store)[0]
        with monitor.store.db:
            [row.update(created=time.time()-30) for row in monitor.store.window_state.candidates.values()]
        def handler(req):
            if failure=='timeout':
                raise httpx.ReadTimeout('private-secret in request URL',request=req)
            if failure=='http':
                return httpx.Response(429,text='private-secret')
            content='invalid private-secret' if failure=='json' else json.dumps({'results':[result(id=case['id'],evidence_ids=['other-person'])]})
            body=[] if failure=='shape' else {'choices':[{'finish_reason':'length' if failure=='length' else 'stop','message':{'content':content}}],'usage':{'completion_tokens':3500}}
            return httpx.Response(200,json=body)
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once()
        saved=case_rows(monitor.store)[0]
        assert expected in monitor.review_error and 'private-secret' not in monitor.review_error
        assert saved['state']=='pending' and saved['attempts']==1 and saved['next_try']>time.time()
        assert saved['error']==monitor.review_error and monitor.quota.calls_hour(time.time())==1
        if failure=='length':
            assert json.loads(next((tmp_path/'logs'/'ds-requests').rglob('*.json')).read_text())['output']['usage']['completion_tokens']==3500
        await monitor.stop()
    asyncio.run(run())


def test_web_host_csrf_and_decision(tmp_path):
    cfg=config(tmp_path)
    monitor=Monitor(cfg)
    monitor.ingest(event(text='123456'))
    c=case_rows(monitor.store)[0]
    monitor.store.update(c['id'],state='violation',confidence=.95,reason='经复核的证据')
    app=create_app(cfg,monitor)
    # No lifespan: this test exercises HTTP endpoints without real workers.
    client=signed_client(app)
    assert client.get('/api/status',headers={'host':'evil.example'}).status_code==403
    page=client.get('/')
    assert page.status_code==200 and 'fake' not in page.text
    url='/api/cases/'+c['id']+'/decision'
    body={'resolution':'confirmed','note':'已人工确认'}
    assert client.post(url,json=body).status_code==403
    token=page.text.split("const token='")[1].split("'")[0]
    assert client.post(url,json=body,headers={'X-CSRF-Token':token}).status_code==200
    assert client.get('/api/cases').json()[0]['resolution']=='confirmed'
    assert 'ds_key' not in client.get('/api/status').text
    assert monitor.store.cases()[0]['decision_at'] is not None
    client.close()
    monitor.store.db.close()


def test_pushplus_save_preserves_env_and_reload(tmp_path, monkeypatch):
    cfg=config(tmp_path)
    path=tmp_path/'.env'
    path.write_text('# 本地配置\nOTHER_SECRET=preserve-me\nPUSHPLUS_ENABLED=false\n',encoding='utf-8-sig')
    new_token="new'${MISSING_TEST_VARIABLE}-token"
    save_push_recipients(cfg,[PushRecipient(id='first',token=new_token)])
    content=path.read_text(encoding='utf-8')
    assert '# 本地配置' in content and 'OTHER_SECRET=preserve-me' in content
    assert 'PUSHPLUS_TOKEN' not in content
    monkeypatch.setenv('PUSHPLUS_TOKEN','environment-token')
    settings=tmp_path/'settings.json'
    settings.write_text(json.dumps({'local_env':str(path),'lan_env':str(tmp_path/'absent')}),encoding='utf-8')
    restored=load_settings(settings)
    assert restored.pushplus_recipients[0].token.get_secret_value()==new_token and restored.pushplus_enabled
    save_push_recipients(cfg,[])
    assert load_settings(settings).pushplus_recipients==[]
    assert not list(tmp_path.glob('.push-*.env'))


def test_pushplus_failed_write_keeps_live_settings(tmp_path, monkeypatch):
    cfg=config(tmp_path,pushplus_recipients=[PushRecipient(token='old-token')],pushplus_enabled=False)
    path=tmp_path/'.env'
    path.write_text('OTHER=untouched\n',encoding='utf-8')
    def deny(*args):
        raise PermissionError('denied')
    monkeypatch.setattr('group_watch.settings.os.replace',deny)
    with pytest.raises(PermissionError):
        save_push_recipients(cfg,[PushRecipient(token='replacement-token')])
    assert cfg.pushplus_recipients[0].token.get_secret_value()=='old-token' and not cfg.pushplus_enabled
    assert path.read_text(encoding='utf-8')=='OTHER=untouched\n'
    assert not list(tmp_path.glob('.push-*.env'))


def test_notification_settings_security_and_validation(tmp_path):
    cfg=config(tmp_path)
    monitor=Monitor(cfg)
    client=signed_client(create_app(cfg,monitor))
    csrf=client.get('/').text.split("const token='")[1].split("'")[0]
    headers={'X-CSRF-Token':csrf}
    url='/api/settings/notifications'
    assert client.post(url,json={'token':'test-secret-token'}).status_code==403
    for value in ['short','new\nTOKEN=bad','含中文token',{'secret':'do-not-echo'}]:
        r=client.post(url,json={'recipients':[{'token':value}]},headers=headers)
        assert r.status_code in (400,422) and 'do-not-echo' not in r.text
    assert not (tmp_path/'.env').exists()
    assert client.post(url,json={'token':'test-secret-token'},headers=headers).status_code==422
    assert client.post(url,json={'recipients':[{'id':'first','token':'test-secret-token'}]},headers=headers).status_code==200
    r=client.get(url)
    data=r.json();recipients=data.pop('recipients');assert len(recipients)==1 and recipients[0]['configured']
    assert data=={'configured':True,'enabled':True,'saved_locally':True,'broadcast_targets':[],'broadcast_confidence':.95}
    assert 'test-secret-token' not in r.text+client.get('/api/status').text+client.get('/').text
    bundle = __import__('re').search(r'src="(/ui/assets/[^"]+\.js)"', client.get('/').text)
    assert bundle and client.get(bundle[1]).status_code == 200
    css = __import__('re').search(r'href="(/ui/assets/[^"]+\.css)"', client.get('/').text)
    assert css and client.get(css[1]).status_code == 200
    assert client.post(url,json={'recipients':[{'id':'first','name':'改名','token':''}]},headers=headers).status_code==200
    assert cfg.pushplus_recipients[0].token.get_secret_value()=='test-secret-token' and cfg.pushplus_enabled
    client.close();monitor.store.db.close()


def test_notification_test_business_error_rate_limit_and_payload(tmp_path):
    cfg=config(tmp_path,pushplus_recipients=[PushRecipient(token=SecretStr('test-secret-token'))])
    monitor=Monitor(cfg)
    sent=[]
    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200,json={'code':500,'msg':'do-not-echo-secret'})
    monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client=signed_client(create_app(cfg,monitor))
    csrf=client.get('/').text.split("const token='")[1].split("'")[0]
    url='/api/settings/notifications/test';headers={'X-CSRF-Token':csrf}
    assert client.post(url,json={}).status_code==403
    response=client.post(url,json={},headers=headers)
    assert response.status_code==502 and 'do-not-echo-secret' not in response.text
    assert client.post(url,json={},headers=headers).status_code==429
    assert len(sent)==1 and '测试' in sent[0]['title'] and '不包含群聊内容' in sent[0]['content']
    assert '100000001' not in sent[0]['content']
    client.close();asyncio.run(monitor.stop())


@pytest.mark.parametrize('fail',[False, True])
def test_qq_notification_test_uses_saved_verified_targets_and_throttles(tmp_path, monkeypatch, fail):
    cfg=config(tmp_path,broadcast_targets=[{'kind':'group','id':'100000010'}])
    monitor=Monitor(cfg);sent=[];verified=[]
    async def resolve(targets):
        verified.extend(targets)
        return [{'kind':'group','id':'100000010','name':'测试群'}]
    async def call(action,params):
        sent.append((action,params))
        if fail:
            raise ValueError('private-secret')
    monkeypatch.setattr(monitor.directory,'resolve_targets',resolve)
    monkeypatch.setattr(monitor.qq,'call',call)
    app=create_app(cfg,monitor)
    client=signed_client(app)
    csrf=client.get('/').text.split("const token='")[1].split("'")[0]
    url='/api/settings/broadcast/test'
    assert client.post(url,json={}).status_code==403
    response=client.post(url,json={},headers={'X-CSRF-Token':csrf})
    assert response.status_code==(502 if fail else 200)
    assert 'private-secret' not in response.text
    assert verified[0]['id']=='100000010'
    assert sent[0][0]=='send_group_msg' and sent[0][1]['group_id']==100000010
    assert '测试' in sent[0][1]['message'][0]['data']['text']
    assert client.post(url,json={},headers={'X-CSRF-Token':csrf}).status_code==429
    assert len(sent)==1
    client.close();asyncio.run(monitor.stop());app.state.evidence.close()


def test_configured_notifications_are_always_enabled_and_deduplicated(tmp_path):
    async def run():
        cfg=config(tmp_path,pushplus_recipients=[PushRecipient(token=SecretStr('test-secret-token'))],pushplus_enabled=False)
        monitor=Monitor(cfg)
        monitor.ingest(event(text='123456'))
        candidate=case_rows(monitor.store)[0]
        monitor.store.update(candidate['id'],state='violation',confidence=.95)
        sent=[]
        def handler(req):
            sent.append(req)
            return httpx.Response(200,json={'code':200})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.notify_once()
        assert len(sent)==1 and case_rows(monitor.store)[0]['notified']==1
        await monitor.notify_once()
        assert len(sent)==1 and case_rows(monitor.store)[0]['notified']==1
        await monitor.stop()
    asyncio.run(run())


def test_manual_dismissal_retains_latest_decision_and_feedback(tmp_path):
    monitor=Monitor(config(tmp_path));monitor.ingest(event(text='123456'))
    row=next(iter(monitor.store.window_state.candidates.values()));monitor.store.update(row['id'],state='violation',confidence=.95,reason='证据')
    client=signed_client(create_app(monitor.cfg,monitor));token=client.get('/').text.split("const token='")[1].split("'")[0]
    response=client.post('/api/cases/'+row['id']+'/decision',json={'resolution':'dismissed','note':'这是引用说明'},headers={'X-CSRF-Token':token})
    assert response.status_code==200
    saved=monitor.store.cases()[0];assert saved['resolution']=='dismissed' and saved['note']=='这是引用说明' and saved['decision_at']
    assert monitor.store.db.execute('SELECT count(*) FROM feedback_jobs').fetchone()[0]==1
    client.close();monitor.store.db.close()


def test_case_search_combines_group_resolution_and_state(tmp_path):
    cfg=config(tmp_path)
    monitor=Monitor(cfg)
    monitor.ingest(event('a',text='123456 线索甲',user=111))
    monitor.ingest(event('b',text='123456 线索乙',group=100000002,user=222))
    candidate=next(c for c in case_rows(monitor.store) if c['user_id']==111)

    for row in list(monitor.store.window_state.candidates.values()): monitor.store.update(row['id'],state='violation',confidence=.95,reason='证据')
    monitor.store.update(candidate['id'],resolution='follow_up')
    client=signed_client(create_app(cfg,monitor))
    assert len(client.get('/api/cases',params={'search':'线索甲','group':100000001,'state':'violation','resolution':'handled'}).json())==1
    assert client.get('/api/cases',params={'search':'线索甲','resolution':'open'}).json()==[]
    assert len(client.get('/api/cases',params={'search':'222'}).json())==1
    assert client.get('/api/cases',params={'search':"' OR 1=1 --"}).json()==[]
    assert client.get('/api/cases',params={'group':123456}).status_code==400
    full = client.get('/api/cases').json()
    summary = client.get('/api/cases', params={'limit':1, 'summary':True}).json()
    assert len(summary) == 1 and summary[0]['id'] == full[0]['id']
    assert summary[0]['member_name'] == full[0]['member_name']
    assert summary[0]['member_account'] == full[0]['member_account']
    assert not {'context', 'evidence', 'reason'} & summary[0].keys()
    second = client.get('/api/cases', params={'limit':1, 'offset':1, 'summary':True}).json()
    assert second[0]['id'] == full[1]['id']
    assert client.get('/api/cases', params={'limit':0}).status_code == 400
    assert client.get('/api/cases', params={'limit':51}).status_code == 400
    stats=client.get('/api/status').json()
    assert stats['open_cases']==1 and sum(g['messages'] for g in stats['activity'])==2
    client.close();monitor.store.db.close()


def test_card_metadata_does_not_trigger_ad_and_legacy_snapshot_is_readable(tmp_path):
    monitor=Monitor(config(tmp_path))
    raw=json.dumps({'prompt':'群相册《兰圈》','meta':{'feed':{'cover':'http://photo.test/a','title':'上传1张图片'}},'config':{'url':'https://qzone.test/private'}},ensure_ascii=False)
    segments=[{'type':'json','data':{'data':raw}},{'type':'face','data':{'id':'1'}},{'type':'reply','data':{'id':'previous'}}]
    text,mentions,media=message_content(segments)
    assert text=='群相册《兰圈》 · 上传1张图片' and not mentions and media==['json','face','reply']
    assert monitor.ingest(event(text=segments))==0
    assert message_content('[CQ:face,id=1][CQ:reply,id=12]')[2]==['face','reply']
    cq='[CQ:json,data='+raw.replace(',', '&#44;')+']'
    assert message_content(cq)[0]==text
    assert message_content([{'type':'xml','data':{'data':'<msg url="https://resource.test"><title>相册</title><summary><![CDATA[正常分享]]></summary></msg>'}}])[0]=='相册 · 正常分享'
    # Old snapshots retain their stored original text; API adapts only presentation.
    msg=dict(group_id=100000001,user_id=123,message_id='legacy',time=time.time(),text=raw,mentions=[],media=['json'],name='测试')
    monitor.store.window_state.candidate(msg,'ad',['legacy'],[msg],0,time.time())
    monitor.store.update(next(reversed(monitor.store.window_state.candidates)),state='violation',confidence=.95,reason='证据')
    client=signed_client(create_app(monitor.cfg,monitor))
    presented=client.get('/api/cases').json()[0]['context'][0]['text']
    assert presented==text and 'http' not in presented
    assert case_rows(monitor.store)[0]['context'][0]['text']==raw
    client.close();monitor.store.db.close()


def test_flood_ten_messages_in_one_minute(tmp_path):
    monitor=Monitor(config(tmp_path))
    now=time.time()
    monitor.ingest(event('outside',text='之前的聊天',stamp=now-121),now-121)
    for i in range(9):
        monitor.ingest(event(str(i),text=f'普通聊天{i}',stamp=now-54+i*6),now-54+i*6)
    assert not case_rows(monitor.store)
    assert monitor.ingest(event('last',text='最后一句',stamp=now),now)==1
    candidate=case_rows(monitor.store)[0]
    assert candidate['rule']=='flood' and len(candidate['evidence'])==10 and 'outside' not in candidate['evidence']
    monitor.store.db.close()


def test_image_urls_and_pixels_are_never_sent_to_review(tmp_path):
    monitor=Monitor(config(tmp_path))
    monitor.ingest(event('image',text=[{'type':'image','data':{'url':'https://private-media.test/photo','file':'base64://PRIVATE_PIXELS'}}]))
    monitor.ingest(event('trigger',text='123456'))
    payload=review_payload(case_rows(monitor.store))
    encoded=json.dumps(payload)
    assert 'private-media.test' not in encoded and 'PRIVATE_PIXELS' not in encoded
    assert any(m['media']==['image'] and m['text']=='' for m in payload['messages'])
    monitor.store.db.close()


def test_multirule_review_shares_context_and_does_not_recheck_completed_cases(tmp_path):
    async def run():
        monitor=Monitor(config(tmp_path,ds_key=SecretStr('fake')))
        assert monitor.ingest(event(text='123456 进群领取'))==2
        batch=case_rows(monitor.store)
        payload=review_payload(batch)
        assert len(payload['messages'])==1 and len(payload['candidates'])==2
        assert payload['candidates'][0]['context_keys']==payload['candidates'][1]['context_keys']
        assert all('context' not in c for c in payload['candidates'])
        # Same message id in another group must remain a separate piece of evidence.
        other={**batch[0],'group_id':100000002}
        assert len(review_payload([batch[0],other])['messages'])==2
        with monitor.store.db:
            [row.update(created=time.time()-30) for row in monitor.store.window_state.candidates.values()]
        requests=[]
        def handler(req):
            data=json.loads(req.content);requests.append(data)
            prompt=json.loads(data['messages'][1]['content'])
            assert len(prompt['messages'])==1 and len(prompt['candidates'])==2
            rows=[result(id=c['id'],verdict='clear',evidence_ids=[]) for c in batch]
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':rows})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await monitor.review_once();await monitor.review_once()
        assert len(requests)==1 and case_rows(monitor.store)==[]
        await monitor.stop()
    asyncio.run(run())


def test_budget_and_candidates_are_memory_only_and_reset_on_restart(tmp_path):
    from group_watch.ds.client import audited_post
    async def run():
        cfg=config(tmp_path,ds_key=SecretStr('fake'))
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(500))) as client:
            for _ in range(5): await audited_post(cfg,'automatic-review',client,'https://example.test/review',json={})
        monitor=Monitor(cfg)
        assert monitor.quota.calls_hour(time.time())==0 and not monitor.store.window_state.candidates
        monitor.ingest(event(text='123456'));calls=[]
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda req:(calls.append(req),httpx.Response(500))[1]))
        await monitor.review_once();assert len(calls)==1 and monitor.quota.calls_hour(time.time())==1
        assert len(monitor.store.window_state.candidates)==1
        now=time.time()
        for _ in range(4): monitor.quota.record(now)
        assert monitor.quota.calls_hour(now)==5
        assert monitor.quota.calls_hour(now+3601)==0
        await monitor.stop()
        restarted=Monitor(cfg)
        assert restarted.quota.calls_hour(time.time())==0 and not restarted.store.window_state.candidates
        await restarted.stop()
    asyncio.run(run())


def test_rules_save_preserves_config_reload_and_failure(tmp_path,monkeypatch):
    cfg=config(tmp_path)
    path=tmp_path/'rules.json'
    path.write_text(json.dumps({'ds_key':'private-key','groups':[100000001],'lan_env':str(tmp_path/'absent'),'local_env':str(tmp_path/'.env')}),encoding='utf-8-sig')
    values=rule_settings(cfg)|{'blocked_words':['测试词','测试词'],'unrelated_streamers':['具体主播'],'sensitive_topics':['具体话题']}
    save_rules(cfg,values)
    assert cfg.blocked_words==['测试词','具体主播','具体话题']
    restored=load_settings(path)
    assert restored.blocked_words==['测试词','具体主播','具体话题'] and restored.query_calls_hour==5 and restored.flood_seconds==60
    assert json.loads(path.read_text(encoding='utf-8'))['ds_key']=='private-key'
    before=path.read_bytes()
    def deny(*args): raise PermissionError('denied')
    monkeypatch.setattr('group_watch.settings.os.replace',deny)
    with pytest.raises(PermissionError): save_rules(cfg,values|{'flood_seconds':45})
    assert cfg.flood_seconds==60 and path.read_bytes()==before and not list(tmp_path.glob('.group-watch-*.json'))


def test_rules_api_csrf_validation_and_immediate_effect(tmp_path):
    cfg=config(tmp_path)
    monitor=Monitor(cfg);client=signed_client(create_app(cfg,monitor))
    csrf=client.get('/').text.split("const token='")[1].split("'")[0]
    headers={'X-CSRF-Token':csrf};url='/api/settings/rules'
    values=client.get(url).json()
    assert values['flood_seconds']==60 and values['query_calls_hour']==5
    assert client.post(url,json=values).status_code==403
    assert client.get(url,headers={'Host':'evil.example'}).status_code==403
    for changes in [{'flood_seconds':0},{'query_calls_hour':0},{'blocked_words':['']},{'sensitive_topics':['x'*81]},{'blocked_words':['x']*601},{'ds_key':'do-not-echo'}]:
        r=client.post(url,json=values|changes,headers=headers)
        assert r.status_code==422 and 'do-not-echo' not in r.text
    assert not (tmp_path/'rules.json').exists()
    assert client.post(url,json=values|{'blocked_words':[' 测试词 ']},headers=headers).status_code==200
    assert monitor.ingest(event(text='测试词'))==1
    assert case_rows(monitor.store)[0]['rule']=='blocked'
    assert client.get('/api/status').json()['rules']['blocked_words']==['测试词']
    client.close();monitor.store.db.close()


def test_case_decisions_replace_latest_without_audit_history(tmp_path):
    monitor=Monitor(config(tmp_path));monitor.ingest(event(text='123456'))
    row=next(iter(monitor.store.window_state.candidates.values()));monitor.store.update(row['id'],state='violation',confidence=.95,reason='证据')
    client=signed_client(create_app(monitor.cfg,monitor));token=client.get('/').text.split("const token='")[1].split("'")[0]
    for resolution in ('dismissed','confirmed'):
        response=client.post('/api/cases/'+row['id']+'/decision',json={'resolution':resolution,'note':resolution},headers={'X-CSRF-Token':token})
        assert response.status_code==200
        assert monitor.store.cases()[0]['resolution']==resolution
    assert len(client.get('/api/cases?resolution=handled').json())==1
    assert 'audit' not in {r[0] for r in monitor.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    client.close();monitor.store.db.close()
