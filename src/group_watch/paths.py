"""Resolve portable project paths without silently reinterpreting another OS's drive."""
import os
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / 'logs/group-watch'


def resolve_path(value, *, base):
    text = os.fspath(value)
    windows = PureWindowsPath(text)
    if os.name != 'nt' and (windows.drive or text.startswith('\\')):
        raise ValueError('Windows 绝对路径不能在 Linux 使用，请改为项目相对路径或 Linux 绝对路径')
    if os.name == 'nt':
        if (windows.anchor and not windows.is_absolute()) or (text.startswith('/') and not text.startswith('//')):
            raise ValueError('请使用项目相对路径或带盘符的 Windows 绝对路径')
    path = Path(text.replace('\\', '/')).expanduser()
    return (path if path.is_absolute() else Path(base) / path).resolve()
