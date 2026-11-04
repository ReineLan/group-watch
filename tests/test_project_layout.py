"""The extracted application must work without importing its former host."""
import os
from pathlib import Path
import subprocess
import sys

from group_watch import settings
from group_watch import resources


def test_source_checkout_uses_built_frontend():
    package = Path(settings.__file__).parent
    assert resources.frontend_dist() == package.parents[1] / 'frontend/dist'


def test_installed_resources_use_package_static_directory(tmp_path, monkeypatch):
    package = tmp_path / 'site-packages/group_watch'
    monkeypatch.setattr(resources, '__file__', str(package / 'resources.py'))
    assert resources.frontend_dist() == package / '_static'


def test_import_from_outside_checkout(tmp_path):
    code = "import group_watch.app, sys; assert not any(x == 'lan' or x.startswith('lan.') for x in sys.modules)"
    result = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_relative_configuration_is_project_owned(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ROOT', tmp_path)
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    config = tmp_path/'settings.json'
    config.write_text('{"local_env":"config/.env","db_path":"data/watch.sqlite3","evidence_data":"data/evidence"}', encoding='utf-8')
    cfg = settings.load_settings(config)
    assert Path(cfg.local_env) == tmp_path/'config/.env'
    assert Path(cfg.db_path) == tmp_path/'data/watch.sqlite3'
    assert Path(cfg.evidence_data) == tmp_path/'data/evidence'
