"""Deletion is serialized with rendering and protects shared media references."""
import asyncio,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from group_watch.monitoring.chat import ChatPresentation
from group_watch.monitoring.feedback import Feedback
from group_watch.monitoring.store import Store
from test_resource_import_refinements import saved_case

def test_delete_api_requires_auth_csrf_and_handled_case(tmp_path,monkeypatch):
    import re
    from fastapi.testclient import TestClient
    from group_watch.app import create_app
    from group_watch.monitoring.service import Monitor
    from test_moderation_feedback import settings
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    monitor=Monitor(settings(tmp_path))
    row=saved_case(monitor.store)
    monitor.feedback.put('case:'+row['id'],'abuse','clear','保留人工反馈')
    async def start(): pass
    async def stop(): monitor.store.db.close()
    monitor.start,monitor.stop=start,stop
    with TestClient(create_app(monitor.cfg,monitor)) as client:
        url='/api/cases/'+row['id']
        assert client.delete(url).status_code==401
        assert client.post('/api/auth/login',json={'token':'中文测试密码'}).status_code==200
        assert client.delete(url).status_code==403
        client.headers['x-csrf-token']=re.search(r'name="csrf-token" content="([^"]+)',client.get('/').text)[1]
        assert client.delete(url).status_code==409
        monitor.store.update(row['id'],resolution='dismissed',decision_at=time.time())
        assert client.delete(url).json()=={'ok':True}
        assert not monitor.store.cases()
        assert monitor.feedback.points()[0]['summary']=='保留人工反馈'
        assert client.delete(url).status_code==404

def test_registered_api_deletes_case_only_after_records_exist(tmp_path,monkeypatch):
    import re
    from fastapi.testclient import TestClient
    from group_watch.app import create_app
    from group_watch.monitoring.service import Monitor
    from test_moderation_feedback import settings
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    monitor=Monitor(settings(tmp_path));row=saved_case(monitor.store)
    async def start(): pass
    async def stop(): monitor.store.db.close()
    monitor.start,monitor.stop=start,stop
    with TestClient(create_app(monitor.cfg,monitor)) as client:
        url='/api/cases/'+row['id']+'/registered'
        assert client.post(url,json={'record_ids':['missing']}).status_code==401
        assert client.post('/api/auth/login',json={'token':'中文测试密码'}).status_code==200
        client.headers['x-csrf-token']=re.search(r'name="csrf-token" content="([^"]+)',client.get('/').text)[1]
        assert client.post(url,json={'record_ids':['missing']}).status_code==409
        assert monitor.store.cases('id=?',(row['id'],))
        body={'member_id':'12345','group_id':100000001,'nickname':None,'card':None,
              'event_date':'2026-01-01','reason':'测试','punishment':'警告','penalty_text':'警告',
              'operator':'','notes':'','occurrence':'','images':[]}
        record=client.post('/evidence/api/records',json=body).json()
        assert record['ids']
        assert client.post(url,json={'record_ids':record['ids']}).json()=={'ok':True,'deleted':True}
        assert not monitor.store.cases('id=?',(row['id'],))
        assert client.post(url,json={'record_ids':record['ids']}).json()=={'ok':True,'deleted':False}


def test_delete_checks_handled_state_after_waiting_for_lock(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');row=saved_case(store)
        store.update(row['id'],resolution='dismissed')
        chat=ChatPresentation(SimpleNamespace(store=store),tmp_path/'assets')
        await chat.lock.acquire()
        deleting=asyncio.create_task(chat.discard_case(row['id'],require_handled=True))
        await asyncio.sleep(0)
        store.update(row['id'],resolution='')
        chat.lock.release()
        with pytest.raises(ValueError,match='请先处理'): await deleting
        assert store.cases();store.db.close()
    asyncio.run(run())
def resource(chat,char):
    chat.assets.root.mkdir(exist_ok=True);path=chat.assets.root/(char*64+'.webp');path.write_bytes(b'fixture')
    return '/api/chat-assets/'+path.name,path
def attach(store,case,url,position):
    with store.db:store.db.execute('INSERT INTO case_resources VALUES(?,?,?,?,1,?,?)',(case['id'],position,'image','https://gchat.qpic.cn/'+position,str(time.time()),url))
def test_discard_private_assets_preserves_shared_assets_and_feedback(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');chat=ChatPresentation(SimpleNamespace(store=store),tmp_path/'assets')
        a,b=saved_case(store,'a'),saved_case(store,'b');private,p=resource(chat,'a');shared,q=resource(chat,'b')
        attach(store,a,private,'private');attach(store,a,shared,'shared');attach(store,b,shared,'shared')
        feedback=Feedback(store);feedback.put('case:'+a['id'],'abuse','clear','原摘要');feedback.edit('case:'+a['id'],'abuse','clear','人工规则')
        assert await chat.discard_case(a['id'])
        assert not p.exists() and q.exists() and not store.cases('id=?',(a['id'],))
        assert feedback.points()[0]['summary']=='人工规则'
        assert await chat.discard_case(b['id']) and not q.exists()
        assert not await chat.discard_case(a['id']);store.db.close()
    asyncio.run(run())
def test_discard_waits_for_render_and_stale_context_cannot_download_again(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');row=saved_case(store);entered,release=asyncio.Event(),asyncio.Event()
        async def presentation(case,assets):entered.set();await release.wait();return {'messages':[]}
        chat=ChatPresentation(SimpleNamespace(store=store,directory=SimpleNamespace(presentation=presentation)),tmp_path/'assets')
        rendering=asyncio.create_task(chat.context(row));await entered.wait()
        deleting=asyncio.create_task(chat.discard_case(row['id']));await asyncio.sleep(0);assert not deleting.done()
        release.set();await rendering;assert await deleting
        with pytest.raises(LookupError):await chat.context(row,refresh=True)
        assert store.db.execute('SELECT count(*) FROM case_resources').fetchone()[0]==0;store.db.close()
    asyncio.run(run())
def test_dismissed_case_and_resources_survive_restart(tmp_path):
    store=Store(tmp_path/'watch.db');chat=ChatPresentation(SimpleNamespace(store=store),tmp_path/'assets');row=saved_case(store)
    url,path=resource(chat,'d');attach(store,row,url,'image');store.update(row['id'],resolution='dismissed',note='人工判断',decision_at=time.time())
    ChatPresentation(SimpleNamespace(store=store),chat.assets.root)
    assert store.cases()[0]['resolution']=='dismissed' and path.exists();store.db.close()
def test_busy_file_cleanup_is_retried_in_memory(tmp_path,monkeypatch):
    async def run():
        store=Store(tmp_path/'watch.db');chat=ChatPresentation(SimpleNamespace(store=store),tmp_path/'assets');row=saved_case(store)
        url,path=resource(chat,'e');attach(store,row,url,'image');unlink=Path.unlink
        def busy(file,*args,**kwargs):
            if file==path:raise PermissionError('busy')
            return unlink(file,*args,**kwargs)
        monkeypatch.setattr(Path,'unlink',busy);assert await chat.discard_case(row['id'])
        assert not store.cases() and path.exists() and path.name in chat.cleanup
        monkeypatch.setattr(Path,'unlink',unlink);await chat.prefetch_once()
        assert not path.exists() and not chat.cleanup;store.db.close()
    asyncio.run(run())
def test_late_download_after_delete_cannot_recreate_resource(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');chat=ChatPresentation(SimpleNamespace(store=store),tmp_path/'assets');row=saved_case(store)
        entered,release=asyncio.Event(),asyncio.Event()
        async def download(source):entered.set();await release.wait();return resource(chat,'f')[0]
        chat.assets.raw.image=download;token=chat.assets.active.set(row['id'])
        task=asyncio.create_task(chat.assets.image('https://gchat.qpic.cn/image'));chat.assets.active.reset(token)
        await entered.wait();assert await chat.discard_case(row['id']);release.set()
        assert await task=='' and not list(chat.assets.root.iterdir())
        assert store.db.execute('SELECT count(*) FROM case_resources').fetchone()[0]==0;store.db.close()
    asyncio.run(run())
