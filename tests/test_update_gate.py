"""Updates requiring a rebuild are built in place before the worker restarts."""
import importlib.util
import json
from pathlib import Path

import pytest


def load_tool():
    path = Path(__file__).resolve().parents[1] / 'tools/group-watch-update.py'
    spec = importlib.util.spec_from_file_location('update_gate', path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('changed,fail', [('frontend/src/app/App.vue', False), ('tools/build_support.py', False), ('frontend/src/app/App.vue', True)])
def test_rebuild_updates_are_built_then_applied(tmp_path, monkeypatch, apply, changed, fail):
    tool = load_tool()
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'automatic_updates': True}), encoding='utf-8')
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'STATE', tmp_path / 'update.json')
    tool.write('准备更新', before='a', target='b')
    monkeypatch.setattr('sys.argv', ['update', '--config', str(config)] + (['--apply'] if apply else []))
    calls, builds = [], []

    def git(*args, **kwargs):
        calls.append(args)
        if args == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        if args == ('status', '--porcelain') or args[0] in ('fetch', 'merge'):
            return ''
        if args == ('rev-parse', 'HEAD') or args[0] == 'merge-base':
            return 'a'
        if args == ('rev-parse', '@{upstream}'):
            return 'b'
        if args == ('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'):
            return 'origin/main'
        if args[0] == 'diff':
            assert any(changed == item or changed.startswith(item + '/') for item in args[args.index('--') + 1:])
            return changed
        pytest.fail(f'Unexpected Git operation: {args}')

    def maintain(paths):
        builds.append(paths)
        return '模拟构建失败' if fail else ''

    monkeypatch.setattr(tool, 'git', git)
    monkeypatch.setattr(tool, 'maintain', maintain)
    tool.main()
    state = json.loads(tool.STATE.read_text(encoding='utf-8'))
    if apply:
        assert state['status'] == '已自动更新' and not builds
        assert any(args[:2] == ('merge', '--ff-only') for args in calls)
    elif fail:
        assert state['status'] == '构建失败' and state['ready'] is False and builds == [[changed]]
    else:
        assert state['status'] == '准备更新' and state['ready'] is True and builds == [[changed]]
        assert any(args[:2] == ('merge', '--ff-only') for args in calls)


def test_failed_build_retries_next_check(tmp_path, monkeypatch):
    tool = load_tool()
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'automatic_updates': True}), encoding='utf-8')
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'STATE', tmp_path / 'update.json')
    tool.write('构建失败', '上一次失败', before='a', target='a', changed=['frontend/src/app/App.vue'])
    monkeypatch.setattr('sys.argv', ['update', '--config', str(config)])
    builds = []

    def git(*args, **kwargs):
        if args == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        if args == ('status', '--porcelain') or args[0] == 'fetch':
            return ''
        if args == ('rev-parse', 'HEAD') or args == ('rev-parse', '@{upstream}'):
            return 'a'
        if args == ('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'):
            return 'origin/main'
        pytest.fail(f'Unexpected Git operation: {args}')

    monkeypatch.setattr(tool, 'git', git)
    monkeypatch.setattr(tool, 'maintain', lambda paths: builds.append(paths) or '')
    tool.main()
    state = json.loads(tool.STATE.read_text(encoding='utf-8'))
    assert state['status'] == '准备更新' and state['ready'] is True
    assert builds == [['frontend/src/app/App.vue']]
