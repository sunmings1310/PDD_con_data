# ADR：Phase 5.5 企业化硬化

- 状态：Accepted / Implemented
- 日期：2026-08-17
- 范围：设备 enrollment、旁路租户边界、配额计量、legacy/default 退出门禁
- 非目标：Phase 6 平台扩展或性能架构

## 决策

1. 新设备只能使用短期、一次性 enrollment bearer 接入。数据库仅保存 SHA-256；消费使用行锁和条件更新。token 可轮换，旧 token 同事务撤销；设备可撤销和轮换 `device_key`。
2. `get_device_by_key` 默认排除 `REVOKED_AT` 非空设备。Heartbeat、Task/Job、商品/图片上报、OTA ack 和投屏发布均复用该门禁。撤销设备时终止当前 Task/Job/Attempt/Lease，避免留下可继续写入的执行权。
3. 账号养护、设备管理、OTA、投屏查看、媒体文件和 Excel 匹配/导出/建任务全部使用服务端 `TenantContext`。OTA 文件按 Enterprise/Workspace 分目录；媒体取消裸 `StaticFiles`，只接受短期租户签名 URL 并核对商品图片归属。
4. Active Task、Daily Snapshot 和 Storage 使用 `SJZQ_QUOTA_USAGE`、`SJZQ_QUOTA_RESERVATION`、`SJZQ_QUOTA_LEDGER`。配额行 `FOR UPDATE` 串行化并发检查，reservation 与业务写入同一 Oracle 事务，ledger 记录 reserve/commit/release/adjust；迁移从持久事实回填初始 usage。
5. 发布迁移为 `P5_5_001_ENTERPRISE_HARDENING`，不修改 Phase 1～5 已发布 migration checksum。

## legacy/default 最终移除条件

只有以下条件同时成立，才允许另起迁移移除 `legacy/default` 和 `P5_003` 默认值；Phase 5.5 不提前删除：

- 连续 30 天生产遥测中，所有新写入均具有非默认 Enterprise/Workspace，`legacy/default` 写入为 0；
- 所有存量设备完成 enrollment 或 device-key 轮换，未 enrollment / 已撤销设备的请求命中率为 0；
- Android、Web、桌面兼容工具、定时任务和离线脚本均不再依赖缺失租户头、`or 1`、`TenantContext(1,1,...)` 或数据库 `DEFAULT 1`；
- Phase 1～5 直接 SQL fixture 已显式写入租户键，真实 Oracle 全量套件在关闭默认值后通过；
- `legacy/default` 私有事实已完成归属迁移或按保留策略清除，计数、总存储和 hash 对账为 0 差异；
- 回滚演练证明可恢复租户映射，但不会恢复无租户写入能力；
- 发布前扫描确认无裸 `/media`、无全局 OTA/Excel 视图、无跨租户资源 ID 旁路。

满足后执行独立 migration：先禁止默认写入并观察，再移除 DEFAULT、删除兼容 fallback，最后在数据清零后删除 legacy Workspace/Enterprise。每一步可单独回滚。

## 成本控制

不新增外部服务或依赖。账本复用 Oracle，投屏仍保持单实例内存中继；只为强一致配额写入增加短行锁和三张轻量表。图片/Raw 才计入 Storage；全局身份表和共享运行制品不重复向租户计费。
