"""Current resource persistence, restart and one-shot profile contracts."""
import asyncio,base64,time,json
from types import SimpleNamespace
import httpx,pytest
from group_watch.monitoring.chat import ChatPresentation
from group_watch.evidence.profiles import download_avatar
from group_watch.evidence.store import RecordStore
from group_watch.monitoring.store import Store
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGZkAAAAASUVORK5CYII=')
def saved_case(store,mid='1'):
    msg=dict(group_id=100000001,user_id=12345,message_id=mid,time=time.time(),name='成员',text='消息',segments=[{'type':'image','data':{'url':'https://gchat.qpic.cn/evidence'}}])
    store.window_state.candidate(msg,'abuse',[mid],[msg],0,time.time());key=next(reversed(store.window_state.candidates))
    store.update(key,state='violation',confidence=.95,reason='真实证据')
    return store.cases('id=?',(key,))[0]
def monitor(store):
    class QQ:
        async def call(self,*args):return {}
    return SimpleNamespace(store=store,qq=QQ(),directory=SimpleNamespace(members={},group_counts={},name=lambda g:'群'))
def test_invalid_primary_uses_160_fallback(monkeypatch):
    calls=[]
    def download(url):calls.append(url);return b'bad' if len(calls)==1 else PNG
    monkeypatch.setattr('group_watch.evidence.profiles.download',download)
    assert download_avatar('12345')==(PNG,'.png') and 'spec=160' in calls[1]
def test_pending_resources_survive_restart_and_missing_files_are_reloaded(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');case=saved_case(store);calls=[]
        def respond(req):calls.append(req);return httpx.Response(200,content=PNG)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            chat=ChatPresentation(monitor(store),tmp_path/'assets');chat.assets.raw.client=client
            await chat.prefetch_once();first=len(calls);assert first==2
            rows=list(store.db.execute('SELECT * FROM case_resources'));assert all(r['status']==1 and r['at'] and r['url'].endswith('.webp') for r in rows)
            store.db.close();store=Store(tmp_path/'watch.db')
            restarted=ChatPresentation(monitor(store),tmp_path/'assets');restarted.assets.raw.client=client
            await restarted.prefetch_once();assert len(calls)==first
            (restarted.assets.root/rows[0]['url'].split('/')[-1]).unlink()
            restarted=ChatPresentation(monitor(store),tmp_path/'assets');restarted.assets.raw.client=client
            await restarted.prefetch_once();assert len(calls)==first+1
        store.db.close()
    asyncio.run(run())
def test_profile_edit_generation_and_deleted_record_reject_late_writes(tmp_path,monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    store=RecordStore(tmp_path/'archive');store.initialize(store.data)
    body=dict(member_id='12345',group_id=100000001,nickname=None,card=None,event_date='2026-10-29',reason='证据',punishment='警告')
    key=store.save_records(body)['id'];cache=store.get_profiles();old=store.get_records()[0]
    cache.generations[key]=1
    store.save_records(body|dict(id=key,nickname='人工昵称'))
    cache.complete(old,1,'nickname',dict(nickname='过期昵称',nickname_status=1))
    assert store.get_records()[0]['nickname']=='人工昵称'
    generation=cache.generations[key];store.delete_record(key)
    cache.complete(old,generation,'avatar',dict(avatar_status=1),PNG)
    assert store.get_records()==[] and list(cache.avatars.iterdir())==[]
    store.close()
def test_resume_pending_only_and_failed_resources_need_explicit_retry(tmp_path,monkeypatch):
    monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','0')
    store=RecordStore(tmp_path/'archive');store.initialize(store.data)
    key=store.save_records(dict(member_id='12345',group_id=100000001,event_date='2026-10-29',reason='证据',punishment='警告'))['id']
    store.close();monkeypatch.setenv('GROUP_EVIDENCE_PROFILES','1')
    calls=[]
    def remote(url,*args):calls.append(url);raise OSError('offline')
    monkeypatch.setattr('group_watch.evidence.profiles.download',remote)
    store.initialize(store.data)
    for future in list(store.get_profiles().pending.values()):future.result(timeout=5)
    row=store.get_records()[0];assert (row['nickname_status'],row['avatar_status'])==(2,2)
    count=len(calls);store.close();store.initialize(store.data);assert len(calls)==count
    store.get_profiles().retry(key)
    for future in list(store.get_profiles().pending.values()):future.result(timeout=5)
    assert len(calls)>count;store.close()


def test_webp_keeps_canvas_alpha_animation_and_durations():
    from io import BytesIO
    from PIL import Image
    from group_watch.utils.images import webp
    a=Image.new('RGBA',(8,8),(255,0,0,0));a.putpixel((2,2),(255,0,0,255))
    b=a.copy();b.putpixel((3,3),(0,255,0,255))
    stream=BytesIO();a.save(stream,format='PNG',save_all=True,append_images=[b],duration=[90,150],loop=2)
    with Image.open(BytesIO(webp(stream.getvalue()))) as result:
        assert result.size==(8,8) and result.n_frames==2 and result.info['loop']==2
        assert result.convert('RGBA').getpixel((0,0))[3]==0
        durations=[]
        for index in range(result.n_frames):
            result.seek(index);result.load();durations.append(result.info['duration'])
        assert durations==[90,150]


def test_prefetch_resumes_pending_resource_independently_of_prepared_context(tmp_path):
    async def run():
        store=Store(tmp_path/'watch.db');case=saved_case(store)
        chat=ChatPresentation(monitor(store),tmp_path/'assets');chat.prepared.add(case['id'])
        source='https://q1.qlogo.cn/g?b=qq&nk=12345&s=100'
        with store.db:store.db.execute('INSERT INTO case_resources VALUES(?,?,?,?,0,NULL,NULL)',(case['id'],'user:12345:avatar','avatar',source))
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=PNG))) as client:
            chat.assets.raw.client=client;await chat.prefetch_once()
        row=store.db.execute('SELECT * FROM case_resources').fetchone()
        assert row['status']==1 and row['at'] and (chat.assets.root/row['url'].split('/')[-1]).exists()
        store.db.close()
    asyncio.run(run())
