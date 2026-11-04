# 数据结构

```text
data/
├── chat-assets/<hash>.webp      # 缓存对话上下文资源
├── group-evidence/
│   ├── avatars/                 # 档案头像
│   ├── uploads/                 # 证据图片
│   ├── backups/
│   └── evidence.sqlite3         # 档案库
├── workbench-backups/
└── group-watch.sqlite3          # 业务状态库

logs/ds-requests/                # deepseek 调用日志（自动复核/登记处理/查询/反馈）
├── automatic-review/
├── registration/
├── query/
└── feedback/
```

# 架构图

```text
QQ / OneBot ───────┐
                  ├─> 来源业务层（正负数区分消息源） ─> 已登记群聊
Bilibili 接入 ─────┘       │
                          ├─> 消息窗口：捕捉、去重、冷却
                          │             │
                          │          DS 复核 ─────> logs/ds-requests 分类日志
                          │             │
                          │      违规 + ≥0.8 + 有效本人证据
                          │             │
                          │             ▼
                          ├─> 业务库 group-watch.sqlite3
                          │     ├─ cases：最终违规及处理
                          │     ├─ case_resources：资源项
                          │     ├─ registered_groups：群登记
                          │     ├─ members：QQ 群成员资料（含已退群成员）
                          │     ├─ monitor_shared_whitelist：白名单
                          │     └─ 通知投递、反馈重试
                          │             │
                          │          人工登记
                          │             ▼
                          └─> 证据库 group-evidence/evidence.sqlite3
                                ├─ records：事件 + 原始昵称/名片 + 资料状态
                                ├─ rules：处理规则
                                └─ audit：档案操作记录
                                      │
                                  WebP 归档图片
```
