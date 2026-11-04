# 后端测试

部分接口测试需要静态页面，需要先构建前端：

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
uv run --locked python -m pytest tests -q
```

| 范围 | 测试 |
| --- | --- |
| 消息、规则、复核与通知 | `test_group_watch.py`、`test_monitoring_persistence.py`、规则及来源相关测试 |
| 档案、登记与资源 | `test_group_evidence_*.py`、`test_chat_registration.py`、`test_resource_import_refinements.py` |
| 资料原值、状态与媒体 | `test_profile_values.py`、`test_storage_values.py`、`test_media.py` |
| QQ 成员资料和采集 | `test_members.py` |
| 模型日志与统计 | `test_ds_audit.py`、`test_ds_log_lifecycle.py`、`test_ds_stats.py` |
| 启动、更新与部署 | `test_launcher.py`、`test_update_gate.py`、`test_project_layout.py`、`test_portable_deployment.py` |

数据库、日志与图片使用临时目录，外部服务使用模拟接口。
