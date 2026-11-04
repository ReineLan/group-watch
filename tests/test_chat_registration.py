def case_rows(store):
    return list(store.window_state.candidates.values())+store.cases()

import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from group_watch.monitoring.chat import AssetCache
from group_watch.monitoring.chat import ChatPresentation
from group_watch.monitoring.chat import safe_image_url
from group_watch.monitoring.chat import segments
from group_watch.sources.qq import Directory
from group_watch.evidence.registration import analyze
from group_watch.evidence.registration import image_content
from group_watch.evidence.registration import RegistrationUnavailable
from group_watch.evidence.registration import recommend_decisions
from group_watch.monitoring.service import Monitor
from group_watch.settings import BroadcastTarget
from group_watch.settings import Settings


def settings(tmp_path, **kw):
    return Settings(db_path=str(tmp_path/'watch.db'), local_env=str(tmp_path/'.env'), settings_file=str(tmp_path/'settings.json'), **kw)


def test_registration_separates_catalog_category_and_explanation(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        category='低俗、违规内容'
        def respond(request):
            body=json.loads(request.content)
            assert 'explanation' in body['messages'][0]['content']
            people=[{'reason':category,'explanation':'证据显示反复发送低俗图片','decision_detail':'建议警告'}]
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'people':people})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}],categories=[category])
        assert result['people'][0]['reason']==category
        assert result['people'][0]['explanation']=='证据显示反复发送低俗图片'
        await monitor.stop()
    asyncio.run(run())


def test_registration_preselects_catalog_penalty_and_accepts_model_fallback():
    category='广告、引流、群邀请、商业推广'
    rules=[{'id':'ad','reason':category,'steps':['移出群聊'],'notes':''}]
    candidate={'member_id':'100000009','nickname':'示例成员','group_name':'粉丝群','reason':category,'punishment':'警告','decision_detail':''}
    result=recommend_decisions({'people':[candidate]},rules,[])
    assert result['people'][0]['punishment']=='移出群聊'
    assert result['people'][0]['decision_detail']=='移出群聊'
    unknown={**candidate,'reason':'未匹配的新行为','punishment':'警告','decision_detail':'按当前证据建议警告'}
    assert recommend_decisions({'people':[unknown]},rules,[])['people'][0]['punishment']=='警告'


def test_qq_asset_origin_magic_redirect_and_reuse(tmp_path):
    async def run():
        for url in ['file:///etc/passwd','https://qq.com.evil.test/a','http://127.0.0.1/a','https://qq.com@evil.test/a','https://qlogo.cn:8080/a']:
            assert not safe_image_url(url)
        requests=[]
        def respond(req):
            requests.append(str(req.url))
            if req.url.path=='/redirect': return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
            return httpx.Response(200,content=__import__('test_resource_import_refinements').PNG if req.url.path=='/ok' else b'<html>no</html>')
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            cache=AssetCache(tmp_path,client)
            assert not await cache.image('http://127.0.0.1/a')
            assert not await cache.image('https://qlogo.cn/redirect')
            assert not await cache.image('https://qlogo.cn/html')
            first=await cache.image('https://qlogo.cn/ok')
            assert first.startswith('/api/chat-assets/')
            assert first==await cache.image('https://qlogo.cn/ok')
            assert len(requests)==3
    asyncio.run(run())


def test_chat_identity_guard_frames_replies_and_cached_portraits(tmp_path):
    async def run():
        cfg=settings(tmp_path)
        requests=[]
        class FakeQQ:
            async def call(self,action,params=None):
                requests.append(action)
                if action=='_get_friend_dress':
                    return {'target_uin':params['user_id'],'items':[{'app_id':2,'item_id':123,'preview_url':'https://qlogo.cn/unsafe-bubble'}, {'app_id':4,'item_id':44,'name':'真实挂件','preview_url':'https://qlogo.cn/frame'}]}
                if action=='get_msg':
                    return {'group_id':100000002,'user_id':12345,'message':[{'type':'text','data':{'text':'错误群的消息'}}]}
                raise AssertionError(action)
        directory=Directory(cfg,FakeQQ())
        directory.groups={100000001:'真实群名'};directory.group_counts={100000001:1954}
        directory.members={100000001:{'12345':{'name':'群昵称','level':'16','role':'nickname','title':''}}}
        from group_watch.monitoring.store import Store
        store=Store(tmp_path/'watch.db')
        presentation=ChatPresentation(SimpleNamespace(qq=directory.qq,directory=directory,store=store),tmp_path)
        assets=[]
        async def asset(url,*args,**kwargs): assets.append(url);return '/api/chat-assets/mock.png'
        presentation.assets.image=asset
        case={'id':'fixture','group_id':100000001,'context':[
            {'message_id':'1','user_id':12345,'time':1,'name':'甲','text':'留存文本'},
            {'message_id':'2','user_id':12345,'time':2,'name':'甲','text':'引用','segments':segments('[CQ:reply,id=1]你好&#91;QQ&#93;')} ]}
        with store.db:
            store.db.execute('INSERT INTO cases(id,group_id,user_id,rule,created,evidence,context,confidence) VALUES(?,?,?,?,?,?,?,?)',('fixture',100000001,12345,'abuse',1,'["1"]',json.dumps(case['context']),.95))
        result=await presentation.context(case)
        assert result['group_name']=='真实群名' and result['member_count']==1954
        assert result['messages'][0]['parts'][0]['text']=='留存文本'
        assert result['messages'][0]['pendant_name']=='真实挂件'
        assert result['messages'][0]['level']=='16'
        assert result['messages'][1]['parts'][0]['text']=='留存文本'
        assert result['messages'][1]['parts'][1]['text']=='你好[QQ]'
        assert 'https://qlogo.cn/unsafe-bubble' not in assets
        assert requests.count('_get_friend_dress')==1
        assert await presentation.context(case)==result
        assert requests.count('get_msg')==1
    asyncio.run(run())


def test_registration_tools_identity_budget_and_no_save(tmp_path):
    async def run():
        cfg=settings(tmp_path,ds_key=SecretStr('test'),query_calls_hour=2)
        monitor=Monitor(cfg)
        monitor.quota.record(__import__('time').time())
        monitor.quota.record(__import__('time').time())
        monitor.directory.groups={100000001:'真实群'}
        monitor.directory.members={100000001:{'12345':{'user_id':'12345','name':'核实昵称','nickname':'核实昵称'}}}
        seen=[]
        def respond(req):
            body=json.loads(req.content);seen.append(body)
            assert all(t['function']['name'] in ('list_groups','find_members') for t in body.get('tools',[]))
            if len(seen)==1:
                return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call1','type':'function','function':{'name':'find_members','arguments':'{"group_id":"100000001","query":"12345"}'}}]},'finish_reason':'tool_calls'}]})
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps({'people':[
                {'member_id':'12345','nickname':'模型昵称','group_id':'100000001','event_date':'2026-10-27','reason':'证据'},
                {'member_id':'99999','nickname':'未知','group_id':'100000001','event_date':'invalid','reason':'不明确','uncertainty':'旧字段应忽略'}]})},'finish_reason':'stop'}]})
        async def no_refresh(): pass
        monitor.directory.refresh=no_refresh
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        image={'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}
        result=await analyze(monitor,[image])
        assert result['people'][0]['nickname']=='核实昵称'
        assert result['people'][0]['group_name']=='真实群'
        assert result['people'][1]['member_id']=='' and result['people'][1]['group_name']=='真实群'
        assert result['people'][1]['event_date']=='' and 'uncertainty' not in result['people'][1]
        assert '+08:00' in seen[0]['messages'][1]['content'][0]['text']
        assert 'uncertainty' not in seen[0]['messages'][0]['content']
        assert all('uncertainty' not in person for person in result['people'])
        assert monitor.store.db.execute('SELECT count(*) FROM cases').fetchone()[0]==0
        await analyze(monitor,[image])
        assert len(seen)==3
        assert monitor.quota.calls_hour(__import__('time').time())==2
        assert len(list((tmp_path/'logs'/'ds-requests'/'registration').rglob('*.json')))==3
        with pytest.raises(ValueError): image_content([{'data':base64.b64encode(b'html').decode()}])
        await monitor.stop()
    asyncio.run(run())


def test_registration_keeps_screenshot_qq_and_group_during_directory_outage(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.directory.groups={100000002:'示例群聊'}
        lookups=[]
        async def unavailable(name,args):
            lookups.append((name,args))
            raise TimeoutError()
        monitor.directory.tool=unavailable
        def respond(request):
            body=json.loads(request.content)
            assert '示例群聊' in body['messages'][1]['content'][0]['text']
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'people':[
                {'nickname':'示例成员','member_id':'100000009','account_evidence':'QQ: 100000009 (ID: example_account)',
                 'group_name':'示例群聊(2915)','reason':'截图原文'},
                {'nickname':'同名','member_id':'99999','group_name':'示例群聊','reason':'无账号原文'}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        person,unknown=result['people']
        assert (person['member_id'],person['nickname'],person['group_id'],person['group_name'])==('100000009','示例成员','100000002','示例群聊')
        assert 'uncertainty' not in person
        assert person['reason']=='' and person['explanation']=='截图原文'
        assert unknown['member_id']=='' and unknown['group_id']=='100000002'
        assert lookups[0][1]['query']=='100000009'
        assert monitor.store.db.execute('SELECT count(*) FROM cases').fetchone()[0]==0
        await monitor.stop()
    asyncio.run(run())


def test_registration_queries_qq_even_when_model_skips_tools(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.directory.groups={100000002:'粉丝群'}
        class FakeQQ:
            async def call(self,action,params):
                assert action=='get_group_member_info'
                assert params=={'group_id':100000002,'user_id':100000009,'no_cache':True}
                return {'group_id':100000002,'user_id':100000009,'nickname':'在线昵称','card':'群名片'}
        monitor.directory.qq=FakeQQ()
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{
            'finish_reason':'stop','message':{'content':json.dumps({'people':[{'member_id':'100000009','nickname':'模型昵称','group_id':'100000002'}]})}}]})))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        assert result['people'][0]['nickname']=='在线昵称'
        assert result['people'][0]['member_id']=='100000009'
        await monitor.stop()
    asyncio.run(run())


@pytest.mark.parametrize('qq_name,expected',[('', ''),('接口昵称','接口昵称'),('   ','   ')])
def test_registration_keeps_ds_name_when_departed_members_qq_name_is_empty(tmp_path,qq_name,expected):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.directory.groups={100000002:'示例群聊'}
        monitor.directory.members={100000002:{'100000009':{'user_id':'100000009','name':qq_name,'nickname':qq_name}}}
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{
            'finish_reason':'stop','message':{'content':json.dumps({'people':[{'member_id':'100000009','nickname':'示例成员','group_id':'100000002'}]})}}]})))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        assert result['people'][0]['nickname']==expected
        assert result['people'][0]['member_id']=='100000009'
        await monitor.stop()
    asyncio.run(run())


def test_directory_restores_names_and_serves_cached_nicknames_without_refresh(tmp_path):
    async def run():
        cfg=settings(tmp_path)
        monitor=Monitor(cfg)
        with monitor.store.db:
            monitor.store.db.execute('UPDATE registered_groups SET name=? WHERE group_id=?',('已确认群名',100000002))
        await monitor.stop()
        monitor=Monitor(cfg)
        assert monitor.directory.name(100000002)=='已确认群名'
        monitor.directory.members={100000002:{'12345':{'user_id':'12345','name':'名片','nickname':'真实昵称'}}}
        async def unavailable(): raise AssertionError('缓存查询不应刷新所有群成员')
        monitor.directory.refresh=unavailable
        result=await monitor.directory.tool('find_members',{'group_id':'100000002','query':'真实昵称'})
        assert result[0]['user_id']=='12345'
        await monitor.stop()
    asyncio.run(run())


def test_registration_independent_lookups_run_together_and_receive_categories(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        all_started=asyncio.Event()
        queries=[]
        async def lookup(name,args):
            queries.append(args['query'])
            if len(queries)==2: all_started.set()
            await asyncio.wait_for(all_started.wait(),.5)
            return []
        monitor.directory.tool=lookup
        rounds=[]
        def respond(request):
            body=json.loads(request.content);rounds.append(body)
            context=json.loads(body['messages'][1]['content'][0]['text'])
            assert context['allowed_reasons']==['广告、引流、群邀请、商业推广']
            assert context['handling_rules']==[{'reason':'广告、引流、群邀请、商业推广','steps':['移出群聊'],'notes':'按证据处理'}]
            if len(rounds)==1:
                message={'content':None,'tool_calls':[{'id':str(i),'type':'function','function':{'name':'find_members','arguments':json.dumps({'group_id':'100000002','query':query})}} for i,query in enumerate(('12345','67890'))]}
                finish='tool_calls'
            else:
                assert len([x for x in body['messages'] if x.get('role')=='tool'])==2
                message={'content':json.dumps({'people':[{'nickname':'截图昵称','reason':'广告引流'}]})}
                finish='stop'
            return httpx.Response(200,json={'choices':[{'finish_reason':finish,'message':message}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}],categories=['广告、引流、群邀请、商业推广'],rules=[{'reason':'广告、引流、群邀请、商业推广','steps':['移出群聊'],'notes':'按证据处理'}])
        assert queries==['12345','67890']
        assert result['people'][0]['reason']==''
        assert result['people'][0]['explanation']=='广告引流'
        await monitor.stop()
    asyncio.run(run())


def test_registration_resolves_only_unique_exact_known_member(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        monitor.directory.groups={100000001:'真实群'}
        monitor.directory.members={100000001:{'12345':{'name':'群名片','nickname':'烟锅猫'},'99999':{'name':'同名'},'88888':{'name':'同名'}}}
        def respond(request):
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'people':[
                {'nickname':'烟锅猫','group_name':'真实群'}, {'nickname':'同名','group_id':'100000001'},
                {'nickname':'群名片','member_id':'77777','group_id':'100000001'}, {'nickname':'群名片','group_id':'1'}]})}}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        assert result['people'][0]['member_id']=='12345'
        assert result['people'][0]['group_id']=='100000001'
        assert result['people'][0]['nickname']=='烟锅猫'
        assert all(row['member_id']=='' for row in result['people'][1:])
        await monitor.stop()
    asyncio.run(run())


@pytest.mark.parametrize('failure', [TimeoutError, OSError, ValueError])
def test_registration_directory_outage_still_returns_unverified_draft(tmp_path, failure):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('fixture')))
        requests=[]
        async def unavailable(name,args):
            raise failure('private lookup details must not escape')
        monitor.directory.tool=unavailable
        def respond(request):
            body=json.loads(request.content);requests.append(body)
            if len(requests)==1:
                message={'role':'assistant','content':None,'tool_calls':[{'id':'lookup','type':'function','function':{'name':'find_members','arguments':'{"group_id":"100000001","query":"12345"}'}}]}
                finish='tool_calls'
            else:
                assert 'tools' not in body
                tool=next(x for x in body['messages'] if x['role']=='tool')
                assert '暂不可用' in tool['content'] and 'private lookup' not in tool['content']
                message={'content':json.dumps({'people':[{'nickname':'截图发送者','member_id':'12345','group_id':'100000001','reason':'截图证据'}]})}
                finish='stop'
            return httpx.Response(200,json={'choices':[{'message':message,'finish_reason':finish}]})
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        result=await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        assert len(requests)==2
        person=result['people'][0]
        assert person['reason']=='' and person['explanation']=='截图证据'
        assert person['member_id']=='' and person['group_id']==''
        assert 'uncertainty' not in person and monitor.store.db.execute('SELECT count(*) FROM cases').fetchone()[0]==0
        await monitor.stop()
    asyncio.run(run())


@pytest.mark.parametrize(('status','text'), [(401,'认证失败'),(429,'过于频繁'),(503,'HTTP 503')])
def test_registration_ds_failure_has_safe_specific_message(tmp_path,status,text):
    async def run():
        monitor=Monitor(settings(tmp_path,ds_key=SecretStr('private-key')))
        monitor.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(status,json={'error':'private upstream details'})))
        with pytest.raises(RegistrationUnavailable) as error:
            await analyze(monitor,[{'data':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}])
        assert text in str(error.value) and '保留' in str(error.value)
        assert 'private' not in str(error.value)
        await monitor.stop()
    asyncio.run(run())


def test_broadcast_threshold_and_persistent_uncertain_delivery_dedupe(tmp_path):
    async def run():
        monitor=Monitor(settings(tmp_path,broadcast_targets=[BroadcastTarget(kind='group',id='100000010',name='示例广播目标')]))
        monitor.ingest({'post_type':'message','message_type':'group','group_id':100000001,'user_id':12345,'message_id':'1','time':__import__('time').time(),'message':'123456','sender':{'nickname':'甲'}})
        case=case_rows(monitor.store)[0]
        monitor.store.update(case['id'],state='violation',confidence=.94)
        sent=[]
        async def send(action,params): sent.append((action,params));raise TimeoutError()
        monitor.qq.call=send
        await monitor.broadcast_once();assert not sent
        monitor.store.update(case['id'],confidence=.99)
        await monitor.broadcast_once();await monitor.broadcast_once()
        assert len(sent)==1 and sent[0][0]=='send_group_msg'
        assert sent[0][1]['group_id']==100000010
        assert monitor.store.db.execute('SELECT status FROM broadcast_delivery').fetchone()[0]=='unknown'
        await monitor.stop()
    asyncio.run(run())
