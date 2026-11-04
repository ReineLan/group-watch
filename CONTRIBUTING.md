# 参与维护

## PR 格式

从 `main` 建立功能分支，建议一次PR只解决一个可独立验证的问题。标题用 `类型: 具体变化`，例如 `fix: 修复候选队列重复处理` 或 `docs: 补充 Linux 首次部署步骤`。

可用类型为 `feat`、`fix`、`perf`、`refactor`、`test`、`docs`、`build`、`ci`、`chore`。PR正文按自动模板说明问题、变化、验证和兼容性。截图与日志注意脱敏。

## 本地检查

```powershell
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
uv sync --locked --dev
uv run --locked python -m pytest tests -q
```

在项目根目录运行 `uv build` 验证 Python 分发包。

## GitHub Actions

`.github/workflows/ci.yml` 在PR、推送到 `main`、`v*` 标签和手动运行时执行：

1. Node.js 24安装锁定依赖、前端测试和构建，上传前端产物供后续任务使用。
2. Windows / Ubuntu + Python 3.12 下载前端产物后运行后端离线测试。
3. 检查Python、前端和npm锁文件版本一致，构建sdist和wheel，从sdist再构建wheel，在独立环境中检查已安装前端及应用导入，并上传构建产物。

Actions以提交SHA固定版本，默认只读仓库权限。PR不使用仓库密钥、不连接正式业务服务。Dependabot每月检查Actions与npm依赖。

## 版本与草稿发布

采用 `MAJOR.MINOR.PATCH`：兼容修复升PATCH，兼容功能升MINOR，不兼容变化升MAJOR。同步维护：

- `pyproject.toml` 的 `project.version`。
- `frontend/package.json` 的 `version` 与 `frontend/package-lock.json` 中两处根版本。
