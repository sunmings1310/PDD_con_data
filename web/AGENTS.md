# Web Module Rules

适用于 `web/`。同时遵守根 [`AGENTS.md`](../AGENTS.md)。

- Web 是管理与观察界面，不得在前端重新定义 Task、Lease、质量、租户或商品成功语义。
- 所有写操作通过受权限控制的 API；路由隐藏和按钮禁用不能替代服务端授权。
- 使用统一 HTTP client 和服务端 DTO；禁止页面各自维护不兼容字段映射或以列表缓存作为事实源。
- Product Snapshot、Raw、动态价格/销量/SKU 和审计事实保持只读；编辑界面只提交明确允许的 Edit DTO。
- 改动 API 消费时补充契约/组件测试（若当前缺测试基础，至少记录并运行 production build）。
- 固定 Node 22.18.x/npm 10.x，使用 `npm ci` 和 `npm run build`；不得通过调高 warning 阈值冒充性能修复。
