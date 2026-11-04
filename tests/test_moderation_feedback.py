def case_rows(store):
    return list(store.window_state.candidates.values())+store.cases()

"""Human guidance, notification fanout and bounded registration regressions."""
import asyncio
import base64
import json
import re
import sqlite3
import time

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from group_watch.app import create_app
from group_watch.monitoring.feedback import Feedback
from group_watch.monitoring.feedback import MAX_CONTEXT
from group_watch.monitoring.feedback import MAX_EXAMPLES
from group_watch.evidence.registration import analyze
from group_watch.monitoring.service import Monitor
from group_watch.settings import Settings
from group_watch.settings import PushRecipient
from group_watch.settings import save_push_recipients
from group_watch.settings import push_recipients
from group_watch.settings import load_settings


def settings(tmp_path, **changes):
    return Settings(db_path=str(tmp_path/'watch.sqlite3'),local_env=str(tmp_path/'.env'),evidence_tokens=['中文测试密码'],**changes)


def test_feedback_deduplicates_stored_rows_and_keeps_human_version(tmp_path):
    monitor=Monitor(settings(tmp_path))
    feedback=monitor.feedback
    source=feedback.edit('','abuse','clear','结合攻击对象判断。')
    feedback.put('case:duplicate','abuse','clear','结合攻击对象判断。')
    assert [r['source'] for r in monitor.store.db.execute('SELECT source FROM moderation_feedback')]==[source]
    feedback.put('case:other-rule','ad','clear','结合攻击对象判断。')
    assert monitor.store.db.execute('SELECT count(*) FROM moderation_feedback').fetchone()[0]==2
    feedback.put('case:third','abuse','clear','不同摘要')
    feedback.edit('case:third','abuse','clear','结合攻击对象判断。')
    rows=monitor.store.db.execute("SELECT source FROM moderation_feedback WHERE rule='abuse'").fetchall()
    assert [r['source'] for r in rows]==['case:third']
    monitor.store.db.close()


def test_feedback_deleted_during_extraction_cannot_reappear(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.feedback.on_queue=None
        source='record:deleted'
        monitor.feedback.queue(source,'abuse','clear','需要结合攻击对象判断')
        def respond(request):
            monitor.feedback.remove(source)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[{'source':source,'reusable':True,'summary':'迟到的摘要'}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        await monitor.feedback.process(monitor)
        assert monitor.store.db.execute('SELECT count(*) FROM moderation_feedback').fetchone()[0]==0
        assert monitor.store.db.execute('SELECT count(*) FROM feedback_jobs').fetchone()[0]==0
        await monitor.stop()
    asyncio.run(run())


def test_feedback_uses_own_evidence_and_human_edits_survive_refresh(tmp_path):
    monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture-key')))
    feedback=monitor.feedback
    case={'id':'fixture','rule':'abuse','user_id':12345,'evidence':['1'],
          'reason':'DS invented reasoning must not be copied','context':[
              {'message_id':'1','user_id':12345,'text':'抱怨公司，联系123456789'},
              {'message_id':'2','user_id':99999,'text':'someone else private text'}]}
    feedback.case(case,'dismissed','攻击对象是公司，并未攻击群友')
    assert not any(p['source']=='case:fixture' for p in feedback.points())
    pending=json.loads(monitor.store.db.execute('SELECT payload FROM feedback_jobs').fetchone()[0])
    assert '攻击对象是公司' in pending['note']
    assert all(text not in str(pending) for text in ('invented','someone else','123456789'))
    async def extract():
        def respond(request):
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[{'source':'case:fixture','reusable':True,'summary':'攻击对象是公司时，应先核对是否攻击群友。'}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        assert await feedback.process(monitor)==1
        await monitor.client.aclose()
    asyncio.run(extract())
    logs=[json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path/'logs'/'ds-requests').rglob('*.json')]
    assert len(logs)==1 and logs[0]['scope']=='feedback' and logs[0]['status']=='received'
    point=next(p for p in feedback.points() if p['source']=='case:fixture')
    assert point['verdict']=='clear' and '攻击对象是公司' in point['summary']
    assert all(text not in point['summary'] for text in ('invented','someone else','123456789'))
    feedback.edit(point['source'],'abuse','clear','工作抱怨应结合攻击对象判断。')
    feedback.case(case,'dismissed','new automatic summary')
    assert next(p for p in feedback.points() if p['source']==point['source'])['summary']=='工作抱怨应结合攻击对象判断。'
    feedback.remove(point['source'])
    assert not monitor.store.db.execute('SELECT 1 FROM moderation_feedback WHERE source=?',(point['source'],)).fetchone()
    assert not monitor.store.db.execute('SELECT 1 FROM feedback_jobs WHERE source=?',(point['source'],)).fetchone()
    feedback.case(case,'dismissed','new note after explicit deletion')
    assert not any(p['source']==point['source'] for p in feedback.points())
    feedback.remove('manual:company-complaint')
    assert Feedback(monitor.store).points()==[]
    feedback.case(case,'','')
    assert not monitor.store.db.execute('SELECT 1 FROM moderation_feedback WHERE source=?',(point['source'],)).fetchone()
    monitor.store.db.close()


def test_feedback_pending_revisions_budget_and_routine_notes(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture'),query_calls_hour=1))
        feedback=monitor.feedback
        feedback.on_queue=None  # Exercise revision handling without the live dispatcher.
        feedback.record({'id':'fixture','category':'abuse','reason':'原文'},'警告一次')
        monitor.quota.record(time.time())
        assert await feedback.process(monitor,manual=False)==0
        assert feedback.points()==[]
        def supersede(request):
            feedback.record({'id':'fixture','category':'abuse'},'新的备注')
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[{'source':'record:fixture','reusable':True,'summary':'过期边界'}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(supersede))
        assert await feedback.process(monitor,manual=True)==1
        assert '过期边界' not in str(feedback.points())
        assert '新的备注' in monitor.store.db.execute('SELECT payload FROM feedback_jobs').fetchone()[0]
        await monitor.client.aclose()
        def routine(request):
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[{'source':'record:fixture','reusable':False,'summary':''}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(routine))
        assert await feedback.process(monitor,manual=True)==1
        assert monitor.quota.calls_hour(time.time())==1
        assert monitor.store.db.execute('SELECT count(*) FROM feedback_jobs').fetchone()[0]==0
        assert feedback.points()==[]
        feedback.record({'id':'removed','category':'abuse'},'待处理')
        feedback.remove('record:removed')
        assert monitor.store.db.execute('SELECT count(*) FROM feedback_jobs').fetchone()[0]==0
        await monitor.stop()
    asyncio.run(run())


def test_feedback_failed_model_output_stays_pending_and_never_becomes_guidance(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.feedback.record({'id':'fixture','category':'abuse'},'原始私人备注')
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"results":[]}'}}]})))
        assert await monitor.feedback.process(monitor)==0
        pending=monitor.store.db.execute('SELECT * FROM feedback_jobs').fetchone()
        assert pending['attempts']==1 and pending['next_try']>time.time()
        assert '原始私人备注' not in str(monitor.feedback.context())
        assert await monitor.feedback.process(monitor)==0
        assert monitor.quota.calls_hour(time.time())==0
        await monitor.stop()
    asyncio.run(run())


def test_feedback_startup_preserves_current_summaries_without_side_effects(tmp_path):
    monitor=Monitor(settings(tmp_path))
    monitor.feedback.put('case:kept','abuse','clear','提炼过的边界')
    source=monitor.feedback.edit('','abuse','clear','人工编辑边界')
    before=monitor.feedback.points()
    assert Feedback(monitor.store).points()==before
    assert not list(tmp_path.rglob('*.sqlite3')) or list(tmp_path.rglob('*.sqlite3'))==[tmp_path/'watch.sqlite3']
    assert not (tmp_path/'backups').exists()
    monitor.store.db.close()


def test_feedback_timeout_retains_pending_job_without_raw_guidance(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.feedback.record({'id':'timeout','category':'abuse'},'私人原始备注')
        def timeout(request):
            raise httpx.ReadTimeout('fixture timeout',request=request)
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(timeout))
        assert await monitor.feedback.process(monitor,manual=True)==0
        row=monitor.store.db.execute('SELECT * FROM feedback_jobs').fetchone()
        assert row['attempts']==1 and row['next_try']>time.time()
        assert '私人原始备注' not in str(monitor.feedback.context())
        assert monitor.quota.calls_hour(time.time())==0
        await monitor.stop()
    asyncio.run(run())


def test_human_feedback_starts_concurrently_despite_full_budget_and_busy_workers(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture'),query_calls_hour=1))
        monitor.quota.record(time.time())
        requested=[]
        started=asyncio.Event()
        release=asyncio.Event()
        async def respond(request):
            items=json.loads(json.loads(request.content)['messages'][1]['content'])['items']
            requested.extend(item['source'] for item in items)
            if len(requested)==2:
                started.set()
            await release.wait()
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[
                {'source':item['source'],'reusable':True,'summary':'核对攻击对象及上下文。'} for item in items]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        await monitor.analysis_lock.acquire()
        await monitor.feedback_lock.acquire()
        try:
            case={'id':'dismissed','rule':'abuse','user_id':12345,'context':[],'evidence':[]}
            monitor.feedback.case(case,'dismissed','只是抱怨公司，不是在攻击群友')
            monitor.feedback.record({'id':'created','category':'abuse','reason':'上下文'},'核对攻击对象')
            await asyncio.wait_for(started.wait(),timeout=1)
            assert set(requested)=={'case:dismissed','record:created'}
            assert monitor.quota.calls_hour(time.time())==1
            assert len(list((tmp_path/'logs'/'ds-requests'/'feedback').rglob('*.json')))==2
            # The retry worker must not duplicate requests already running.
            assert await monitor.feedback.process(monitor,sources=requested)==0
            release.set()
            await asyncio.gather(*list(monitor.manual_feedback_tasks.values()))
            assert monitor.store.db.execute('SELECT count(*) FROM feedback_jobs').fetchone()[0]==0
        finally:
            release.set()
            monitor.analysis_lock.release()
            monitor.feedback_lock.release()
            await monitor.stop()
    asyncio.run(run())


def test_new_human_feedback_supersedes_running_request_without_stale_result(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        started=asyncio.Event()
        release=asyncio.Event()
        notes=[]
        async def respond(request):
            item=json.loads(json.loads(request.content)['messages'][1]['content'])['items'][0]
            notes.append(item['note'])
            started.set()
            await release.wait()
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':[
                {'source':item['source'],'reusable':True,'summary':item['note']}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        monitor.feedback.record({'id':'same','category':'abuse'},'旧判断')
        await asyncio.wait_for(started.wait(),timeout=1)
        old=monitor.manual_feedback_tasks['record:same']
        started.clear()
        monitor.feedback.record({'id':'same','category':'abuse'},'新的判断边界')
        await asyncio.wait_for(started.wait(),timeout=1)
        release.set()
        await asyncio.gather(old,*list(monitor.manual_feedback_tasks.values()),return_exceptions=True)
        assert notes==['旧判断','新的判断边界']
        assert next(p for p in monitor.feedback.points() if p['source']=='record:same')['summary']=='新的判断边界'
        assert monitor.quota.calls_hour(time.time())==0
        await monitor.stop()
    asyncio.run(run())


def test_feedback_bounded_context_and_editable_authenticated_api(tmp_path,monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    monitor=Monitor(settings(tmp_path))
    feedback=monitor.feedback
    for i in range(180):
        feedback.put(f'case:{i}','abuse','clear',f'例{i}：'+'边界'*240)
    assert len(feedback.points())<=MAX_EXAMPLES
    feedback.edit('','abuse','clear','用户明确调整的优先判断')
    context=feedback.context(['abuse'])
    assert context[0]['summary']=='用户明确调整的优先判断'
    assert len(context)<=12 and len(json.dumps(context,ensure_ascii=False))<=MAX_CONTEXT
    app=create_app(monitor.cfg,monitor)
    async def start(): pass
    async def stop(): monitor.store.db.close()
    monitor.start,monitor.stop=start,stop
    with TestClient(app) as client:
        assert client.get('/api/settings/feedback').status_code==401
        assert client.post('/api/auth/login',json={'token':'中文测试密码'}).status_code==200
        page=client.get('/')
        client.headers['x-csrf-token']=re.search(r'name="csrf-token" content="([^"]+)',page.text)[1]
        assert client.get('/api/settings/feedback').status_code==200
        result=client.post('/api/settings/feedback',json={'rule':'political','verdict':'violation','summary':'人工补充的判断边界'})
        assert result.status_code==200
        source=result.json()['source']
        result=client.post('/api/settings/feedback',json={'source':source,'rule':'political','verdict':'clear','summary':'调整后的边界'})
        assert next(p for p in result.json()['points'] if p['source']==source)['summary']=='调整后的边界'
        assert client.post('/api/settings/feedback',json={'source':source,'verdict':'bad','summary':'无效'}).status_code==400
        result=client.post('/api/settings/feedback/delete',json={'source':source})
        assert all(p['source']!=source for p in result.json()['points'])


def test_push_recipients_preserve_blanks_and_fail_atomically(tmp_path,monkeypatch):
    cfg=settings(tmp_path,pushplus_recipients=[PushRecipient(id='first',token=SecretStr('first-test-token'))])
    path=tmp_path/'.env';path.write_text('OTHER_SECRET=keep-me\nGROUP_EVIDENCE_TOKENS=中文测试密码\n',encoding='utf-8')
    old=push_recipients(cfg)[0]
    save_push_recipients(cfg,[PushRecipient(id=old.id,name='甲'),PushRecipient(name='乙',token='second-test-token')])
    saved=push_recipients(cfg)
    assert [r.token.get_secret_value() for r in saved]==['first-test-token','second-test-token']
    config=tmp_path/'settings.json';config.write_text(json.dumps({'local_env':str(path),'lan_env':str(tmp_path/'absent')}),encoding='utf-8')
    restored=load_settings(config)
    assert [r.name for r in restored.pushplus_recipients]==['甲','乙']
    assert 'OTHER_SECRET=keep-me' in path.read_text(encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(ValueError):
        save_push_recipients(cfg,[PushRecipient(token='second-test-token'),PushRecipient(token='second-test-token')])
    def deny(*args): raise PermissionError('fixture')
    with monkeypatch.context() as patch:
        patch.setattr('group_watch.settings.os.replace',deny)
        with pytest.raises(PermissionError): save_push_recipients(cfg,[])
    assert path.read_bytes()==before and len(push_recipients(cfg))==2
    save_push_recipients(cfg,[])
    assert push_recipients(load_settings(config))==[]


def test_push_fanout_retries_only_failed_recipient_after_restart(tmp_path):
    async def run():
        cfg=settings(tmp_path,pushplus_recipients=[PushRecipient(id='a',token='test-recipient-a'),PushRecipient(id='b',token='test-recipient-b')])
        monitor=Monitor(cfg);now=time.time()
        monitor.ingest(dict(post_type='message',message_type='group',group_id=100000001,user_id=12345,message_id='1',time=now,message='123456',sender={'nickname':'fixture'}),now)
        case=case_rows(monitor.store)[0];monitor.store.update(case['id'],state='violation',confidence=.99)
        sent=[]
        def respond(request):
            token=json.loads(request.content)['token'];sent.append(token)
            code=500 if token=='test-recipient-b' and sent.count(token)==1 else 200
            return httpx.Response(200,json={'code':code})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        await monitor.notify_once()
        assert case_rows(monitor.store)[0]['notified']==0
        assert 'test-recipient-a' not in str([dict(r) for r in monitor.store.db.execute('SELECT * FROM broadcast_delivery')])
        await monitor.stop()
        monitor=Monitor(cfg);monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        monitor.store.update(case['id'],notify_next=0)
        await monitor.notify_once()
        assert sent==['test-recipient-a','test-recipient-b','test-recipient-b']
        assert case_rows(monitor.store)[0]['notified']==1
        await monitor.stop()
    asyncio.run(run())


def test_repeated_registration_lookup_forces_final_draft_without_tools(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture-key'),query_calls_hour=6))
        requests=[];lookups=[]
        async def tool(name,args):lookups.append((name,args));return []
        monitor.directory.tool=tool
        def respond(request):
            body=json.loads(request.content);requests.append(body)
            if len(requests)<=2:
                message={'role':'assistant','content':None,'tool_calls':[{'id':str(len(requests)),'type':'function','function':{'name':'list_groups','arguments':'{}'}}]}
                finish='tool_calls'
            else:
                assert 'tools' not in body
                message={'role':'assistant','content':json.dumps({'people':[{'member':'截图发送者','reason':'截图中的政治言论，账号待确认'}]})};finish='stop'
            return httpx.Response(200,json={'choices':[{'message':message,'finish_reason':finish}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        image={'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}
        result=await analyze(monitor,[image])
        assert len(requests)==3 and len(lookups)==1
        assert result['people'][0]['member_id']=='' and result['people'][0]['reason']==''
        assert result['people'][0]['explanation']=='截图中的政治言论，账号待确认'
        assert 'human_feedback' in requests[0]['messages'][1]['content'][0]['text']
        await monitor.stop()
    asyncio.run(run())
