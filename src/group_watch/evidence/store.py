"""Formal records, profile fields and verified operation snapshots."""
from group_watch.utils.files import atomic_write
from group_watch.utils.images import webp
from group_watch.evidence.profiles import ProfileCache
from group_watch.evidence.domain import normalize_account, now, suggestion
from group_watch.utils.sqlite import connect
from contextlib import nullcontext
import base64
import hashlib
import json
from pathlib import Path
import re
import threading
import tempfile
import uuid
from datetime import datetime

FIELDS = ['member_id','group_id','nickname','card','event_date','reason','punishment','penalty_text','operator','notes','occurrence']
PROFILE_FIELDS = ['nickname_status','nickname_at','avatar_status','avatar_at','avatar_url']

class RecordStore:
    def __init__(self, data):
        self.data = Path(data).resolve()
        self.uploads = self.data / 'uploads'
        self.db_path = self.data / 'evidence.sqlite3'
        self.lock = threading.RLock()
        self.profiles = None
        self.groups = None
        self.source_profile = None

    def connect(self):
        return connect(self.db_path, timeout=30, close_on_exit=True)

    def init_db(self):
        self.uploads.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, member_id TEXT NOT NULL, group_id INTEGER NOT NULL CHECK(group_id != 0),
                nickname TEXT, card TEXT, event_date TEXT NOT NULL, reason TEXT NOT NULL,
                punishment TEXT NOT NULL, penalty_text TEXT NOT NULL, operator TEXT NOT NULL,
                notes TEXT NOT NULL, occurrence TEXT NOT NULL, images TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                nickname_status INTEGER NOT NULL DEFAULT 0 CHECK(nickname_status IN (0,1,2)), nickname_at TEXT,
                avatar_status INTEGER NOT NULL DEFAULT 0 CHECK(avatar_status IN (0,1,2)), avatar_at TEXT, avatar_url TEXT);
            CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, reason TEXT NOT NULL UNIQUE, steps TEXT NOT NULL, notes TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL, record_id TEXT NOT NULL, detail TEXT NOT NULL);
            """)

    def initialize(self, data):
        self.close()
        self.data = Path(data).resolve()
        self.uploads = self.data / 'uploads'
        self.db_path = self.data / 'evidence.sqlite3'
        self.init_db()
        self.get_profiles().resume()

    def close(self):
        if self.profiles:
            self.profiles.close()
            self.profiles = None

    def get_records(self):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM records ORDER BY event_date DESC,created_at DESC,id')]
        for row in rows:
            row['images'] = json.loads(row['images'])
        return rows

    def get_rules(self):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM rules ORDER BY rowid')]
        for row in rows:
            row['steps'] = json.loads(row['steps'])
        return rows

    def get_profiles(self):
        with self.lock:
            if self.profiles is None:
                self.profiles = ProfileCache(self.data, self.source_profile)
            return self.profiles

    def queue_profiles(self, records):
        for row in records:
            self.get_profiles().queue(row)

    def audit(self, db, action, record_id='', detail=None):
        db.execute('INSERT INTO audit(at,action,record_id,detail) VALUES(?,?,?,?)',
                   (now().isoformat(),action,record_id,json.dumps(detail or {},ensure_ascii=False)))

    @staticmethod
    def _replace_file(target, raw):
        atomic_write(target,raw)

    def validate_record(self, body):
        if not isinstance(body,dict):
            raise ValueError('记录格式无效')
        values = {key:str(body.get(key,'')).strip() for key in FIELDS if key not in ('nickname','card','group_id')}
        for key in ('nickname','card'):
            value = body.get(key)
            if value is not None and (not isinstance(value,str) or len(value)>100):
                raise ValueError('昵称与群名片须为文本或空值')
            values[key] = value
        try:
            group = int(body['group_id'])
            if isinstance(body['group_id'],bool) or not group or abs(group)>2**63-1:
                raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise ValueError('请选择已登记的群聊或直播间')
        if self.groups is not None and group not in self.groups():
            raise ValueError('请选择已登记的群聊或直播间')
        values['group_id'] = group
        values['member_id'] = normalize_account(values['member_id'])
        if not values['member_id']:
            raise ValueError('请填写成员账号；可先填昵称，系统会按群成员自动补全')
        pattern = r'[1-9]\d{4,11}' if group>0 else r'-[1-9]\d{0,18}'
        if not re.fullmatch(pattern,values['member_id']) or abs(int(values['member_id']))>2**63-1:
            raise ValueError('QQ 群成员账号应为 5-12 位数字' if group>0 else '直播间成员账号须为负号开头的 UID（如 -123456）')
        if not values['reason']:
            raise ValueError('请填写行为原因')
        if any(len(v)>10000 for v in values.values() if isinstance(v,str)):
            raise ValueError('单项文本不能超过10000字')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',values['event_date']):
            raise ValueError('日期格式应为 YYYY-MM-DD')
        datetime.strptime(values['event_date'],'%Y-%m-%d')
        if values['punishment'] not in ('警告','禁言','移出群聊','其他'):
            raise ValueError('处罚类型无效')
        return values

    def store_images(self, items, existing, written, record_id):
        if not isinstance(items,list) or len(items)>8:
            raise ValueError('每条记录最多8张图片')
        result=[]
        for index,item in enumerate(items,1):
            if not isinstance(item,dict):
                raise ValueError('图片数据无效')
            if 'url' in item:
                match=next((x for x in existing if x['url']==item['url']),None)
                if not match:
                    raise ValueError('图片不属于当前记录')
                result.append(match)
                continue
            raw=base64.b64decode(item.get('data',''),validate=True)
            if not raw or len(raw)>5*1024*1024:
                raise ValueError('单张图片须在5MB以内')
            raw=webp(raw)
            target=self.uploads/(hashlib.sha256(raw).hexdigest()+'.webp')
            if not target.exists():
                self._replace_file(target,raw)
                written.append(target)
            result.append(dict(url='/uploads/'+target.name,name=f'{record_id}-{index}.webp',
                               original_name=str(item.get('original_name') or item.get('name','图片'))[:200]))
        return result

    def save_records(self, body, batch=False):
        written=[]
        with self.lock, self.profiles.lock if self.profiles else nullcontext():
            inputs=body.get('records') if batch else [body]
            if not isinstance(inputs,list) or not 1<=len(inputs)<=50:
                raise ValueError('一次可登记1至50名成员')
            existing=self.get_records()
            prepared=[]
            seen=set()
            try:
                for item in inputs:
                    values=self.validate_record(item)
                    key=(values['group_id'],values['member_id'])
                    if batch and (key in seen or item.get('id')):
                        raise ValueError('批量名单重复或包含已有记录')
                    seen.add(key)
                    record_id=str(item.get('id') or uuid.uuid4().hex)
                    old=next((r for r in existing if r['id']==record_id),None)
                    if item.get('id') and not old:
                        raise ValueError('记录不存在，请刷新后重试')
                    if not values['occurrence']:
                        values['occurrence']=str(suggestion(existing,self.get_rules(),dict(values,id=record_id))['occurrence'])
                    same=old is not None and (old['member_id'],old['group_id'])==key[::-1]
                    states={k:old[k] for k in PROFILE_FIELDS} if same else dict(nickname_status=0,nickname_at=None,avatar_status=0,avatar_at=None,avatar_url=None)
                    if old and not same:
                        values.update(nickname=None,card=None)
                    # Explicitly supplied raw strings are valid successful data, including blanks.
                    if values['nickname'] is not None:
                        states.update(nickname_status=1,nickname_at=now().isoformat())
                    record=dict(id=record_id,**values,**states,
                                images=self.store_images(item.get('images',[]),old['images'] if old else [],written,record_id),
                                created_at=old['created_at'] if old else now().isoformat(),updated_at=now().isoformat())
                    prepared.append((record,old))
                archive=self.backup('before-edit' if any(old for _,old in prepared) else 'before-create')
                with self.connect() as db:
                    for row,old in prepared:
                        if self.profiles:
                            self.profiles.invalidate(row['id'])
                        columns=list(row)
                        db.execute(f'INSERT OR REPLACE INTO records ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                                   [json.dumps(row[k],ensure_ascii=False) if k=='images' else row[k] for k in columns])
                        self.audit(db,'编辑记录' if old else '新建记录',row['id'],dict(before=old,after=row,backup=archive.name))
            except Exception:
                # Only unpublished files from this failed transaction are removed.
                for target in written:
                    target.unlink(missing_ok=True)
                raise
            try:
                self.queue_profiles([r for r,_ in prepared])
            except (RuntimeError,OSError):
                pass  # Committed pending work is resumed at the next startup.
            return dict(ids=[r['id'] for r,_ in prepared],id=prepared[0][0]['id'],count=len(prepared))

    def save_rules(self, body):
        incoming = body.get('rules')
        if not isinstance(incoming, list) or not 1 <= len(incoming) <= 200:
            raise ValueError('请保留至少1条规则，最多200项')
        rules, names = ([], set())
        for rule in incoming:
            reason = str(rule.get('reason', '')).strip()
            steps = rule.get('steps')
            if not reason or reason in names or len(reason) > 500:
                raise ValueError('规则行为名称不能为空、重复或超过500字')
            if not isinstance(steps, list) or len(steps) > 10 or any((not isinstance(x, str) or len(x) > 1000 for x in steps)):
                raise ValueError('每条规则最多10级，每级不超过1000字')
            notes = str(rule.get('notes', ''))
            if len(notes) > 10000:
                raise ValueError('规则备注过长')
            names.add(reason)
            rules.append({'id': uuid.uuid4().hex, 'reason': reason, 'steps': steps, 'notes': notes})
        with self.lock:
            archive = self.backup('before-rules')
            with self.connect() as db:
                self.audit(db, '更新处理规则', detail={'before': self.get_rules(), 'after': rules, 'backup': archive.name})
                db.execute('DELETE FROM rules')
                db.executemany('INSERT INTO rules VALUES(?,?,?,?)', [(r['id'], r['reason'], json.dumps(r['steps'], ensure_ascii=False), r['notes']) for r in rules])
        return {'count': len(rules)}

    def overview(self):
        from group_watch.evidence.domain import risk_members
        with self.lock:
            with self.connect() as db:
                logs=[dict(row) for row in db.execute('SELECT id,at,action,record_id,detail FROM audit ORDER BY id DESC LIMIT 50')]
            files=[p for p in (self.data/'backups').glob('*.tar.zst') if p.is_file() and not p.is_symlink()]
            available={p.name for p in files}
            for row in logs:
                detail=json.loads(row.pop('detail') or '{}')
                if detail.get('backup') in available:
                    row['backup']=detail['backup']
            return dict(risks=risk_members(self.get_records(),self.get_rules()),audit=logs,
                        backup_count=len(files),backup_bytes=sum(p.stat().st_size for p in files),
                        as_of=now().isoformat(),timezone='Asia/Shanghai')

    def delete_record(self, record_id):
        with self.lock, self.profiles.lock if self.profiles else nullcontext():
            if self.profiles:
                self.profiles.invalidate(record_id)
            record=next((r for r in self.get_records() if r['id']==record_id),None)
            if not record:
                return None
            archive=self.backup('before-delete')
            with self.connect() as db:
                db.execute('DELETE FROM records WHERE id=?',(record_id,))
                self.audit(db,'删除记录',record_id,dict(before=record,backup=archive.name))
            return dict(ok=True,backup=archive.name)

    def backup(self, label='manual'):
        from group_watch.evidence.archives import create_backup
        with self.lock:
            return create_backup(self.data,self.connect,self.get_profiles(),label)

    def backup_path(self, name):
        if not isinstance(name,str) or not re.fullmatch(r'\d{8}-\d{6}-[a-z0-9-]+-[a-f0-9]{8}\.tar\.zst',name):
            raise ValueError('请选择有效的留证备份')
        path=self.data/'backups'/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('备份不存在')
        return path

    def rollback(self, name):
        from group_watch.evidence.archives import restore_archive
        with self.lock, tempfile.TemporaryDirectory(prefix='.rollback-',dir=self.data) as temporary:
            restored=Path(temporary)/'snapshot'
            restore_archive(self.backup_path(name),restored)
            safety=self.backup('before-rollback')
            self.close()
            staged=RecordStore(restored)
            # Only the current schema is accepted. No startup schema conversion.
            changed=[]
            try:
                for folder in ('uploads','avatars'):
                    for source in (restored/folder).glob('*.webp'):
                        target=self.data/folder/source.name
                        target.parent.mkdir(exist_ok=True)
                        previous=target.read_bytes() if target.exists() else None
                        changed.append((target,previous))
                        self._replace_file(target,source.read_bytes())
                with staged.connect() as source,self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    for table in ('records','rules'):
                        columns=[r[1] for r in db.execute(f'PRAGMA table_info({table})')]
                        rows=source.execute(f'SELECT {",".join(columns)} FROM {table}').fetchall()
                        db.execute(f'DELETE FROM {table}')
                        db.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})',rows)
                    self.audit(db,'回退留证备份',detail=dict(restored_backup=name,backup=safety.name))
                changed.clear()
            finally:
                for target,previous in reversed(changed):
                    if previous is None:
                        target.unlink(missing_ok=True)
                    else:
                        self._replace_file(target,previous)
                self.get_profiles().resume()
            return dict(ok=True,backup=safety.name)
