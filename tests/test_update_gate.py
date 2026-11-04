"""Updates requiring a frontend rebuild must stop before changing the checkout."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('changed', ['frontend/src/app/App.vue', 'tools/build_support.py'])
def test_rebuild_changes_require_manual_update(tmp_path, monkeypatch, apply, changed):
    path = Path(__file__).resolve().parents[1] / 'tools/group-watch-update.py'
    spec = importlib.util.spec_from_file_location('update_gate', path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'automatic_updates': True}), encoding='utf-8')
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'STATE', tmp_path / 'update.json')
    tool.write('准备更新', before='a', target='b')
    monkeypatch.setattr('sys.argv', ['update', '--config', str(config)] + (['--apply'] if apply else []))
    calls = []

    def git(*args):
        calls.append(args)
        if args == ('rev-parse', '--show-toplevel'):
            return str(tmp_path)
        if args == ('status', '--porcelain') or args[0] == 'fetch':
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

    monkeypatch.setattr(tool, 'git', git)
    tool.main()
    state = json.loads(tool.STATE.read_text(encoding='utf-8'))
    assert state['status'] == '等待手动更新'
    assert state['ready'] is False
    assert not any(args[0] == 'merge' for args in calls)
