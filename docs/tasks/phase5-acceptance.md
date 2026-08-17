# Phase 5 企业化验收

- 日期：2026-08-17
- 状态：Implemented / Verified
- 决策：`docs/decisions/phase5-product-master-tenancy.md` 方案 C

## 数据与 RBAC 模型

`Enterprise -> Workspace -> EnterpriseMembership(User, Role)` 构成授权边界；可选 WorkspaceMembership 进一步收窄 Workspace。租户角色复用既有 Role/Permission catalog，但权限从当前 EnterpriseMembership 的 `ROLE_ID` 解析，平台 `super_admin` 也不能绕过普通租户数据查询的上下文选择。

全局 `SJZQ_PRODUCT_MASTER` 仅保存平台 identity。`SJZQ_ENTERPRISE_PRODUCT` 为租户可见商品主档；Snapshot、Raw、Quality、Quarantine、Diff、Provenance 和 legacy Product 均归属 Enterprise/Workspace。默认 Diff 链不跨 Workspace，更不跨 Enterprise。

## 隔离策略

- Web 使用 `X-Enterprise-Id/X-Workspace-Id`；服务端验证 membership、Enterprise/Workspace active 状态和 role permission。
- 列表、搜索、COUNT、OFFSET/FETCH、Dashboard、质量指标均把租户谓词放入 Oracle 查询。
- Task、Job、Attempt、Quarantine 等 ID 先以 `(enterprise_id, workspace_id, id)` 检查；跨租户与不存在返回相同空结果/404 语义。
- Android Job acquire 从 Device 绑定租户筛选 Task；后续 Lease identity 同时绑定 Device/Job/Attempt。
- 租户 API 使用 EnterpriseProduct ID，不暴露全局 identity ID；Snapshot predecessor 以 EnterpriseProduct + Enterprise + Workspace 查询。

## Migration

1. `P5_001_ENTERPRISE_TENANCY`：模型、租户列、legacy/default 回填和索引。
2. `P5_002_TENANT_NOT_NULL`：核心私有事实租户键非空。
3. `P5_003_LEGACY_TENANT_DEFAULTS`：保持 Phase 1～4 直接 SQL fixture 兼容；服务写入仍显式传租户。

三项使用固定 checksum、运行状态记录和逐对象保护。真实 Oracle 首次执行、失败恢复以及重复执行均 exit 0。

## 验收证据

- Python 离线回归：155 项通过，Oracle 环境门禁项 12 项按设计跳过。
- Phase 5 契约：7 项通过，覆盖模型、核心列、跨租户 ID、分页/指标、Snapshot 链、migration 和 Web context。
- Oracle Phase 1～5：34 项通过，耗时 88.255 秒；真实两企业跨 ID/分页与 migration 状态 2 项通过。
- Android JVM：`testDebugUnitTest`，BUILD SUCCESSFUL，26 秒。
- Web：Vite production build 成功，1673 modules transformed，7.95 秒。
- P5 migration：首次/续跑 exit 0；`P5_002` 和 `P5_003` 实际 applied。

## GAP 与技术债务

- 配额模型已建立，Workspace 门禁已实施；Active Task、Daily Snapshot、Storage 还需统一 reservation/usage ledger。
- Device enrollment 仍需一次性 token、轮换、撤销和审计。
- 账号养护、OTA、投屏媒体 URL、旧 Excel 兼容导出的所有路径应继续迁入统一 TenantContext；核心租户数据 API 已隔离。
- Oracle 应在后续容量验证中评估组合索引执行计划；不提前引入分区或缓存。

## 成本记录与停止点

- Agent：Sol 主 Agent 1 个；子 Agent 0。
- 外部插件：0。
- 实际执行时间：本会话约 40 分钟；Oracle 最终全套 88.255 秒、Android 26 秒、Web 7.95 秒。
- Token：由会话平台计量；仓库内无权威精确计数，不写估算值。
- 新增 P0：0。
- Phase 6 启动条件：Phase 1～5 回归与核心模型条件满足；仍应先关闭设备 enrollment token 和确认其他平台 adapter 的数据授权边界。当前按要求停止，不启动 Phase 6。
