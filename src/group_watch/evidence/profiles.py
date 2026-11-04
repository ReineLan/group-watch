"""One-shot, per-record QQ profile snapshots; reads never trigger network requests."""
from group_watch.utils.files import atomic_write
from group_watch.evidence.domain import normalize_account, now
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import threading
from urllib.request import Request, urlopen
from urllib.parse import urlparse


DEFAULT_NICKNAME_API = 'https://xiaoapi.cn/v1/qzone_info.php?qq={qq}'


def avatar_extension(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if raw.startswith(b'\xff\xd8\xff'): return '.jpg'
    if raw.startswith((b'GIF87a',b'GIF89a')): return '.gif'
    if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP': return '.webp'
    raise ValueError('头像接口未返回图片')


def download_avatar(account):
    for url in (f'https://q1.qlogo.cn/g?b=qq&nk={account}&s=100',
                f'https://q.qlogo.cn/headimg_dl?dst_uin={account}&spec=160&img_type=jpg'):
        try:
            raw = download(url)
            return raw, avatar_extension(raw)
        except (ValueError,OSError):
            continue
    raise ValueError('未取得有效头像')

def qq_account(value):
    account = normalize_account(value)
    return account if re.fullmatch(r'[1-9]\d{4,11}', account) else ''


def download(url, limit=1024 * 1024):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://qzone.qq.com/'})
    with urlopen(request, timeout=5) as response:
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('资料响应过大')
        return raw


def nickname_from_json(raw, account):
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('昵称接口返回格式无效')
    code = data.get('code', data.get('ret', 200))
    if str(code) not in ('0', '1', '200') or data.get('success') is False:
        raise ValueError('昵称服务未返回可用昵称')
    payload = data['data'] if 'data' in data else data.get('result', data)
    if not isinstance(payload, dict):
        raise ValueError('昵称接口返回格式无效')
    user = payload.get('user_info', payload)
    if not isinstance(user, dict):
        raise ValueError('昵称接口返回格式无效')
    for returned in (data.get('qq'), payload.get('qq'), user.get('qq')):
        if returned and qq_account(returned) != account:
            raise ValueError('昵称接口返回账号不一致')
    name = next((user[k] for k in ('nickname','nick','name') if k in user),None)
    if not isinstance(name,str) or len(name)>100:
        raise ValueError('昵称接口未返回有效昵称')
    return name


class ProfileCache:
    """One attempt per pending resource; identity guarded writes survive restarts."""
    def __init__(self, root, resolver=None):
        self.root=Path(root)
        self.database=self.root/'evidence.sqlite3'
        self.avatars=self.root/'avatars'
        self.avatars.mkdir(parents=True,exist_ok=True)
        self.resolver=resolver
        self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='record-profile')
        self.pending={}
        self.generations={}
        self.stopped=False
        self.enabled=os.environ.get('GROUP_EVIDENCE_PROFILES','1')!='0'
        self.nickname_url=os.environ.get('QQ_NICKNAME_API',DEFAULT_NICKNAME_API).strip()
        if self.nickname_url.lower() in ('off','0'):
            self.nickname_url=''

    def rows(self):
        with closing(sqlite3.connect(self.database,timeout=30)) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM records')]

    def snapshot(self):
        return {r['id']:{k:r[k] for k in ('member_id','nickname','card','nickname_status','nickname_at','avatar_status','avatar_at','avatar_url')}
                for r in self.rows()}

    def settings(self):
        return dict(enabled=self.enabled,nickname_configured=bool(self.nickname_url),mode='record-fields')

    def lookup(self,value):
        matches=[r for r in self.snapshot().values() if r['member_id']==str(value)]
        return matches[-1] if matches else None

    def resume(self):
        for row in self.rows():
            self.queue(row)

    def queue(self,record):
        with self.lock:
            if self.stopped or not self.enabled or not any(record[k]==0 for k in ('nickname_status','avatar_status')):
                return
            key=record['id']
            generation=self.generations.get(key,0)+1
            self.generations[key]=generation
            future=self.pool.submit(self.fetch,dict(record),generation)
            self.pending[key]=future
            future.add_done_callback(lambda f:self.finished(key,generation))

    def invalidate(self,key):
        with self.lock:
            self.generations[key]=self.generations.get(key,0)+1

    def finished(self,key,generation):
        with self.lock:
            if self.generations.get(key)==generation:
                self.pending.pop(key,None)

    def retry(self,key):
        with self.lock,closing(sqlite3.connect(self.database,timeout=30)) as db,db:
            self.invalidate(key)
            db.execute("UPDATE records SET nickname_status=0,nickname_at=NULL,avatar_status=0,avatar_at=NULL WHERE id=?",(key,))
        row=next((r for r in self.rows() if r['id']==key),None)
        if row is None:
            raise ValueError('记录不存在')
        self.queue(row)

    def complete(self,record,generation,resource,fields,raw=None):
        key=record['id']
        with self.lock,closing(sqlite3.connect(self.database,timeout=30)) as db,db:
            if self.generations.get(key)!=generation or self.stopped:
                return
            match=(key,record['member_id'],record['group_id'],record['updated_at'])
            where='id=? AND member_id=? AND group_id=? AND updated_at=? AND '+resource+'_status=0'
            if not db.execute('SELECT 1 FROM records WHERE '+where,match).fetchone():
                return
            if raw is not None:
                target=self.avatars/(hashlib.sha256(raw).hexdigest()+'.webp')
                if not target.exists():
                    atomic_write(target,raw)
                fields['avatar_url']='/avatars/'+target.name
            fields[resource+'_at']=now().isoformat()
            db.execute('UPDATE records SET '+','.join(k+'=?' for k in fields)+' WHERE '+where,tuple(fields.values())+match)

    def fetch(self,record,generation):
        from group_watch.utils.images import webp
        account=record['member_id']
        identity={}
        if self.resolver:
            try:
                identity=self.resolver(record,self.root) or {}
            except Exception:
                pass
        if record['nickname_status']==0:
            try:
                if 'nickname' in identity and isinstance(identity['nickname'],str):
                    name=identity['nickname']
                elif record['group_id']>0 and self.nickname_url:
                    if '{qq}' not in self.nickname_url or urlparse(self.nickname_url).scheme!='https':
                        raise ValueError('昵称接口配置无效')
                    name=nickname_from_json(download(self.nickname_url.replace('{qq}',account),65536),account)
                else:
                    raise ValueError('未取得昵称')
                card=identity.get('card',record.get('card'))
                self.complete(record,generation,'nickname',dict(nickname=name,card=card,nickname_status=1))
            except Exception:
                self.complete(record,generation,'nickname',dict(nickname_status=2))
        if record['avatar_status']==0:
            try:
                if record['group_id']>0:
                    raw,_=download_avatar(account)
                elif identity.get('avatar_url'):
                    from group_watch.monitoring.chat import safe_image_url
                    if not safe_image_url(identity['avatar_url']):
                        raise ValueError('头像来源无效')
                    raw=download(identity['avatar_url'])
                else:
                    raise ValueError('未取得头像')
                self.complete(record,generation,'avatar',dict(avatar_status=1),webp(raw))
            except Exception:
                self.complete(record,generation,'avatar',dict(avatar_status=2))

    def close(self):
        with self.lock:
            self.stopped=True
        self.pool.shutdown(wait=True)
