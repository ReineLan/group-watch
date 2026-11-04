"""Live events use the ordinary moderation, identity and archive paths."""
import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from group_watch.app import create_app
from group_watch.monitoring.chat import ChatPresentation
from group_watch.monitoring.chat import safe_image_url
from group_watch.evidence.store import RecordStore
from group_watch.monitoring.feedback import Feedback
from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings
from group_watch.settings import load_settings


def config(tmp_path, **values):
    return Settings(db_path=str(tmp_path/'watch.sqlite3'), evidence_data=str(tmp_path/'archive'),
                    local_env=str(tmp_path/'.env'), live_forward_token='test-live-token', live_rooms={20:'兰音Reine直播间'},
                    evidence_tokens=['workbench-test-password'], **values)


def event(mid='one', uid='123456', kind='danmaku'):
    return dict(event_id=f'bilibili:live:20:{kind}:{mid}', source='bilibili_live', source_id='bilibili:live:20',
                event_type=kind, time=time.time(), group_id='20', user_id=uid,
                message_id=f'bilibili:live:20:{kind}:{mid}', raw_text='123456',
                message=[{'type':'text','data':{'text':'123456'}}],
                sender={'nickname':'直播观众', 'card':'', 'level':26}, assets={},
                bilibili={'room_id':'20', 'medal':{'name':'兰兔','level':8},
                          'guard_level':3, 'super_chat':{'id':mid, 'price_cny':30}})


def batch(*events):
    return dict(schema_version=1, source='bilibili_live', events=list(events))


def test_live_batch_identity_dedup_atomicity_and_restart(tmp_path, monkeypatch):
    cfg=config(tmp_path)
    monitor=Monitor(cfg)
    row=event()
    monitor.ingest_live(batch(row))
    monitor.ingest_live(batch(row))
    assert len(monitor.store.window_state.messages)==1
    case=next(iter(monitor.store.window_state.candidates.values()))
    assert (case['group_id'],case['user_id'],case['rule'])==(-20,-123456,'protected_group')
    assert case['context'][0]['text']=='123456'
    assert monitor.directory.member(-20,'-123456')=='直播观众'
    assert monitor.directory.account(-20,-123456)=='-123456'
    # Same digits on QQ are a different member and a different cooldown scope.
    qq=monitor.directory.adapt_batch(batch(event('qq')))[0]
    qq.pop('live');qq.update(group_id=cfg.groups[0],user_id=123456,message_id='qq')
    monitor.ingest(qq)
    assert len(monitor.store.window_state.candidates)==2
    saved=monitor.ingest
    def fail_second(item):
        if item['user_id']==-222222:
            raise RuntimeError('simulated failure')
        return saved(item)
    with monkeypatch.context() as patch:
        patch.setattr(monitor,'ingest',fail_second)
        with pytest.raises(RuntimeError):
            monitor.ingest_live(batch(event('rollback','111111'),event('rollback','222222')))
    assert not any(m['user_id']==-111111 for _,m in monitor.store.window_state.messages.values())
    assert not monitor.directory.member(-20,'111111')
    monitor.store.db.close()
    monitor=Monitor(cfg)
    monitor.ingest_live(batch(row))
    assert len(monitor.store.window_state.candidates)==1 and monitor.store.cases()==[]
    assert monitor.directory.member(-20,'123456')=='直播观众'
    monitor.store.db.close()


def test_live_route_separate_auth_size_validation_and_no_partial_accept(tmp_path):
    cfg=config(tmp_path);monitor=Monitor(cfg)
    with TestClient(create_app(cfg,monitor)) as client:
        url='/internal/events/live'
        assert client.post(url,json=batch(event())).status_code==401
        assert client.post(url,json=batch(event()),headers={'Authorization':'Bearer workbench-test-password'}).status_code==401
        headers={'Authorization':'Bearer test-live-token'}
        bad=event('bad');bad['user_id']='-5'
        assert client.post(url,json=batch(event(),bad),headers=headers).status_code==400
        assert len(monitor.store.window_state.messages)==0
        assert client.post(url,content=b'x'*(1024*1024+1),headers=headers).status_code==413
        assert client.post(url,json=batch(event()),headers=headers).status_code==204
        assert client.post(url,json=batch(event()),headers=headers).status_code==204
        assert client.get('/api/cases',headers=headers).status_code==401
        assert client.post('/api/auth/login',json={'token':'workbench-test-password'}).status_code==200
        pending=next(iter(monitor.store.window_state.candidates.values()))
        monitor.store.update(pending['id'],state='violation',confidence=.95)
        cases=client.get('/api/cases').json()
        assert cases[0]['member_account']=='-123456' and cases[0]['group_name']=='兰音Reine直播间'
        assert -20 in client.get('/api/status').json()['groups']


def test_live_uses_cached_identity_and_resources_without_qq(tmp_path,monkeypatch):
    async def run():
        monitor=Monitor(config(tmp_path));monitor.ingest_live(batch(event(kind='super_chat')))
        async def forbidden(*args,**kwargs):
            raise AssertionError('Live presentation must not call QQ')
        monitor.qq.call=forbidden
        chat=ChatPresentation(monitor,tmp_path/'chat-assets')
        pending=next(iter(monitor.store.window_state.candidates.values()))
        monitor.store.update(pending['id'],state='violation',confidence=.95)
        data=await chat.context(monitor.store.cases()[0])
        row=data['messages'][0]
        assert row['medal']['level']==8 and row['level']==26 and row['super_chat']['price_cny']==30
        assert row['parts']==[{'type':'text','text':'123456'}]
        found=await monitor.directory.tool('find_members',{'group_id':'-20','query':'直播观众'})
        assert found[0]['user_id']=='-123456'
        store=RecordStore(tmp_path/'archive');store.source_profile=monitor.directory.archive_profile
        store.initialize(tmp_path/'archive')
        result=store.save_records({'member_id':'-123456','nickname':'直播观众','group_id':-20,
                                   'event_date':'2026-10-29','reason':'泄露舰长群号','punishment':'禁言','penalty_text':'禁言3天'})
        assert store.get_profiles().snapshot()[result['id']]['member_id']=='-123456'
        assert store.get_records()[0]['member_id']=='-123456'
        store.close();await monitor.stop()
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    asyncio.run(run())
    assert safe_image_url('https://i0.hdslb.com/bfs/face/example.jpg')
    assert not safe_image_url('https://hdslb.com.attacker.example/image.png')


def test_live_immediate_review_and_original_text(tmp_path):
    async def run():
        monitor=Monitor(config(tmp_path,ds_key='fixture-key',batch_seconds=300))
        monitor.ingest_live(batch(event(kind='super_chat')))
        sent=[]
        def response(request):
            body=json.loads(request.content);sent.append(body)
            case=next(iter(monitor.store.window_state.candidates.values()))
            result={'id':case['id'],'verdict':'clear','confidence':.99,'reason':'fixture','evidence_ids':[]}
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[result]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(response))
        await monitor.review_once()
        assert len(sent)==1 and monitor.cfg.batch_seconds==0
        assert '123456' in sent[0]['messages'][1]['content']
        assert monitor.store.cases()==[] and not monitor.store.window_state.candidates
        await monitor.stop()
    asyncio.run(run())


def test_feedback_removes_plain_registrations_preserves_corrections(tmp_path):
    monitor=Monitor(config(tmp_path));feedback=monitor.feedback
    feedback.put('record:old','unrelated','violation','人工登记；行为：提及无关主播/up主；处理：警告；判断要点：')
    feedback.edit('','abuse','clear','抱怨公司不等于攻击群友')
    feedback=Feedback(monitor.store)
    assert any(p['source']=='record:old' for p in feedback.points())
    feedback.record({'id':'normal','category':'抢红包外挂'})
    assert not any(p['source']=='record:normal' for p in feedback.points())
    row={'id':'boundary','category':'辱骂'}
    feedback.record(row,'应结合攻击对象判断')
    assert not any(p['source']=='record:boundary' for p in feedback.points())
    assert monitor.store.db.execute('SELECT 1 FROM feedback_jobs WHERE source=?',('record:boundary',)).fetchone()
    feedback.put('record:boundary','辱骂','violation','应结合攻击对象判断')
    feedback.edit('record:boundary','辱骂','violation','应结合攻击对象判断')
    feedback.record(row)
    assert any(p['source']=='record:boundary' and p['summary']=='应结合攻击对象判断' for p in feedback.points())
    monitor.store.db.close()


def test_legacy_words_merge_and_immediate_config(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'blocked_words':['甲'],'unrelated_streamers':['甲','乙'],'sensitive_topics':['丙'],
                                'batch_seconds':300,'local_env':str(tmp_path/'empty.env')}),encoding='utf-8')
    cfg=load_settings(path)
    assert cfg.blocked_words==['甲','乙','丙'] and cfg.unrelated_streamers==cfg.sensitive_topics==[]
    assert cfg.batch_seconds==0
