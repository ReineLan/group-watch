"""Export working sources and a rebuilt example UI without local data or Git history."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'AGENTS.md', 'README.md', 'CONTRIBUTING.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
              'MANIFEST.in', 'pyproject.toml', 'uv.lock', '.gitignore', '.gitattributes'}
PUBLIC_FILES = {'data/README.md', 'config/.env.example', 'config/config.example.json',
                'deploy/config.cloud.example.json', 'deploy/snowluma/.env.example',
                'deploy/snowluma/compose.yaml', 'deploy/systemd/group-watch.service'}
SOURCE_DIRS = {'src', 'tests', 'tools', 'frontend', '.github'}


def export(destination):
    destination = destination.resolve()
    if destination.exists() or destination.with_suffix('.zip').exists():
        raise SystemExit('Destination already exists; choose a new directory')
    if destination == ROOT or not destination.is_relative_to(ROOT / 'tmp'):
        raise SystemExit('Export destination must be a new directory under project tmp/')
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('npm is required to build the public UI')
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    destination.mkdir(parents=True)
    for name in sorted(set(paths) - {''}):
        relative = Path(name)
        if relative.parts[0] not in SOURCE_DIRS and name not in ROOT_FILES:
            if name not in PUBLIC_FILES:
                continue
        if any(part in {'dist', 'node_modules', 'local-scene', '__pycache__', '.pytest_cache', '.venv'} for part in relative.parts):
            continue
        if name.startswith('frontend/src/shared/ui/scene/'):
            continue
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    env = dict(os.environ, GROUP_WATCH_PUBLIC_RESOURCES='1')
    subprocess.run([npm, 'run', 'build', '--', '--outDir', str(destination / 'frontend/dist')],
                   cwd=ROOT / 'frontend', env=env, check=True)
    files = [p for p in destination.rglob('*') if p.is_file()]
    forbidden = {'.git', 'local-scene', 'node_modules', 'data', 'logs', 'runtime'}
    for path in files:
        relative = path.relative_to(destination)
        if (forbidden.intersection(relative.parts) and relative.as_posix() != 'data/README.md') or path.name in {'.env', 'config.json'}:
            raise SystemExit('Private path in export: ' + str(relative))
        if path.suffix.lower() in {'.avif', '.mp4', '.sqlite3', '.db'}:
            raise SystemExit('Private media/database in export: ' + str(relative))
    archive = destination.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, path.relative_to(destination).as_posix())
    print(f'Public sources: {destination}\nPublic ZIP: {archive}\nFiles: {len(files)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/github-public')
    export(parser.parse_args().output)
