import base64,hashlib,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from group_watch.evidence.archive_container import Archive
from group_watch.evidence.store import RecordStore
from group_watch.evidence.archives import restore_archive
PNG='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGZkAAAAASUVORK5CYII='
class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.environment=patch.dict(os.environ, GROUP_EVIDENCE_PROFILES='0');self.environment.start()
  self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.store=RecordStore(self.root/'source');self.store.initialize(self.store.data)
 def tearDown(self):
  self.store.get_profiles().close();self.store.profiles=None;self.folder.cleanup();self.environment.stop()
 def record(self):
  return dict(group_id=100000001,member_id='12345',event_date='2026-10-24',reason='回归验证',punishment='警告',operator='测试',nickname='测试成员',images=[dict(data=PNG,name='证据.png')])
 def save(self):
  self.store.save_records(self.record());return self.store.backup()
 def test_mutations_publish_verified_undo_snapshots_and_sizes(self):
     created=self.store.save_records(self.record())
     self.store.save_records(self.record()|{'id':created['id'],'reason':'已修改'})
     self.store.delete_record(created['id'])
     overview=self.store.overview()
     self.assertEqual(len(overview['audit']),3)
     self.assertEqual(overview['backup_count'],3)
     self.assertEqual(overview['backup_bytes'],sum(p.stat().st_size for p in (self.store.data/'backups').glob('*.tar.zst')))
     for row in overview['audit']:
         self.assertTrue(self.store.backup_path(row['backup']).is_file())
     self.store.rollback(overview['audit'][0]['backup'])
     self.assertEqual(self.store.get_records()[0]['reason'],'已修改')
     self.store.rollback(overview['audit'][-1]['backup'])
     self.assertEqual(self.store.get_records(),[])
 def test_manual_backups_are_not_operation_rows(self):
  self.store.save_records(self.record())
  before=self.store.overview()['audit']
  archive=self.store.backup('manual')
  after=self.store.overview()
  assert archive.is_file()
  assert after['audit']==before
  assert all(row['action']!='手动备份' for row in after['audit'])
 def test_rollback_has_a_safety_snapshot_and_can_be_undone(self):
     created=self.store.save_records(self.record());snapshot=self.store.backup()
     self.store.save_records(self.record()|{'id':created['id'],'reason':'修改'})
     result=self.store.rollback(snapshot.name)
     self.assertEqual(self.store.get_records()[0]['reason'],'回归验证')
     self.assertEqual(len(list((self.store.data/'backups').glob('*.tar.zst'))),4)
     self.store.rollback(result['backup'])
     self.assertEqual(self.store.get_records()[0]['reason'],'修改')
 def test_old_zip_is_rejected_without_creating_a_destination(self):
  from zipfile import ZipFile
  old=self.root/'old.zip'
  with ZipFile(old,'w') as archive:archive.writestr('manifest.json','{}')
  with self.assertRaisesRegex(ValueError,'备份格式无效'):restore_archive(old,self.root/'old-restored')
  self.assertFalse((self.root/'old-restored').exists())
 def rewrite(self,original,changes):
  target=self.root/'changed.tar.zst'
  with Archive(original) as z:files={n:z.read(n) for n in z.namelist()}
  files.update(changes);manifest=json.loads(files['manifest.json'])
  for name in changes:
   if name!='manifest.json':manifest['files'][name]={'bytes':len(files[name]),'sha256':hashlib.sha256(files[name]).hexdigest()}
  files['manifest.json']=json.dumps(manifest).encode()
  with Archive(target,'w') as z:
   for name,raw in files.items():z.writestr(name,raw)
  return target
 def test_round_trip_preserves_every_hash_and_audit(self):
  archive=self.save();destination=self.root/'restored';manifest=restore_archive(archive,destination)
  for name,info in manifest['files'].items():self.assertEqual(hashlib.sha256((destination/name).read_bytes()).hexdigest(),info['sha256'])
  with closing(sqlite3.connect(destination/'evidence.sqlite3')) as db:
   self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0],1);self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],1)
  with self.assertRaises(ValueError):restore_archive(archive,destination)
  self.assertTrue((destination/'evidence.sqlite3').exists())
 def test_corrupt_database_path_and_hash_leave_no_destination(self):
  archive=self.save()
  for name,bad in [('database',self.rewrite(archive,{'evidence.sqlite3':b'broken sqlite'})),('path',self.rewrite(archive,{'../escape':b'unsafe'}))]:
   with self.subTest(name=name),self.assertRaises((ValueError,sqlite3.DatabaseError)):restore_archive(bad,self.root/name)
   self.assertFalse((self.root/name).exists());self.assertFalse(list(self.root.glob(name+'.restore-*')))
  with Archive(archive) as z:files={n:z.read(n) for n in z.namelist()}
  files['evidence.sqlite3']=b'bad'
  damaged=self.root/'hash.tar.zst'
  with Archive(damaged,'w') as z:
   for name,raw in files.items():z.writestr(name,raw)
  with self.assertRaises(ValueError):restore_archive(damaged,self.root/'hash')
  self.assertFalse((self.root/'hash').exists())
 def test_transaction_failure_cleans_only_new_images(self):
  with patch.object(self.store,'audit',side_effect=sqlite3.OperationalError('injected rollback')):
   with self.assertRaises(sqlite3.OperationalError):self.store.save_records(self.record())
  self.assertEqual(self.store.get_records(),[]);self.assertEqual(list(self.store.uploads.iterdir()),[])
  self.save();committed=list(self.store.uploads.iterdir())
  bad=self.record();bad['images'].append(dict(data='not base64'))
  with self.assertRaises(ValueError):self.store.save_records(bad)
  self.assertEqual(list(self.store.uploads.iterdir()),committed)
 def test_profile_failure_keeps_committed_record_and_image(self):
  with patch.object(self.store,'queue_profiles',side_effect=OSError('profile disk failure')):self.store.save_records(self.record())
  self.assertEqual(len(self.store.get_records()),1);self.assertEqual(len(list(self.store.uploads.iterdir())),1)
 def test_failed_backup_does_not_publish_final_archive(self):
  self.store.save_records(self.record())
  (self.store.data/'backups').mkdir(exist_ok=True)
  before=set((self.store.data/'backups').iterdir())
  with patch('group_watch.evidence.archives.verify_archive',side_effect=ValueError('injected failed verification')):
   with self.assertRaises(ValueError):self.store.backup()
  self.assertEqual(set((self.store.data/'backups').iterdir()),before)

 def test_rollback_restores_media_and_compensates_failed_transaction(self):
  snapshot=self.save();record=self.store.get_records()[0];image=self.store.uploads/Path(record['images'][0]['url']).name
  original=image.read_bytes()
  from io import BytesIO
  from PIL import Image
  encoded=BytesIO();Image.new('RGB',(2,2),'red').save(encoded,format='WEBP');changed=encoded.getvalue();image.write_bytes(changed)
  with patch.object(self.store,'audit',side_effect=RuntimeError('transaction failed')):
   with self.assertRaises(RuntimeError):self.store.rollback(snapshot.name)
  self.assertEqual(image.read_bytes(),changed)
  result=self.store.rollback(snapshot.name)
  self.assertEqual(image.read_bytes(),original)
  self.assertTrue(result['ok'])
  self.assertTrue(self.store.backup_path(result['backup']).is_file())
  self.assertEqual(len(list((self.store.data/'backups').glob('*.tar.zst'))),4)

if __name__=='__main__':unittest.main()
