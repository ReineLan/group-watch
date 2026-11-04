# 前端结构（FSD v2.1 架构）

技术栈：Vue 3 + Vite + Node.js 24 LTS。构建产物写入 `dist/`，由 Python 服务提供给浏览器访问。

```text
frontend/
├── src/
│   ├── main.js                           # 取得 CSRF 令牌，创建并挂载 Vue 应用
│   ├── app/
│   │   ├── App.vue                       # 登录状态检查、登录表单和登录/工作区切换
│   │   ├── Workspace.vue                 # 工作台组装、共享状态注入、导航与主题调度
│   │   ├── navigation.js                 # 页面清单、hash 解析和旧 hash 兼容
│   │   ├── theme/                        # 主题状态及场景切换子系统
│   │   │   ├── theme.js                  # 组合资源、队列、切换控制器和诊断
│   │   │   ├── themes.js / assets.js     # 主题配置、颜色 token 和场景资源入口
│   │   │   ├── resources.js / preload.js / sharedVideos.js
│   │   │   │                             # 图片准备状态、预载和共享视频
│   │   │   ├── selection.js / selectionQueue.js
│   │   │   │                             # 选择协调、请求去重和切换排队
│   │   │   ├── sceneTransitions.js / reveal.js
│   │   │   ├── revealDriver.js / revealTargets.js
│   │   │   │                             # 场景状态、圆形动画及动画目标同步
│   │   │   ├── scenePolicy.js            # 窄屏、触屏和减少动态效果策略
│   │   │   ├── paletteRegions.js / paletteWave.js
│   │   │   ├── workspacePalette.js / paletteClock.js
│   │   │   │                             # 区域识别、变色时序和共享渐变时钟
│   │   │   └── diagnostics*.js           # 实验入口、性能记录和诊断输出
│   │   ├── ui/
│   │   │   ├── SidebarNavigation.vue / ThemeSwitcher.vue / ServiceStatus.vue
│   │   │   └── background/
│   │   │       ├── SceneRenderer.vue / BackgroundScene.vue
│   │   │       └── playback.js / parallax.js
│   │   └── styles/                       # 主题变量、工作台布局和控件样式
│   ├── pages/                            # 按页面组织界面和页面专属模型
│   │   ├── overview/                     # 工作总览
│   │   ├── events/                       # 待办线索
│   │   ├── evidence/                     # 禁言跟踪、黑名单与预警、处罚档案、处理办法
│   │   ├── rules/                        # 监控规则
│   │   ├── notifications/                # 通知
│   │   └── maintenance/                  # 运行与恢复
│   ├── entities/                         # 跨页面复用的业务模型和部件
│   │   ├── monitor/model/workspace.js    # 服务状态、刷新、通知及轮询
│   │   └── evidence/                     # 档案状态、记录模型和成员/处罚 UI
│   └── shared/                           # 共用模块
│       ├── api/                          # 请求客户端、CSRF 和会话注入
│       ├── lib/                          # 格式化、视口和绘制时序小工具
│       └── ui/                           # 基础控件、图标、场景示例资源
├── tests/                                # Node 测试、内存 Vue 渲染和依赖边界检查
├── dist/                                 # 本地构建产物
├── package.json / package-lock.json      # 脚本和锁定的前端依赖
└── vite.config.js                        # 插件、资源基路径、代理与构建目录
```

# 架构图

页面与业务请求：

```text
浏览器 ── GET / ──> FastAPI 返回 HTML、CSRF meta 与 /ui/ 构建资源
  │                         ▲
  ├─ main.js 解析 CSRF ─────┘
  ├─ App.vue ─   GET /api/auth/session ─> 检查会话
  │          └─ POST /api/auth/login   ─> 登录后挂载 Workspace
  ▼
Workspace 提供 session / workspace / evidence 状态
  └─ 页面与 entities ─ shared/api/client.js
                         ├─ /api/* ──────────> FastAPI ─> group-watch.sqlite3
                         ├─ /evidence/api/* ─> FastAPI ─> evidence.sqlite3
                         └─ /evidence/* ─────> 头像、上传图片等证据资源
                                                    │
                             JSON / 图片 / 文件响应 <┘
```

主题切换动画管理和时序：

```text
ThemeSystem
├── ThemeManager
│   ├── 主题配置/切换、颜色 Token
│   └── 协调资源准备与过渡控制
│
├── ThemeResourceManager
│   ├── 悬停、聚焦时预解码原图
│   ├── 请求去重与准备状态
│   └── 共享视频资源
│
├── ThemeTransitionController
│   ├── 请求队列 TransitionQueue
│   ├── 动画管理 RevealState、RevealAnimationDriver
│   └── Vue场景管理 SceneLifecycle
│
├── SceneRenderer
│   └── BaseScene + RevealScene × N
│       ├── 背景、视频、动态特效、公共时钟
│       └── 外层 clip-path: circle()、内层 filter: opacity(1)
│
└── UI 颜色呈现
    ├── 区域管理 paletteRegions
    ├── 时序管理 paletteWave
    └── 渐变执行 workspacePalette / paletteClock

用户点击主题
      │
      ▼
ThemeManager
      ├── ThemeResourceManager
      │     └── 按需准备资源，不等待解码完成再响应
      ▼
TransitionQueue
      │  最小启动间隔 260ms；窄屏/触屏最多等待 3 项，其余视口 5 项
      ▼
ThemeTransitionController
      │
      ├── 提交目标主题，创建并发布 RevealState
      │
      ├───────────────────────────────┐
      ▼                               ▼
RevealAnimationDriver          UI 颜色呈现
      │                               │
      │ 950ms 圆形扩散                 ├── paletteRegions
      │                               │   确定一起变色的区域
      ▼                               ├── paletteWave
SceneRenderer                         │   根据圆形几何与扩散曲线
背景 + 视频 + 特效                     │   估算各区域的开始时间
      │                               ▼
      │                        workspacePalette / paletteClock
      │                        区域整体渐变 260ms
      │                        区域内颜色共享一个进度
      ▼
圆形动画完成
      │
      ▼
SceneLifecycle
原场景实例提升为 Base
回收不再需要的场景
```

# 开发、测试与构建

需要 Node.js 24 LTS 和 npm。在 `frontend/` 目录执行：

```powershell
npm ci
npm test
npm run build
```

- `npm ci` 按 `package-lock.json` 安装锁定的前端依赖。
- `npm test` 使用 Node 内置测试运行器执行 `tests/*.test.js`。
- `npm run build` 用 Vite 编译 Vue、样式和资源，写入 `frontend/dist/`。
- `npm run dev` 是持续构建模式（Vite `--watch`），浏览器仍打开 `http://127.0.0.1:8066`，由 Python 服务提供页面。
