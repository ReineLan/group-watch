# 工具

| 文件 | 用途 |
| --- | --- |
| `build_support.py` | Python 打包钩子，将已构建前端放入 wheel，由构建系统调用 |
| `check-release.py` | CI 检查版本、发布包、前端及许可证 |
| `export-public.py` | 导出公开源码和示例前端 |
| `group-watch-update.py` | 守护进程检查、应用代码更新，由守护进程调用 |
| `restore-group-workbench.py` | 将备份恢复到新目录 |
| `ds-stats.py` | 从调用日志生成 DeepSeek 统计 |
| `benchmark-workbench.py` | 使用隔离副本比较工作台性能 |

使用方法：

```powershell
uv run python tools/ds-stats.py
uv run python tools/check-release.py versions
uv run python tools/restore-group-workbench.py 备份.tar.zst --destination tmp/restored-workbench
```
