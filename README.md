# Group Watch

<p align="center">
<a href="https://github.com/ReineLan/group-watch/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="license"></a>
<a href="https://github.com/ReineLan/group-watch"><img src="https://img.shields.io/badge/GitHub-ReineLan%2Fgroup--watch-181717?style=flat-square&logo=github" alt="GitHub"></a>
</p>

Group Watch 是面向兰音粉丝群的管理工作台，接收 QQ 消息和 B站直播消息，并记录处罚留档。

## 功能概览

- 汇集 QQ 群消息与直播互动线索，提供上下文、规则筛选、AI 复核和人工处理记录。
- 管理成员资料、处罚档案、禁言跟踪、黑名单、预警、证据图片和操作审计。
- 提供通知、反馈、规则维护、工作台查询、手动备份与恢复。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。从源码构建前端还需要 Node.js 24 LTS；使用已构建的 wheel 运行时不需要 Node.js。SnowLuma 和 QQ 需单独安装、登录并配置。

在项目根目录执行：

```sh
cp config/config.example.json config/config.json
cp config/.env.example config/.env
npm --prefix frontend ci
npm --prefix frontend run build
uv sync --locked
```

配置 `config/config.json` 和 `config/.env`。

将 SnowLuma 放在 `runtime/snowluma/`，完成 QQ 登录与 OneBot WebSocket 适配器配置，禁用 `#sl` 自动回复，然后启动：

```sh
uv run lan serve
```

浏览器打开 <http://127.0.0.1:8066>。

SnowLuma 控制台默认位于 `127.0.0.1:5099`，仅启动 Web 使用 `uv run lan web`。

## 项目结构与文档

技术栈：

- 前端：Vue 3 / Vite / Node.js 24
- 后端：FastAPI / Uvicorn
- 存储：SQLite
- 依赖与构建：uv / setuptools
- 运行时：SnowLuma

目录结构：

```text
.
├── config/            本机配置与密钥
├── data/              证据与业务数据
├── deploy/            Linux 配置、SnowLuma Compose 与 systemd 单元
├── frontend/          前端
│   └── tests/         前端测试
├── logs/              运行日志
├── runtime/           SnowLuma 运行时
├── src/group_watch/   后端
├── tests/             后端测试
└── tools/             构建、导出、备份与统计脚本
```

README 导航：

| 文档 | 内容 |
| --- | --- |
| [数据结构](data/README.md) | SQLite、证据文件、调用日志和业务数据流 |
| [前端结构](frontend/README.md) | Vue 页面、主题系统、请求流程及前端构建 |
| [前端测试](frontend/tests/README.md) | 前端测试范围、模拟方式与画面验收边界 |
| [后端结构](src/group_watch/README.md) | 服务分层、模块职责和后端数据流 |
| [后端测试](tests/README.md) | 后端测试准备、覆盖范围与隔离方式 |
| [工具脚本](tools/README.md) | 构建、公开导出、备份恢复和统计工具 |
| [参与维护](CONTRIBUTING.md) | PR、本地检查、CI、版本与草稿发布流程 |

## 联系

本工具仅供内部管理使用，请确保在合法合规及获得群成员授权的前提下处理数据。

b站：兰兰家的甜筒；qq号：2304368957

## 许可证

本项目：[MIT](LICENSE)；第三方库和素材：[第三方声明](THIRD_PARTY_NOTICES.md)
