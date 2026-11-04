"""Download and retain QQ presentation resources for saved review cases."""
from group_watch.utils.files import atomic_write
from group_watch.utils.images import webp
import asyncio
import hashlib
import html
import re
import time
from pathlib import Path
from contextvars import ContextVar
from urllib.parse import urlsplit

import httpx
from websockets.exceptions import WebSocketException


def segments(value):
    if isinstance(value, list):
        return [x for x in value[:200] if isinstance(x, dict) and isinstance(x.get('data'), dict)]
    if not isinstance(value, str):
        return []
    result, pos = [], 0
    for match in re.finditer(r'\[CQ:([^\]]*)\]', value):
        if match.start()>pos:
            result.append({'type':'text','data':{'text':html.unescape(value[pos:match.start()])}})
        fields=match[1].split(',')
        result.append({'type':fields[0], 'data':{k:html.unescape(v) for k,v in (x.split('=',1) for x in fields[1:] if '=' in x)}})
        pos=match.end()
    if pos<len(value):
        result.append({'type':'text','data':{'text':html.unescape(value[pos:])}})
    return result[:200]


def safe_image_url(url):
    if not isinstance(url, str) or len(url)>8192:
        return False
    try:
        p=urlsplit(url)
        host=(p.hostname or '').lower()
        return p.scheme in ('http','https') and not p.username and not p.password and p.port in (None,80,443) and any(host==d or host.endswith('.'+d) for d in ('qq.com','qq.com.cn','qpic.cn','qlogo.cn','gtimg.cn','gtimg.com','hdslb.com','biliimg.com'))
    except ValueError:
        return False


def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'png'
    if data.startswith(b'\xff\xd8\xff'): return 'jpg'
    if data.startswith((b'GIF87a',b'GIF89a')): return 'gif'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP': return 'webp'
    return ''


class AssetCache:
    def __init__(self, root, client=None, retained=None):
        self.root=Path(root)
        self.client=client
        self.locks={}
        self.failed={}
        self.cleaned=0
        self.retained=retained or (lambda: set())

    async def image(self, url):
        if not safe_image_url(url): return ''
        key=hashlib.sha256(url.encode()).hexdigest()
        lock=self.locks.setdefault(key,asyncio.Lock())
        try:
            async with lock:
                self.root.mkdir(parents=True,exist_ok=True)
                self.prune()
                path=self.root/(key+'.webp')
                if path.is_file(): return '/api/chat-assets/'+path.name
                if time.time()-self.failed.get(key,0)<60: return ''
                try:
                    if self.client is None:
                        async with httpx.AsyncClient(timeout=12,follow_redirects=False,trust_env=False) as client:
                            return await self.download(client,url,key)
                    return await self.download(self.client,url,key)
                except (httpx.HTTPError,ValueError,OSError):
                    self.failed[key]=time.time()
                    if len(self.failed)>1000: self.failed.clear()
                    return ''
        finally:
            # Keep bounded synchronization objects; all current waiters share this lock.
            if not lock.locked() and not getattr(lock,'_waiters',None): self.locks.pop(key,None)

    async def download(self,client,url,key):
        async with client.stream('GET',url,follow_redirects=False) as response:
            response.raise_for_status()
            if int(response.headers.get('content-length','0'))>8*1024*1024: raise ValueError('图片过大')
            data=bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data)>8*1024*1024: raise ValueError('图片过大')
        data=await asyncio.to_thread(webp,bytes(data))
        path=self.root/(key+'.webp')
        atomic_write(path,data)
        return '/api/chat-assets/'+path.name

    def prune(self):
        now=time.time()
        if now-self.cleaned<3600: return
        self.cleaned=now
        retained=self.retained()
        files=[]
        for path in self.root.iterdir():
            if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|gif|webp|part)',path.name) or not path.is_file(): continue
            if path.name in retained: continue
            stat=path.stat()
            if now-stat.st_mtime>7*86400:
                path.unlink(missing_ok=True)
            else: files.append((stat.st_mtime,stat.st_size,path))
        total=sum(x[1] for x in files)
        for _,size,path in sorted(files):
            if total<=256*1024*1024: break
            path.unlink(missing_ok=True);total-=size


class CaseAssets:
    def __init__(self, presentation, root):
        self.presentation=presentation
        self.raw=AssetCache(root,retained=presentation.retained_assets)
        self.root=self.raw.root
        self.active=ContextVar('case-resource',default=None)
        self.inflight={}

    async def image(self,url,position=None,kind='image'):
        case=self.active.get()
        if isinstance(url,str) and re.fullmatch(r'/api/chat-assets/[a-f0-9]{64}\.webp',url):
            row=self.presentation.db.execute('SELECT 1 FROM case_resources WHERE case_id=? AND url=? AND status=1',(case,url)).fetchone()
            return url if row and (self.root/Path(url).name).is_file() else ''
        if not safe_image_url(url): return ''
        if case is None: return await self.raw.image(url)
        key=position or 'source:'+hashlib.sha256(url.encode()).hexdigest()
        db=self.presentation.db
        if not db.execute('SELECT 1 FROM cases WHERE id=?',(case,)).fetchone(): return ''
        row=db.execute('SELECT * FROM case_resources WHERE case_id=? AND position=?',(case,key)).fetchone()
        if row and row['source']==url and row['status']!=0:
            if row['status']==2 or row['url'] and (self.root/Path(row['url']).name).is_file():
                return row['url'] or ''
        with db:
            db.execute('INSERT INTO case_resources VALUES(?,?,?,?,0,NULL,NULL) ON CONFLICT(case_id,position) DO UPDATE SET source=excluded.source,status=0,at=NULL,url=NULL',
                       (case,key,kind,url))
        taskkey=(case,key,url)
        if taskkey not in self.inflight:
            task=asyncio.create_task(self.resolve(case,key,url))
            self.inflight[taskkey]=task
            task.add_done_callback(lambda done:self.inflight.pop(taskkey,None))
        return await asyncio.shield(self.inflight[taskkey])

    async def resolve(self,case,key,source):
        result=''
        for attempt in range(3):
            result=await self.raw.image(source)
            if result: break
            if attempt<2:
                self.raw.failed.pop(hashlib.sha256(source.encode()).hexdigest(),None)
                await asyncio.sleep(.25*(attempt+1))
        db=self.presentation.db
        with db:
            changed=db.execute('UPDATE case_resources SET status=?,at=?,url=? WHERE case_id=? AND position=? AND source=? AND EXISTS (SELECT 1 FROM cases WHERE id=?)',
                (1 if result else 2,time.time(),result or None,case,key,source,case)).rowcount
        if not changed and result:
            self.presentation.remove_unreferenced([Path(result).name])
        return result if changed else ''


class ChatPresentation:
    def __init__(self,monitor,root):
        self.monitor=monitor
        monitor.chat=self
        self.db=monitor.store.db
        self.cache={}
        self.dresses={}
        self.prepared=set()
        self.cleanup=set()
        self.lock=asyncio.Lock()
        self.assets=CaseAssets(self,root)

    def retained_assets(self):
        retained={Path(row[0]).name for row in self.db.execute('SELECT url FROM case_resources WHERE status=1 AND url IS NOT NULL')}
        retained.update(hashlib.sha256(row[0].encode()).hexdigest()+'.webp' for row in self.db.execute('SELECT source FROM case_resources WHERE status=0'))
        return retained

    def remove_unreferenced(self,names):
        retained=self.retained_assets()
        for name in names:
            if name not in retained and re.fullmatch(r'[a-f0-9]{64}\.webp',name):
                try:
                    (self.assets.root/name).unlink(missing_ok=True)
                    self.cleanup.discard(name)
                except OSError:
                    self.cleanup.add(name)

    def stored(self,key):
        cached=self.cache.get(key)
        return cached[1] if cached and time.time()-cached[0]<300 else None

    async def discard_case(self,key,require_handled=False):
        async with self.lock:
            row=self.db.execute('SELECT resolution FROM cases WHERE id=?',(key,)).fetchone()
            if row is None: return False
            if require_handled and not row['resolution']:
                raise ValueError('请先处理线索再删除')
            names=[Path(r[0]).name for r in self.db.execute('SELECT url FROM case_resources WHERE case_id=? AND url IS NOT NULL',(key,))]
            with self.db:
                for table in ('case_resources','broadcast_delivery'):
                    self.db.execute(f'DELETE FROM {table} WHERE case_id=?',(key,))
                self.db.execute('DELETE FROM cases WHERE id=?',(key,))
            self.remove_unreferenced(names)
            self.cache.pop(key,None)
            self.prepared.discard(key)
            return True

    async def prefetch_once(self,limit=3):
        self.remove_unreferenced(list(self.cleanup))
        pending=list(self.db.execute('SELECT case_id,position,kind,source FROM case_resources WHERE status=0 LIMIT 12'))
        async def resume(row):
            token=self.assets.active.set(row['case_id'])
            try: await self.assets.image(row['source'],row['position'],row['kind'])
            finally: self.assets.active.reset(token)
        if pending: await asyncio.gather(*(resume(row) for row in pending))
        cases=self.monitor.store.cases('1=1',(),10000)
        ids={c['id'] for c in cases}
        self.prepared.intersection_update(ids)
        for case in [c for c in cases if c['id'] not in self.prepared][:limit]:
            try:
                await self.context(case,refresh=True)
                self.prepared.add(case['id'])
            except LookupError:
                pass

    async def close(self):
        tasks=list(self.assets.inflight.values())
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)
        if self.assets.raw.client: await self.assets.raw.client.aclose()

    async def loop(self):
        await asyncio.sleep(1)
        while True:
            try:
                await self.prefetch_once()
            except Exception:
                pass  # Retries are bounded and never interrupt collection or review.
            await asyncio.sleep(10)

    async def portrait(self, user):
        cached=self.dresses.get(str(user))
        if cached and time.time()-cached[0]<900:
            result=dict(cached[1])
            result['avatar']=await self.assets.image(f'https://q1.qlogo.cn/g?b=qq&nk={user}&s=100',position=f'user:{user}:avatar',kind='avatar')
            if len(cached)>2 and cached[2]:
                result['pendant']=await self.assets.image(cached[2],position=f'user:{user}:pendant',kind='pendant')
            return result
        pendant_source=''
        result={'avatar':await self.assets.image(f'https://q1.qlogo.cn/g?b=qq&nk={user}&s=100',position=f'user:{user}:avatar',kind='avatar'), 'pendant':'', 'pendant_name':''}
        if not result['avatar']:
            result['avatar']=await self.assets.image(f'https://q.qlogo.cn/headimg_dl?dst_uin={user}&spec=160&img_type=jpg')
        try:
            dress=await self.monitor.qq.call('_get_friend_dress',{'user_id':int(user)})
            if str(dress.get('target_uin'))==str(user):
                # Bubble/font IDs from targetUin-only lookups are defaults, not the user's skin.
                item=next((x for x in dress.get('items',[]) if x.get('app_id')==4 and int(x.get('item_id') or 0)>0),None)
                if item:
                    pendant_source=item.get('preview_url','')
                    result['pendant']=await self.assets.image(pendant_source,position=f'user:{user}:pendant',kind='pendant')
                    result['pendant_name']=str(item.get('name') or '')[:100]
        except (ValueError,TypeError,AttributeError,TimeoutError,OSError,WebSocketException): pass
        if len(self.dresses)>=200: self.dresses.pop(next(iter(self.dresses)))
        self.dresses[str(user)]=(time.time(),result,pendant_source)
        return result

    async def context(self,case,refresh=False):
        token=self.assets.active.set(case['id'])
        try:
            # A stale QQ message must not leave the whole review waiting indefinitely.
            try:
                async with asyncio.timeout(28):
                    return await self._context(case,refresh)
            except (TimeoutError, OSError, WebSocketException):
                return {'group_name':self.monitor.directory.name(case['group_id']),
                        'member_count':self.monitor.directory.group_counts.get(case['group_id'],0),
                        'messages':[{**m,'parts':[{'type':'text','text':m.get('text','')},
                            *[{'type':'unsupported','text':{'image':'图片暂不可用','face':'QQ 表情暂不可用'}.get(t,'附件暂不可用')} for t in m.get('media',[]) if t not in ('at','reply')]]} for m in case['context'][-40:]],
                        'decoration_note':'QQ 资源暂不可用，已展示留存的消息文本。'}

        finally:
            self.assets.active.reset(token)

    async def _context(self,case,refresh=False):
        key=case['id']
        async with self.lock:
            if self.db is not None and not self.db.execute('SELECT 1 FROM cases WHERE id=?',(key,)).fetchone():
                raise LookupError('线索已删除')
            if not refresh:
                saved=self.stored(key)
                if saved is not None: return saved
                if key in self.cache and time.time()-self.cache[key][0]<300: return self.cache[key][1]
            adapter = getattr(self.monitor.directory, 'presentation', None)
            adapted = await adapter(case, self.assets) if adapter else None
            if adapted is not None:
                if len(self.cache)>=20:self.cache.pop(next(iter(self.cache)))
                self.cache[key]=(time.time(),adapted)
                return adapted
            messages=[]
            source=case['context'][-40:]
            # Fetch repeated members once; bound parallel QQ and asset requests.
            semaphore=asyncio.Semaphore(4)
            async def fetch(user):
                async with semaphore: return user,await self.portrait(user)
            portraits=dict(await asyncio.gather(*(fetch(user) for user in dict.fromkeys(m['user_id'] for m in source))))
            async def render(original):
                event=None
                if 'segments' not in original:
                    try:
                        event=await self.monitor.qq.call('get_msg',{'message_id':original['message_id']})
                        if not isinstance(event,dict) or int(event.get('group_id',0))!=case['group_id'] or str(event.get('user_id'))!=str(original['user_id']): event=None
                    except (ValueError,TimeoutError,OSError,WebSocketException): pass
                raw=segments(event.get('message')) if event else original.get('segments') or [{'type':'text','data':{'text':original.get('text','')}}]
                if not event and 'segments' not in original:
                    saved=list(self.db.execute('SELECT position,kind,url FROM case_resources WHERE case_id=? AND position LIKE ? AND status=1',(key,f"message:{original['message_id']}:part:%")))
                    raw += [{'type':r['kind'],'data':{'url':r['url'],'resource_position':r['position']}} for r in saved]
                    if not saved: raw += [{'type':kind,'data':{}} for kind in original.get('media',[]) if kind in ('image','face')]
                row={k:original[k] for k in ('message_id','user_id','time','name')}
                row.update(portraits[original['user_id']])
                member=self.monitor.directory.members.get(case['group_id'],{}).get(str(original['user_id']),{})
                row.update(level=member.get('level',''),role=member.get('role',''),title=member.get('title',''))
                row['parts']=[]
                for index,part in enumerate(raw[:100]):
                    kind,data=part.get('type'),part.get('data',{})
                    if kind=='text': row['parts'].append({'type':'text','text':str(data.get('text',''))[:8000]})
                    elif kind=='at': row['parts'].append({'type':'text','text':'@'+('全体成员' if data.get('qq')=='all' else self.monitor.directory.member(case['group_id'],data.get('qq')) or '成员')})
                    elif kind=='reply':
                        quoted=next((m for m in source if str(m['message_id'])==str(data.get('id'))),None)
                        row['parts'].append({'type':'reply','name':quoted['name'] if quoted else '引用消息','text':quoted.get('text','')[:300] if quoted else '原消息未包含在当前上下文中'})
                    elif kind in ('image','face'):
                        url=data.get('url','')
                        label=str(data.get('summary') or ('QQ表情' if kind=='face' else '图片'))[:100]
                        try:
                            if kind=='face' and not data.get('resource_position'):
                                face=await self.monitor.qq.call('fetch_face_entity',{'face_id':int(data.get('id',0))})
                                url=(face or {}).get('url','');label=(face or {}).get('q_des') or label
                            elif not safe_image_url(url) and (data.get('file') or data.get('file_id')):
                                info=await self.monitor.qq.call('get_image',{'file':str(data.get('file') or data['file_id'])})
                                url=(info or {}).get('url','')
                        except (ValueError,TimeoutError,OSError,WebSocketException): pass
                        cached=await self.assets.image(url,position=data.get('resource_position') or f"message:{original['message_id']}:part:{index}",kind=kind)
                        row['parts'].append({'type':kind,'url':cached,'text':label})
                    else: row['parts'].append({'type':'unsupported','text':{'record':'语音','video':'视频','forward':'合并转发','json':'卡片','xml':'卡片','file':'文件'}.get(kind,'其他附件')})
                return row
            async def bounded(original):
                async with semaphore: return await render(original)
            messages=list(await asyncio.gather(*(bounded(m) for m in source)))
            result={'group_name':self.monitor.directory.name(case['group_id']),'member_count':self.monitor.directory.group_counts.get(case['group_id'],0),'messages':messages,'decoration_note':'头像与挂件为当前 QQ 资料；历史装扮及个性气泡皮肤未提供，使用普通气泡。'}
            if len(self.cache)>=20: self.cache.pop(next(iter(self.cache)))
            self.cache[key]=(time.time(),result)
            return result
