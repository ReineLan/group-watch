"""Supervisor update gate. Frontend, packaging and dependency changes need maintenance."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'logs/group-watch/update.json'
# These changes require installation or rebuilding before the service restarts.
MAINTENANCE_PATHS = ('pyproject.toml', 'uv.lock', 'frontend', 'tools/build_support.py',
                     'MANIFEST.in', 'THIRD_PARTY_NOTICES.md')


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=35)
    if result.returncode:
        raise RuntimeError('Git 检查未完成')
    return result.stdout.strip()


def write(status, detail='', **extra):
    value = dict(status=status, detail=detail, ready=status == '准备更新', checked=time.time(), **extra)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    part = STATE.with_suffix('.part')
    part.write_text(json.dumps(value, ensure_ascii=False), 'utf-8')
    part.replace(STATE)
    # Keep the native stdout protocol safe across Windows console code pages.
    print(json.dumps(value, ensure_ascii=True))


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
            plan = json.loads(STATE.read_text('utf-8-sig'))
            if plan.get('status') != '准备更新' or git('rev-parse', 'HEAD') != plan['before']:
                return write('更新计划已失效', '保留当前版本，下轮重新检查。')
            target = plan['target']
            if git('diff', '--name-only', 'HEAD', target, '--', *MAINTENANCE_PATHS):
                return write('等待手动更新', '前端、打包或依赖有变化，需要安装依赖、重新构建前端后再重启。')
            git('merge', '--ff-only', target)
            return write('已自动更新', before=plan['before'], target=target)
        upstream = git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
        if not upstream.startswith('origin/'):
            return write('跳过：未配置 origin 上游')
        git('fetch', '--no-tags', 'origin')
        before, target = git('rev-parse', 'HEAD'), git('rev-parse', '@{upstream}')
        if before == target:
            return write('已是最新版本')
        if git('merge-base', 'HEAD', target) != before:
            return write('跳过：分支无法快进')
        if git('diff', '--name-only', before, target, '--', *MAINTENANCE_PATHS):
            return write('等待手动更新', '前端、打包或依赖有变化，需要安装依赖、重新构建前端后再重启。')
        write('准备更新', before=before, target=target)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        write('更新检查失败', '检查 Git 上游配置或网络；服务继续使用当前版本。')


if __name__ == '__main__':
    main()
