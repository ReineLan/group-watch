"""Offline release checks used by CI; never opens runtime configuration or databases."""
import argparse
import copy
from email.parser import BytesParser
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def check_versions():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf8'))['project']
    package = json.loads((ROOT / 'frontend/package.json').read_text(encoding='utf8'))
    lock = json.loads((ROOT / 'frontend/package-lock.json').read_text(encoding='utf8'))
    versions = [project['version'], package['version'], lock['version'], lock['packages']['']['version']]
    require(len(set(versions)) == 1, f'Package versions disagree: {versions}')
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/tags/'):
        require(ref == f"refs/tags/v{versions[0]}", f'Tag {ref} does not match version {versions[0]}')
    print(f'Version consistency: {versions[0]}')
    return project


def check_paths(paths):
    private_roots = {'.git', '.venv', 'data', 'runtime', 'logs', 'tmp', 'build', 'node_modules'}
    for name in paths:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts, f'Unsafe archive path: {name}')
        require(path.parts and path.parts[0] not in private_roots, f'Private runtime path: {name}')
        require(path.name not in {'.env', 'config.json'}, f'Local configuration in distribution: {name}')
        require(not path.name.endswith(('.sqlite', '.sqlite3', '.db', '.pyc')), f'Runtime file: {name}')
        require(path.name not in {'连接到云端.md', 'QQ群成员筛查复查报告.md'}, f'Private report: {name}')


def check_distributions(directory, extract_to):
    project = check_versions()
    wheels = list(directory.glob('*.whl'))
    sources = list(directory.glob('*.tar.gz'))
    require(len(wheels) == len(sources) == 1, 'Expected exactly one wheel and one source distribution')
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        check_paths(names)
        metadata_files = [name for name in names if name.endswith('.dist-info/METADATA')]
        require(len(metadata_files) == 1, 'Missing or ambiguous wheel metadata')
        metadata = BytesParser().parsebytes(wheel.read(metadata_files[0]))
        require(metadata['Name'] == project['name'], 'Wheel project name differs')
        require(metadata['Version'] == project['version'], 'Wheel version differs')
        require(metadata['License-Expression'] == project['license'], 'Wheel license expression differs')
        dist_info = metadata_files[0].rsplit('/', 1)[0]
        for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md']:
            require(wheel.read(f'{dist_info}/licenses/{name}') == (ROOT / name).read_bytes(),
                    f'Missing or changed license: {name}')
        source_ui = ROOT / 'frontend/dist'
        require((source_ui / 'THIRD_PARTY_NOTICES.md').read_bytes() ==
                (ROOT / 'THIRD_PARTY_NOTICES.md').read_bytes(),
                'Frontend third-party notices differ from the root document; rebuild the frontend')
        expected = {p.relative_to(source_ui).as_posix() for p in source_ui.rglob('*') if p.is_file()}
        actual = {name.removeprefix('group_watch/_static/') for name in names
                  if name.startswith('group_watch/_static/') and not name.endswith('/')}
        require(actual == expected, 'Wheel UI differs from frontend/dist file list')
        for name in expected:
            require(wheel.read(f'group_watch/_static/{name}') == (source_ui / name).read_bytes(),
                    f'Wheel UI content differs: {name}')
    with tarfile.open(sources[0], 'r:gz') as source:
        members = source.getmembers()
        roots = {PurePosixPath(m.name).parts[0] for m in members}
        require(len(roots) == 1, 'Source archive must have one root directory')
        stripped = []
        for member in members:
            require(member.isfile() or member.isdir(), f'Unexpected archive member: {member.name}')
            relative = PurePosixPath(*PurePosixPath(member.name).parts[1:]).as_posix()
            if relative == '.':
                continue
            item = copy.copy(member)
            item.name = relative
            stripped.append(item)
        names = {m.name for m in stripped}
        check_paths(names)
        for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md',
                     'pyproject.toml', 'uv.lock', 'config/config.example.json', 'config/.env.example',
                     'tools/build_support.py', 'frontend/dist/index.html',
                     'frontend/dist/THIRD_PARTY_NOTICES.md']:
            require(name in names, f'Source distribution is missing {name}')
        if extract_to is not None:
            destination = extract_to.resolve()
            require(not destination.exists(), f'Extraction destination already exists: {destination}')
            destination.mkdir(parents=True)
            source.extractall(destination, members=stripped, filter='data')
    print('Distribution contents, bundled UI, licenses and private-file checks: OK')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('versions')
    distributions = commands.add_parser('distributions')
    distributions.add_argument('directory', type=Path)
    distributions.add_argument('--extract-to', type=Path)
    args = parser.parse_args()
    if args.command == 'versions':
        check_versions()
    else:
        check_distributions(args.directory, args.extract_to)


if __name__ == '__main__':
    main()
