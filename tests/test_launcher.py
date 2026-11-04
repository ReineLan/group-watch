"""Real owned-child cleanup and lifecycle failure regressions; no business data."""
import asyncio
import sys
import time
from types import SimpleNamespace

from loguru import logger
import pytest

from group_watch.launcher import Child
from group_watch.launcher import identity
from group_watch.launcher import matching
from group_watch.launcher import process_lock
from group_watch.maintenance import Maintenance


@pytest.mark.parametrize('snow_ports', [(True,), (False, False), (False, True)])
def test_serve_reuses_external_snowluma_and_only_closes_owned_children(tmp_path, monkeypatch, snow_ports):
    from group_watch import launcher

    snow_root = tmp_path/'runtime/snowluma'
    snow_root.mkdir(parents=True)
    if not snow_ports[0]:
        for name in ('node.exe', 'node', 'index.mjs'):
            (snow_root/name).touch()
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'LOGS', tmp_path)
    monkeypatch.setattr(launcher, 'STATE', tmp_path/'supervisor.json')
    monkeypatch.setattr(launcher, 'configure', lambda *_: None)
    monkeypatch.setattr(launcher, 'load_settings', lambda _: SimpleNamespace(
        db_path=str(tmp_path/'watch.sqlite3'), automatic_updates=False))
    ports = iter(snow_ports)
    monkeypatch.setattr(launcher, 'occupied', lambda port: next(ports) if port == 3001 else False)
    checks = []
    def check_node(*args, **kwargs):
        checks.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(launcher.subprocess, 'run', check_node)
    started, closed = [], []
    class FakeChild:
        def __init__(self, name, *args, **kwargs):
            self.name = name
            self.process = SimpleNamespace(poll=lambda: 0, returncode=0)
            started.append(name)
        def close(self):
            closed.append(self.name)
    monkeypatch.setattr(launcher, 'Child', FakeChild)
    def interrupt(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(launcher.time, 'sleep', interrupt)

    launcher.serve(tmp_path/'config.json', 8066)

    expected = ['SnowLuma', 'Web'] if snow_ports == (False, False) else ['Web']
    assert started == expected
    assert sorted(closed) == sorted(expected)
    assert len(checks) == (0 if snow_ports[0] else 1)
    assert not launcher.STATE.exists()


def test_owned_child_output_and_shutdown(tmp_path):
    captured = []
    sink = logger.add(lambda message: captured.append(str(message)))
    child = Child('fixture', [sys.executable, '-u', '-c',
        "import sys,time; print('stdout-ready'); print('stderr-ready',file=sys.stderr); time.sleep(60)"], tmp_path)
    try:
        for _ in range(100):
            if all(any(text in line for line in captured) for text in ('stdout-ready', 'stderr-ready')):
                break
            time.sleep(.02)
        assert any('stdout-ready' in line for line in captured)
        assert any('stderr-ready' in line for line in captured)
        saved = identity(child.process.pid)
        assert matching(saved) is not None
        assert matching({**saved, 'created':saved['created']+1}) is None
    finally:
        child.close()
        logger.remove(sink)
    assert child.process.poll() is not None
    assert not list(tmp_path.glob('*.log'))


def test_exclusive_instance_lock(tmp_path):
    lock = tmp_path/'instance.lock'
    with process_lock(lock):
        with pytest.raises(RuntimeError, match='已有实例'):
            with process_lock(lock):
                pass
    with process_lock(lock):
        pass


def test_snowluma_output_keeps_inherited_file_handles_without_readers(tmp_path,monkeypatch):
    monkeypatch.setattr('group_watch.launcher.LOGS',tmp_path/'logs')
    child=Child('SnowLuma',[sys.executable,'-u','-c',
        "import sys,time; time.sleep(.05); print('stable-out'); print('stable-err',file=sys.stderr)"],tmp_path,direct_output=True)
    try:
        assert child.process.stdout is None and child.process.stderr is None and not child.readers
        assert child.process.wait(timeout=5)==0
        assert (tmp_path/'logs/snowluma.stdout.log').read_text('utf8').strip()=='stable-out'
        assert (tmp_path/'logs/snowluma.stderr.log').read_text('utf8').strip()=='stable-err'
    finally:
        child.close()


@pytest.mark.asyncio
async def test_failed_backup_does_not_abort_resource_cleanup(tmp_path):
    maintenance = Maintenance(SimpleNamespace(db_path=str(tmp_path/'watch.sqlite3')), None)
    async def failing():
        await asyncio.sleep(0)
        raise OSError('fixture backup failure')
    maintenance.backup_task = asyncio.create_task(failing())
    await maintenance.close()
    assert maintenance.backup_task.done()
