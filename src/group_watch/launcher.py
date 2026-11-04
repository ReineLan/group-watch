"""Python lifecycle owner for Web and bundled SnowLuma; no PowerShell dependency."""
from group_watch.logging_setup import configure
from group_watch.paths import LOGS
from group_watch.settings import ROOT, load_settings
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

import httpx
from loguru import logger
import psutil


STATE = LOGS / 'supervisor.json'


@contextlib.contextmanager
def process_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('已有实例使用此项目，请先停止原来的服务') from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError('已有实例使用此项目') from None
        yield


def identity(pid):
    proc = psutil.Process(pid)
    return {'pid':pid, 'created':proc.create_time(), 'exe':proc.exe()}


def matching(saved):
    try:
        proc = psutil.Process(saved['pid'])
        return proc if abs(proc.create_time()-saved['created']) < .01 and os.path.normcase(proc.exe()) == os.path.normcase(saved['exe']) else None
    except (psutil.Error, KeyError, TypeError):
        return None


def read_state():
    try:
        value = json.loads(STATE.read_text('utf-8'))
        return value if matching(value) else None
    except (OSError, ValueError):
        return None


def occupied(port):
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) == 0


def stop():
    state = read_state()
    if not state:
        raise RuntimeError('没有发现 Python 守护实例；旧版 PowerShell 实例须从原终端停止')
    control = LOGS / ('stop-'+state['instance'])
    control.touch()
    for _ in range(90):
        if not matching(state):
            print('工作台与自有 SnowLuma 进程已停止；QQ 保持运行。')
            return
        time.sleep(1)
    raise RuntimeError('停止尚未完成，请查看日志；未强杀未确认的进程')


def background(config, port):
    state = read_state()
    if state:
        if state.get('port') != port or state.get('config') != str(config.resolve()):
            raise RuntimeError('此项目已由另一配置或端口运行')
        print(f'已运行：http://127.0.0.1:{port}')
        return
    if occupied(port):
        raise RuntimeError(f'端口 {port} 已被占用，请先停止旧服务')
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    process = subprocess.Popen([sys.executable, '-m', 'group_watch', 'serve', '--config', str(config), '--port', str(port)],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, start_new_session=os.name!='nt')
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError('启动失败，请查看 logs/group-watch 下的 Loguru 日志')
        try:
            health = httpx.get(f'http://127.0.0.1:{port}/api/status', timeout=1, trust_env=False).json()
            state = read_state()
            if state and health.get('project_root') == str(ROOT):
                print(f'已启动：http://127.0.0.1:{port}（Python 守护 PID {state["pid"]}）')
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(1)
    # This handle is ours, but leave an unready supervisor available for diagnosis/stop.
    raise RuntimeError('启动尚未就绪，请查看日志；可用 group-watch stop 停止本次实例')


def pipe_output(stream, source, *, protocol=False):
    for line in stream:
        line = line.rstrip()
        if not line:
            continue
        level = 'INFO'
        if protocol:
            try:
                data = json.loads(line)
                level, line = data['level'], data['message'].rstrip()
            except (ValueError, KeyError, TypeError):
                pass
        logger.log(level, '{} | {}', source, line)
    stream.close()


class Child:
    def __init__(self, name, args, cwd, *, protocol=False, direct_output=False):
        self.name = name
        with contextlib.ExitStack() as outputs:
            stdout = stderr = subprocess.PIPE
            if direct_output:
                # SnowLuma must keep writable handles even if its supervisor exits.
                LOGS.mkdir(parents=True,exist_ok=True)
                stdout=outputs.enter_context((LOGS/'snowluma.stdout.log').open('ab'))
                stderr=outputs.enter_context((LOGS/'snowluma.stderr.log').open('ab'))
            self.process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, text=True, encoding='utf-8', errors='replace',
                env={**os.environ, 'PYTHONUTF8':'1', 'GROUP_WATCH_MANAGED':'1'},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.saved = identity(self.process.pid)
        self.readers = []
        for stream in (self.process.stdout, self.process.stderr):
            if stream is None: continue
            reader = threading.Thread(target=pipe_output, args=(stream,name), kwargs={'protocol':protocol}, daemon=True)
            reader.start(); self.readers.append(reader)
        logger.info('{} 已启动，PID {}', name, self.process.pid)

    def close(self):
        if self.process.poll() is None:
            proc = matching(self.saved)
            if proc is None:
                raise RuntimeError(f'无法确认自有 {self.name} 进程身份')
            # Children include the Windows venv executable redirector, never QQ's parent tree.
            children = proc.children(recursive=True)
            for child in reversed(children):
                with contextlib.suppress(psutil.NoSuchProcess): child.terminate()
            with contextlib.suppress(psutil.NoSuchProcess): proc.terminate()
            _, alive = psutil.wait_procs([*children,proc], timeout=5)
            for child in alive:
                with contextlib.suppress(psutil.NoSuchProcess): child.kill()
            self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=2)


def graceful_web(port):
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=3) as client:
            status = client.get('/api/status').json()
            if status.get('project_root') != str(ROOT):
                return False
            token = client.get('/api/maintenance/update-token').json()['token']
            return client.post('/api/maintenance/shutdown', headers={'x-csrf-token':token}).is_success
    except (httpx.HTTPError, ValueError, KeyError):
        return False


def update(port, config):
    command = [sys.executable, str(ROOT/'tools/group-watch-update.py'), '--config', str(config)]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
        if not json.loads(result.stdout).get('ready'):
            return False
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=3) as client:
            if client.get('/api/status').json().get('counts', {}).get('open', 0):
                return False
            token = client.get('/api/maintenance/update-token').json()['token']
            headers = {'x-csrf-token':token}
            client.post('/api/maintenance/drain', headers=headers).raise_for_status()
            client.post('/api/maintenance/restart', headers=headers).raise_for_status()
        return True
    except (OSError, subprocess.SubprocessError, httpx.HTTPError, ValueError, KeyError):
        logger.warning('更新检查未完成，服务继续运行')
        return False


def serve(config, port):
    configure(LOGS)
    cfg = load_settings(config)
    with process_lock(Path(cfg.db_path).with_suffix('.supervisor.lock')):
        if occupied(port):
            raise RuntimeError('Web 端口已被占用，请先停止旧版实例')
        external_snow = occupied(3001)
        snow_root = ROOT/'runtime/snowluma'
        node = snow_root/('node.exe' if os.name=='nt' else 'node')
        if not external_snow:
            if not node.is_file() or not (snow_root/'index.mjs').is_file():
                raise RuntimeError('缺少 runtime/snowluma 运行文件')
            check = subprocess.run([str(node), str(snow_root/'check-node-version.cjs')], capture_output=True, timeout=20)
            if check.returncode:
                raise RuntimeError('SnowLuma Node 版本检查失败')
        else:
            logger.info('复用 3001 端口上的 SnowLuma；本守护不负责启动或停止它')
        instance = uuid.uuid4().hex
        control = LOGS/('stop-'+instance)
        value = {**identity(os.getpid()), 'instance':instance, 'port':port, 'config':str(config.resolve())}
        STATE.write_text(json.dumps(value), 'utf-8')
        snow = web = None
        next_snow = next_web = 0
        next_update = time.monotonic()+5
        delays = {'Web':5, 'SnowLuma':5}
        apply_update = False
        try:
            logger.info('统一工作台启动：http://127.0.0.1:{}', port)
            while not control.exists():
                now = time.monotonic()
                if snow and snow.process.poll() is not None:
                    logger.warning('SnowLuma 退出（{}），{} 秒后重启',snow.process.returncode,delays['SnowLuma'])
                    snow.close(); snow=None; next_snow=now+delays['SnowLuma']; delays['SnowLuma']=min(60,delays['SnowLuma']*2)
                if web and web.process.poll() is not None:
                    logger.warning('Web 退出（{}），{} 秒后重启',web.process.returncode,delays['Web'])
                    web.close(); web=None; next_web=now+delays['Web']; delays['Web']=min(60,delays['Web']*2)
                    if apply_update:
                        subprocess.run([sys.executable,str(ROOT/'tools/group-watch-update.py'),'--config',str(config),'--apply'],cwd=ROOT,timeout=90,stdout=subprocess.DEVNULL)
                        apply_update=False
                if not external_snow and snow is None and now>=next_snow:
                    # Recheck before spawning, including after a managed child exits.
                    if occupied(3001):
                        external_snow = True
                        logger.info('3001 端口已有服务，转为复用；停止时保留该进程')
                    else:
                        snow=Child('SnowLuma',[str(node),str(snow_root/'index.mjs')],snow_root,direct_output=True)
                if web is None and now>=next_web:
                    web=Child('Web',[sys.executable,'-m','group_watch','_worker','--config',str(config),'--port',str(port)],ROOT,protocol=True)
                if cfg.automatic_updates and now>=next_update and web and occupied(port):
                    next_update=now+3600
                    apply_update=update(port,config)
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info('收到停止请求')
        finally:
            if web and web.process.poll() is None:
                # Finish in-flight backup/query before graceful shutdown (bounded wait).
                for _ in range(60):
                    if graceful_web(port): break
                    if web.process.poll() is not None: break
                    time.sleep(1)
                with contextlib.suppress(subprocess.TimeoutExpired): web.process.wait(timeout=15)
            try:
                if web: web.close()
            finally:
                try:
                    if snow: snow.close()
                finally:
                    control.unlink(missing_ok=True)
                    STATE.unlink(missing_ok=True)
                    logger.info('自有进程已清理，工作台已停止')
