"""Isolated API and domain regression checks. Never modifies live data."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import shutil
import threading
import unittest
import uuid
from unittest.mock import patch
from datetime import datetime, timedelta
from zipfile import ZipFile
from group_watch.evidence.archive_container import Archive

TEST_ROOT = (Path(os.environ.get('LAN_TEST_ROOT', 'tmp')) / 'group-evidence-tests').resolve()


class SandboxDirectory:
    def __init__(self, parent=TEST_ROOT):
        self.path = parent / uuid.uuid4().hex
        self.path.mkdir(parents=True)
        self.name = str(self.path)

    def cleanup(self):
        if not self.path.resolve().is_relative_to(TEST_ROOT):
            raise RuntimeError('Test cleanup must stay within the project test directory')
        shutil.rmtree(self.path)


SANDBOX = SandboxDirectory()
from group_watch.evidence.store import RecordStore
from group_watch.app import create_app
from group_watch.settings import Settings
from group_watch.monitoring.service import Monitor
from fastapi.testclient import TestClient
from group_watch.evidence.domain import ban_info
from group_watch.evidence.domain import duration_delta
from group_watch.evidence.domain import normalize_account
from group_watch.evidence.domain import suggestion
from group_watch.evidence.domain import risk_members

PNG = base64.b64encode(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGZkAAAAASUVORK5CYII=')).decode()


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, GROUP_EVIDENCE_PROFILES='0')
        self.environment.start()
        self.folder = SandboxDirectory(Path(SANDBOX.name))
        cfg = Settings(db_path=str(self.folder.path/'watch.sqlite3'), local_env=str(self.folder.path/'.env'),
                       evidence_tokens=['fixture-token-'+'x'*32])
        monitor = Monitor(cfg)
        async def start(): pass
        async def stop():
            if monitor.client: await monitor.client.aclose()
            monitor.store.db.close()
        monitor.start, monitor.stop = start, stop
        self.app = create_app(cfg, monitor)
        self.client = TestClient(self.app, base_url='http://127.0.0.1')
        self.client.__enter__()
        self.store = self.app.state.evidence

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.folder.cleanup()
        self.environment.stop()

    def request(self, path, body=None, method=None, headers=None, status=200):
        response = self.client.request(method or ('POST' if body is not None else 'GET'), '/evidence'+path,
            content=json.dumps(body,ensure_ascii=False) if body is not None else None,
            headers={'Authorization':'Bearer fixture-token-'+'x'*32, **(headers or ({'Content-Type':'application/json'} if body is not None else {}))})
        self.assertEqual(response.status_code, status, response.text if response.status_code != status else '')
        return response.json() if response.headers['content-type'].startswith('application/json') else response.content

    def record(self, **updates):
        return {'nickname':'测试成员', 'member_id':'10001', 'group_id':100000001, 'event_date':'2026-10-22',
                'reason':'行为甲', 'punishment':'警告', 'operator':'测试管理员', **updates}

    def test_fresh_schema_contains_only_current_record_tables(self):
        with self.store.connect() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns={r[1] for r in db.execute('PRAGMA table_info(records)')}
        self.assertEqual(tables,{'records','rules','audit','sqlite_sequence'})
        self.assertFalse({'member','category','source','group_name','duration'}&columns)
        self.assertTrue({'nickname','card','group_id','avatar_status','nickname_status'}<=columns)

    def test_batch_shared_images_edit_delete_backup(self):
        people = [self.record(member_id=str(n),images=[{'data':PNG,'name':'原图.png'}]) for n in (10001,10002)]
        ids = self.request('/api/batch', {'records':people})['ids']
        records = self.request('/api/records')
        self.assertEqual(len(records), 2)
        self.assertEqual(len({r['images'][0]['url'] for r in records}),1)
        self.assertEqual(len(list(self.store.uploads.iterdir())),1)
        image_url = records[0]['images'][0]['url']
        image = records[0]['images'][0]
        self.assertTrue(image['name'].endswith('.webp'))
        self.assertEqual(image['original_name'],'原图.png')
        media = self.client.get('/evidence'+image_url,headers={'Authorization':'Bearer fixture-token-'+'x'*32})
        self.assertEqual(media.status_code,200)
        self.assertIn('inline; filename="'+image['name']+'"',media.headers['content-disposition'])
        before = self.request(image_url)
        item = next(r for r in records if r['id']==ids[0])
        item.update(event_date='2026-10-23',notes='修改后',source='伪造来源')
        self.request('/api/records', item)
        edited = next(r for r in self.request('/api/records') if r['id']==ids[0])
        self.assertNotIn('source',edited)
        self.assertNotIn('date_basis',edited)
        self.request('/api/records/'+ids[0], {}, 'DELETE')
        self.assertEqual(self.request(image_url),before)
        zip_bytes = self.request('/api/backup')
        archive_path = self.store.data/'verification.zip'
        archive_path.write_bytes(zip_bytes)
        with Archive(archive_path) as archive:
            names = archive.namelist()
            self.assertIn('evidence.sqlite3',names)
            self.assertTrue(any(n.startswith('uploads/') for n in names))
            copied = sqlite3.connect(':memory:')
            copied.deserialize(archive.read('evidence.sqlite3'))
            self.assertEqual(copied.execute('SELECT count(*) FROM records').fetchone()[0],1)
            copied.close()
        self.request('/api/records/'+ids[1],{},'DELETE')
        self.assertEqual(self.request(image_url),before)  # retained for audit history
        self.assertEqual(self.request('/api/records'),[])
        self.assertEqual(self.request('/api/overview')['backup_count'],5)
        with self.store.connect() as db:
            changes = [json.loads(row[0]) for row in db.execute("SELECT detail FROM audit WHERE action='编辑记录'")]
        self.assertEqual(changes[0]['before']['notes'],'')
        self.assertEqual(changes[0]['after']['notes'],'修改后')

    def test_batch_rolls_back_and_validation(self):
        first = self.record(images=[{'data':PNG,'name':'临时图.png'}])
        duplicate = self.record(member_id='００１０００１')
        self.request('/api/batch',{'records':[first,duplicate]},status=400)
        self.assertEqual(self.store.get_records(),[])
        self.assertEqual(list(self.store.uploads.iterdir()),[])
        for updates in ({'event_date':'2026-02-30'},{'punishment':'不存在'}, {'images':[{'url':'/uploads/other.png'}]},
                        {'nickname':123}):
            self.request('/api/records',self.record(**updates),status=400)
        self.request('/api/records',self.record(),headers={'Content-Type':'application/json','Origin':'https://other.example'},status=403)
        self.assertEqual(self.store.get_records(),[])

    def test_rules_suggestion_group_identity_and_risks(self):
        self.request('/api/rules',{'rules':[{'reason':'行为甲','steps':['警告','禁言3天','移出群聊'],'notes':'人工确认'}]})
        candidate = self.record(member_id='００１０００１')
        self.assertEqual(self.request('/api/suggest',candidate)['penalty'],'警告')
        for i in range(2):
            self.request('/api/records',candidate)
        advice = self.request('/api/suggest',candidate)
        self.assertEqual((advice['occurrence'],advice['penalty']),(3,'移出群聊'))
        risks = self.request('/api/overview')['risks']
        self.assertEqual(risks[0]['status'],'再犯预警')
        self.assertEqual(self.request('/api/suggest',{**candidate,'group_id':100000002})['previous'],0)
        old = self.store.get_records()[0]
        self.assertEqual(self.request('/api/suggest',old)['previous'],1)
        self.request('/api/records',candidate)
        self.assertEqual(self.request('/api/overview')['risks'][0]['status'],'达到移出规则')
        self.assertEqual(self.request('/api/suggest',candidate)['penalty'],'')
        self.request('/api/rules',{'rules':[]},status=400)

    def test_profile_jobs_update_merged_fields_and_reads_do_not_fetch(self):
        cache=self.store.get_profiles();cache.enabled=True;self.store.source_profile=None;cache.resolver=None
        cache.nickname_url='https://profiles.example.test/?qq={qq}'
        with patch('group_watch.evidence.profiles.download',side_effect=lambda url,*args:base64.b64decode(PNG) if 'qlogo.cn' in url else b'{"nickname":""}') as remote:
            key=self.request('/api/records',self.record(nickname=None))['id']
            for future in list(cache.pending.values()):future.result(timeout=5)
            profile=self.request('/api/profiles')['items'][key]
            self.assertEqual((profile['nickname'],profile['nickname_status'],profile['avatar_status']),('',1,1))
            self.assertTrue(profile['avatar_url'].endswith('.webp'))
            calls=remote.call_count
            self.request('/api/records');self.request('/api/profiles');self.assertEqual(remote.call_count,calls)
            archive=self.store.backup()
            with Archive(archive) as saved:
                db=sqlite3.connect(':memory:');db.deserialize(saved.read('evidence.sqlite3'))
                self.assertEqual(db.execute('SELECT nickname,nickname_status FROM records').fetchone(),('',1));db.close()

    def test_same_qq_new_record_cannot_replace_old_snapshot(self):
        cache=self.store.get_profiles();cache.enabled=True;cache.resolver=None
        names=[]
        for generation in (1,2):
            with patch('group_watch.evidence.profiles.download',side_effect=lambda url,*args:base64.b64decode(PNG) if 'qlogo.cn' in url else json.dumps({'name':'昵称'+str(generation)}).encode()):
                key=self.request('/api/records',self.record(nickname=None))['id']
                for future in list(cache.pending.values()):future.result(timeout=5)
                names.append((key,self.request('/api/profiles')['items'][key]['nickname']))
        self.assertEqual([name for _,name in names],['昵称1','昵称2'])
        self.assertEqual(self.request('/api/profiles')['items'][names[0][0]]['nickname'],'昵称1')

    def test_profile_failures_remain_optional(self):
        cache=self.store.get_profiles();cache.enabled=True;cache.resolver=None
        with patch('group_watch.evidence.profiles.download',side_effect=OSError('offline')) as remote:
            key=self.request('/api/records',self.record(nickname=None))['id']
            for future in list(cache.pending.values()):future.result(timeout=5)
            result=self.request('/api/profiles')['items'][key]
            self.assertEqual((result['nickname_status'],result['avatar_status']),(2,2));self.assertIsNone(result['nickname'])
            count=remote.call_count
            self.request('/api/profiles');self.request('/api/records');self.assertEqual(remote.call_count,count)
        self.assertEqual(len(self.store.get_records()),1)

    def test_restart_does_not_retry_completed_resources(self):
        key=self.request('/api/records',self.record())['id']
        self.store.close()
        with self.store.connect() as db:db.execute('UPDATE records SET nickname_status=1,avatar_status=2 WHERE id=?',(key,))
        with patch('group_watch.evidence.profiles.download',side_effect=AssertionError('completed resources must not fetch')) as remote:
            self.store.initialize(self.store.data)
            self.assertEqual(self.request('/api/profiles')['items'][key]['nickname'],'测试成员')
            self.assertEqual(remote.call_count,0)



class DomainTests(unittest.TestCase):
    def test_nickname_payload_validation(self):
        from group_watch.evidence.profiles import nickname_from_json
        for field in ('nickname','nick','name'):
            raw = json.dumps({'code':200,'result':{'qq':'10001',field:'昵称示例'}}).encode()
            self.assertEqual(nickname_from_json(raw,'10001'),'昵称示例')
        raw = json.dumps({'code':200,'data':{'user_info':{'qq':'10001','name':'嵌套昵称'}}}).encode()
        self.assertEqual(nickname_from_json(raw,'10001'),'嵌套昵称')
        for response in ({'code':201,'msg':'数据获取出错'},
                         {'code':200,'data':{'user_info':{'qq':'10002','name':'其他人'}}},
                         {'code':200,'qq':'10002','data':{'user_info':{'qq':'10001','name':'账号冲突'}}}):
            with self.assertRaises(ValueError):
                nickname_from_json(json.dumps(response).encode(),'10001')
        for response in ({'code':500,'name':'错误结果'}, {'result':{'qq':'10002','name':'其他人'}}, {'name':None}):
            with self.assertRaises(ValueError):
                nickname_from_json(json.dumps(response).encode(),'10001')

    def test_ban_precision_and_ranges(self):
        def ban(text, **changes):
            return ban_info({'punishment':'禁言','event_date':'2026-10-20','penalty_text':text,'duration':'',**changes},datetime(2026,10,22,12))
        current = ban('禁言三天')
        self.assertEqual((current['status'],current['end'],current['estimated']),('进行中','2026-10-23T00:00',True))
        self.assertEqual(ban('禁言20天（2026/10/1 8:30 起）')['status'],'已结束')
        self.assertEqual(ban('永久禁言')['status'],'永久禁言')
        self.assertEqual(ban('禁言7-30天')['status'],'未注明结束')
        self.assertEqual(ban('禁言7天至30天')['end'],'')
        self.assertEqual(ban('禁言2026-10-23 09:00至2026-10-24 09:00')['status'],'未开始')
        self.assertEqual(ban('禁言2026-10-20 09:00至2026-10-21 09:00')['estimated'],False)
        self.assertEqual(ban('禁言1个月 2026-10-20 09:00')['estimated'],True)
        self.assertEqual(ban('禁言1个月 2026-10-20 09:00至2026-11-20 09:00')['estimated'],False)
        self.assertEqual(ban('禁言2026-10-22 12:00至2026-10-22 13:00')['start'],'2026-10-22T12:00')
        for text in ('7-30天','7天至30天','1.5～3天','一到两周'):
            self.assertIsNone(duration_delta(text))
        self.assertEqual(duration_delta('禁言两周'),timedelta(days=14))
        self.assertEqual(normalize_account(' ００１２３ '),'123')


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        SANDBOX.cleanup()
