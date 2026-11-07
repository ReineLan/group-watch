"""Supervisor update gate. Frontend and dependency changes are built in place before restarting."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'logs/group-watch/update.json'
# These changes need installation or a frontend rebuild before the service restarts.
MAINTENANCE_PATHS = ('pyproject.toml', 'uv.lock', 'frontend', 'tools/build_support.py',
                     'MANIFEST.in', 'THIRD_PARTY_NOTICES.md')
# The service has no writable home; keep package caches inside the ignored checkout.
CACHE = ROOT / '.cache'
MAINT_ENV = dict(os.environ, HOME=str(CACHE), PATH='/usr/local/bin:/usr/bin:/bin',
                 npm_config_cache=str(CACHE / 'npm'), UV_CACHE_DIR=str(CACHE / 'uv'),
                 UV_PYTHON=str(ROOT / '.venv/bin/python'))


def git(*args, retries=0):
    # The supervisor kills this script after a bounded wait, so the retry budget stays small.
    for attempt in range(retries+1):
        try:
            result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=35)
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and not result.returncode:
            return result.stdout.strip()
        if attempt < retries:
            time.sleep(2)
    raise RuntimeError('Git 检查未完成')


def write(status, detail='', **extra):
    value = dict(status=status, detail=detail, ready=status == '准备更新', checked=time.time(), **extra)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    part = STATE.with_suffix('.part')
    part.write_text(json.dumps(value, ensure_ascii=False), 'utf-8')
    part.replace(STATE)
    # Keep the native stdout protocol safe across Windows console code pages.
    print(json.dumps(value, ensure_ascii=True))


def read_state():
    try:
        return json.loads(STATE.read_text('utf-8-sig'))
    except (ValueError, OSError):
        return {}


def step(command, timeout):
    try:
        return subprocess.run(command, cwd=ROOT, env=MAINT_ENV, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        return 124


def maintain(changed):
    """Rebuild whatever the maintenance paths touched; returns an error detail or ''."""
    CACHE.mkdir(exist_ok=True)
    if 'pyproject.toml' in changed or 'uv.lock' in changed:
        if step(['uv', 'sync', '--locked'], 240):
            return '依赖安装失败'
    if any(c == 'frontend' or c.startswith('frontend/') for c in changed):
        if any(c in ('frontend/package.json', 'frontend/package-lock.json') for c in changed) \
                and step(['npm', '--prefix', 'frontend', 'ci', '--no-audit', '--no-fund'], 180):
            return '前端依赖安装失败'
        if step(['npm', '--prefix', 'frontend', 'run', 'build'], 240):
            return '前端构建失败'
        if list(ROOT.glob('frontend/dist/assets/example-*')):
            return '构建使用了占位素材：请先上传 frontend/src/shared/ui/scene/ 中的场景文件'
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/config.json')
    args = parser.parse_args()
    try:
        if Path(git('rev-parse', '--show-toplevel')).resolve() != ROOT.resolve():
            return write('跳过：未配置独立仓库', '独立项目配置自己的 Git 上游后启用自动更新。')
        cfg = json.loads(args.config.read_text('utf-8-sig'))
        if not cfg.get('automatic_updates', True):
            return write('已关闭')
        if git('status', '--porcelain'):
            return write('跳过：有未提交修改', '保存当前工作后再自动更新；不会覆盖或清理本地改动。')
        if args.apply:
            plan = read_state()
            head = git('rev-parse', 'HEAD')
            if plan.get('status') != '准备更新' or head not in (plan.get('before'), plan.get('target')):
                return write('更新计划已失效', '保留当前版本，下轮重新检查。')
            if head == plan['before']:
                git('merge', '--ff-only', plan['target'])
            return write('已自动更新', before=plan['before'], target=plan['target'])
        upstream = git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
        if not upstream.startswith('origin/'):
            return write('跳过：未配置 origin 上游')
        git('fetch', '--no-tags', 'origin', retries=1)
        before, target = git('rev-parse', 'HEAD'), git('rev-parse', '@{upstream}')
        if before == target:
            # A supervisor restart may have lost the drain/apply step; re-arm or rebuild as needed.
            state = read_state()
            if state.get('status') == '准备更新' and state.get('target') == target:
                return write('准备更新', before=state['before'], target=target)
            if state.get('status') in ('构建中', '构建失败'):
                changed = state.get('changed') or list(MAINTENANCE_PATHS)
                error = maintain(changed)
                if error:
                    return write('构建失败', error, changed=changed)
                return write('准备更新', before=state.get('before', before), target=target, changed=changed)
            return write('已是最新版本')
        if git('merge-base', 'HEAD', target) != before:
            return write('跳过：分支无法快进')
        changed = git('diff', '--name-only', before, target, '--', *MAINTENANCE_PATHS).splitlines()
        if changed:
            # Build before signalling readiness: a failed build never takes the site down.
            git('merge', '--ff-only', target)
            write('构建中', changed=changed)
            error = maintain(changed)
            if error:
                return write('构建失败', error, changed=changed)
            return write('准备更新', before=before, target=target, changed=changed)
        write('准备更新', before=before, target=target)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        write('更新检查失败', '检查 Git 上游配置或网络；服务继续使用当前版本。')


if __name__ == '__main__':
    main()
