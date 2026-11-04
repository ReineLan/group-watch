"""Atomic, hash-verified archives; restoration always creates a fresh directory."""
from group_watch.evidence.domain import now
from group_watch.evidence.archive_container import Archive
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import uuid


def _allowed(name):
    return name in {'evidence.sqlite3', 'README.txt'} or bool(
        re.fullmatch(r'(?:uploads/[a-f0-9]{64}|avatars/(?:[1-9]\d{4,11}|[a-f0-9]{64}))\.webp', name))


def _sqlite_check(path):
    if not path.is_file():
        raise ValueError('备份缺少数据库')
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('备份数据库检查失败')
        names = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'records', 'rules', 'audit'} <= names:
            raise ValueError('备份缺少群序数据表')
        required={'group_id','nickname','card','nickname_status','avatar_status'}
        if not required <= {r[1] for r in db.execute('PRAGMA table_info(records)')}:
            raise ValueError('备份结构版本不支持')
        return [json.loads(row[0]) for row in db.execute('SELECT images FROM records')]


def verify_archive(path):
    with Archive(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 50000:
            raise ValueError('备份目录重复或数量过多')
        if any(not _allowed(n) and n != 'manifest.json' for n in names):
            raise ValueError('备份包含不允许的路径')
        if sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
            raise ValueError('备份解压后超过 2 GB')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'lan-group-evidence/1':
            raise ValueError('备份格式不支持')
        expected = manifest['files']
        if set(names) != set(expected) | {'manifest.json'} or 'evidence.sqlite3' not in expected:
            raise ValueError('备份文件清单不一致')
        for name, info in expected.items():
            raw = archive.read(name)
            if len(raw) != info['bytes'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
                raise ValueError('备份文件校验失败：' + name)
        return manifest


def rotate_backups(data, keep=5):
    """Keep today's snapshots and the latest older five; leave unknown files alone."""
    folder = Path(data) / 'backups'
    today = now().strftime('%Y%m%d')
    def stamp(path):
        if re.fullmatch(r'\d{8}-\d{6}-[a-z0-9-]+-[a-f0-9]{8}\.tar\.zst', path.name):
            return path.name[:15]
        return ''
    older = sorted((p for p in folder.iterdir() if p.is_file() and stamp(p) and stamp(p)[:8] < today),
                   key=lambda p: (stamp(p), p.stat().st_mtime_ns, p.name), reverse=True) if folder.exists() else []
    removed = []
    for path in older[keep:]:
        path.unlink()
        removed.append(path.name)
    return removed


def create_backup(data, connect, profiles, label, *, rotate=True, compressed=True):
    folder = data / 'backups'
    folder.mkdir(exist_ok=True)
    label = re.sub('[^a-z0-9-]', '-', label.lower())[:40]
    target = folder / (f'{now():%Y%m%d-%H%M%S}-{label}-{uuid.uuid4().hex[:8]}' + ('.tar.zst' if compressed else '.tar'))
    part = target.with_name(target.name + '.part')
    manifest = {'format': 'lan-group-evidence/1', 'created_at': now().isoformat(), 'files': {}}
    try:
        with closing(sqlite3.connect(':memory:')) as memory, connect() as db:
            db.backup(memory)
            database = memory.serialize()
        with Archive(part, 'w', compressed=compressed) as archive:
            def put(name, raw):
                if not _allowed(name):
                    raise ValueError('文件名不符合留证存储规则：' + name)
                archive.writestr(name, raw)
                manifest['files'][name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            put('evidence.sqlite3', database)
            for file in sorted((data / 'uploads').iterdir()):
                if file.is_file() and not file.name.endswith('.part'):
                    put('uploads/' + file.name, file.read_bytes())
            with profiles.lock:
                for file in sorted(profiles.avatars.iterdir()):
                    if file.is_file() and file.suffix in {'.webp'}:
                        put('avatars/' + file.name, file.read_bytes())
            put('README.txt', '使用 lan-group-evidence restore 备份.tar.zst --data 新目录 恢复。先校验全部文件，恢复到新目录；不会覆盖已有数据。'.encode('utf-8'))
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        verify_archive(part)
        os.replace(part, target)
        if rotate:
            rotate_backups(data)
        return target
    finally:
        part.unlink(missing_ok=True)


def restore_archive(archive_path, destination):
    """Validate first; failed restores leave no apparently usable destination."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('恢复目录已存在，请选择新的空目录路径')
    manifest = verify_archive(archive_path)
    stage = destination.with_name(destination.name + '.restore-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        with Archive(archive_path) as archive:
            for name in manifest['files']:
                target = stage.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        images = _sqlite_check(stage / 'evidence.sqlite3')
        for record in images:
            for image in record:
                relative = str(image.get('url', '')).removeprefix('/')
                if not relative.startswith('uploads/') or not _allowed(relative) or not (stage / relative).is_file():
                    raise ValueError('备份缺少记录引用的证据图片')
        for name, info in manifest['files'].items():
            if hashlib.sha256((stage / name).read_bytes()).hexdigest() != info['sha256']:
                raise ValueError('恢复后的文件校验失败')
        os.rename(stage, destination)
        return manifest
    except BaseException:
        # Stage is a unique sibling created above, never a computed user tree.
        if stage.exists() and stage.parent == destination.parent and '.restore-' in stage.name:
            shutil.rmtree(stage)
        raise
