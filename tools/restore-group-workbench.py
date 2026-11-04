"""Verify a workbench backup and restore into a NEW destination."""
import argparse
import json
from pathlib import Path
import shutil
import uuid
from group_watch.evidence.archive_container import Archive

from group_watch.maintenance import verify_backup
from group_watch.evidence.archives import restore_archive


def restore(archive, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('恢复目录已存在，请选择新目录')
    verify_backup(archive)
    stage = destination.with_name(destination.name + '.restore-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        with Archive(archive) as container:
            package = stage / 'evidence.tar'
            package.write_bytes(container.read('evidence.tar'))
        restore_archive(package, stage / 'group-evidence')
        package.unlink()
        stage.rename(destination)
    finally:
        if stage.exists() and stage.parent == destination.parent and '.restore-' in stage.name:
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    restore(args.archive, args.destination)
    print(json.dumps({'ok': True, 'destination': str(args.destination)}, ensure_ascii=False))
