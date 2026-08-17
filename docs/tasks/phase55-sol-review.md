# Phase 5.5 Sol Review（2026-08-17）

## 结论

代码级 Review 在 Phase 5.5 范围内通过；未进入 Phase 6。真实 Oracle 集成门禁未配置，因此发布/Phase 6 结论仍为有条件。

## Review 发现与修复

1. **租户角色与 JWT 全局角色混用**：账号、设备、任务、商品和 Excel 的管理员判断曾读取 `user.role_code`。已改为 `TenantContext.role_code`，避免用户在某 Enterprise 的全局角色扩大另一个 membership 的权限。
2. **撤销后的既有投屏连接**：仅阻止新连接不能终止已建立 publisher。已在 revoke/key rotation 提交后主动断开 publisher/viewer 并清除 room/key 映射。
3. **Excel 服务端图片旁路**：批量导出曾可读取客户端提交的 `/media` 路径。已按当前租户和 Product ID 从数据库重新装载图片路径，再生成签名 URL。
4. **Job 聚合终态配额释放**：Job 聚合直接更新 Task 终态，可能绕过 `transition_task`。已在同一事务补充 Active Task ledger release。
5. **OTA 全局文件互相覆盖**：TenantContext 仅限制 push 不足以隔离 APK。已将 APK/meta 改为 Enterprise/Workspace 目录，并按设备租户返回签名下载 URL。
6. **撤销与 heartbeat 竞态**：active-device 预读后 heartbeat/register 更新可能与 revoke 交错。更新语句增加 `REVOKED_AT IS NULL` 条件和 rowcount 拒绝。

## 残余门禁

- `T003_ORACLE_TEST_ENABLED` 和隔离 Oracle 凭据未配置，`P5_5_001` 的真实 DDL、回填、两会话配额锁、跨租户 HTTP/WS/媒体集成尚未在本机执行。
- `legacy/default` 的运行时 fallback 按 ADR 保留；只有最终移除条件全部满足后才另起迁移删除。
