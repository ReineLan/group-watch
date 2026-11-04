"""Explicit verified backups and rotation limited to files owned by this component."""
from group_watch.paths import LOGS
from group_watch.evidence.archive_container import Archive
import asyncio
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import time
import threading
import uuid


LOG = logging.getLogger(__name__)


def verify_backup(path):
    with Archive(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        evidence_name = 'evidence.tar'
        if manifest.get('format') != 'lan-workbench/2' or set(archive.namelist()) != {'manifest.json', evidence_name}:
            raise ValueError('备份格式无效')
        if len(archive.namelist()) != 2 or sum(i.file_size for i in archive.infolist()) > 3*1024**3:
            raise ValueError('备份大小或文件数量无效')
        for name in (evidence_name,):
            raw = archive.read(name)
            if hashlib.sha256(raw).hexdigest() != manifest['files'][name]:
                raise ValueError('备份校验失败')
        return manifest


class Maintenance:
    def __init__(self, cfg, evidence):
        self.cfg, self.evidence = cfg, evidence
        self.folder = Path(cfg.db_path).parent / 'workbench-backups'
        self.state_file = self.folder / 'state.json'
        self.state = {}
        self.last_activity = time.time()
        self.draining = False
        self.task = None
        self.busy = False
        self.backup_task = None
        self._backup_lock = threading.Lock()

    def save_state(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        part = self.state_file.with_suffix('.part')
        part.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
        os.replace(part, self.state_file)

    def backup(self):
        if not self._backup_lock.acquire(blocking=False):
            raise ValueError('正在创建备份，请稍后重试')
        self.busy = True
        try:
            return self._backup()
        finally:
            self.busy = False
            self._backup_lock.release()

    def _backup(self):
        from group_watch.evidence.archives import create_backup
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / ('auto-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + '.tar.zst')
        part = target.with_suffix('.zst.part')
        evidence_archive = None
        try:
            with self.evidence.lock:
                evidence_archive = create_backup(self.evidence.data, self.evidence.connect, self.evidence.get_profiles(), 'workbench-manual', rotate=False, compressed=False)
                evidence_raw = evidence_archive.read_bytes()
            files = {'evidence.tar': evidence_raw}
            manifest = dict(format='lan-workbench/2', created=time.time(), files={name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()})
            with Archive(part, 'w') as archive:
                for name, raw in files.items():
                    archive.writestr(name, raw)
                archive.writestr('manifest.json', json.dumps(manifest))
            verify_backup(part)
            os.replace(part, target)
            # Only auto-* in this dedicated directory. Existing/manual evidence archives stay untouched.
            for old in sorted(list(self.folder.glob('auto-*.tar.zst')), key=lambda p: p.stat().st_mtime, reverse=True)[5:]:
                old.unlink()
            self.state.update(last_backup=time.time(), backup=target.name, error='')
            self.save_state()
            return target
        finally:
            part.unlink(missing_ok=True)
            if evidence_archive is not None:
                evidence_archive.unlink(missing_ok=True)  # Temporary archive created by this invocation only.

    def status(self, queries):
        update_file = LOGS / 'update.json'
        try:
            update = json.loads(update_file.read_text('utf-8-sig'))
        except (ValueError, OSError):
            update = {'status': '等待监督进程检查' if self.cfg.automatic_updates else '已关闭'}
        def size(folder):
            total = 0
            for path in folder.glob('*'):
                try:
                    if path.is_file() and path.suffix in {'.zip', '.zst', '.sqlite3'}:
                        total += path.stat().st_size
                except FileNotFoundError:
                    pass  # A successful concurrent backup may have rotated this file.
            return total
        workbench = size(self.folder)
        operations = size(self.evidence.data/'backups') if self.evidence is not None else 0
        migration = size(Path(self.cfg.db_path).parent/'backups')
        return dict(**self.state, backup_bytes=workbench+operations+migration,
                    workbench_backup_bytes=workbench, operation_backup_bytes=operations, migration_backup_bytes=migration,
                    busy=self.busy, query_active=queries.active,
                    query_error=queries.last_error, last_activity=self.last_activity,
                    draining=self.draining, update=update, retention_days=self.cfg.retention_days,
                    query_calls_hour=self.cfg.query_calls_hour)

    async def close(self):
        if self.task:
            # Let an in-flight atomic backup finish before closing evidence profiles.
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.backup_task:
            try:
                await self.backup_task
            except Exception:
                LOG.exception('停止时等待备份失败；继续释放工作台资源')
