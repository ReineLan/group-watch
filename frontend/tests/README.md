# 前端测试

在 `frontend/` 运行：

```powershell
npm test
npm run build
```

| 范围 | 测试 |
| --- | --- |
| 档案、表单、请求与弹窗 | `workspace.test.js`、`workspace-teleport.test.js`、`csrf.test.js` |
| 切换队列、动画完成与取消 | `selection-queue.test.js`、`scene-instances.test.js`、`reveal-*.test.js` |
| 卡片颜色、遮罩与区域释放 | `palette-*.test.js`、`workspace-palette.test.js`、`appearance-masks.test.js` |
| 图片、视频与场景 | `interaction-performance.test.js`、`parallax.test.js`、`scene-appearance-regressions.test.js` |
| 主题配置、依赖与诊断隔离 | `theme.test.js`、`imports.test.js`、`theme-diagnostics.test.js` |

使用 Node 测试运行器、模拟时钟和内存中的 Vue 渲染器。动画测试验证状态、时序和资源释放，实际画面由人工验收。
