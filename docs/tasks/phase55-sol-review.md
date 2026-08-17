# Phase 5.5 最终 Sol Review（2026-08-18）

## 结论

代码、迁移、真实 Oracle 并发与全量回归均在 Phase 5.5 范围内通过；未进入 Phase 6。**Phase 5.5 ACCEPTED；Phase 6 UNBLOCKED**。

## Review 发现与修复

1. **租户角色与 JWT 全局角色混用**：账号、设备、任务、商品和 Excel 的管理员判断曾读取 `user.role_code`。已改为 `TenantContext.role_code`，避免用户在某 Enterprise 的全局角色扩大另一个 membership 的权限。
2. **撤销后的既有投屏连接**：仅阻止新连接不能终止已建立 publisher。已在 revoke/key rotation 提交后主动断开 publisher/viewer 并清除 room/key 映射。
3. **Excel 服务端图片旁路**：批量导出曾可读取客户端提交的 `/media` 路径。已按当前租户和 Product ID 从数据库重新装载图片路径，再生成签名 URL。
4. **Job 聚合终态配额释放**：Job 聚合直接更新 Task 终态，可能绕过 `transition_task`。已在同一事务补充 Active Task ledger release。
5. **OTA 全局文件互相覆盖**：TenantContext 仅限制 push 不足以隔离 APK。已将 APK/meta 改为 Enterprise/Workspace 目录，并按设备租户返回签名下载 URL。
6. **撤销与 heartbeat 竞态**：active-device 预读后 heartbeat/register 更新可能与 revoke 交错。更新语句增加 `REVOKED_AT IS NULL` 条件和 rowcount 拒绝。
7. **撤销后已签发 OTA URL**：原短签名只绑定租户，设备撤销后旧 URL 在到期前仍可读取。设备 OTA URL 现额外绑定 `device_id`，读取时实时校验相同租户且未撤销；管理端租户媒体 URL 保持原语义。
8. **legacy/default 与序列碰撞**：新 schema 直接写入 ID 1 后，Enterprise/Workspace sequence 的首次值也为 1。`P5_5_001` 现将两个 sequence 提升到存量最大 ID 以上，并在首次/重复 migration 门禁中验证。
9. **全量测试污染 Oracle 环境**：若干离线测试模块在 discovery 时覆盖 `ORACLE_*`，使同进程真实集成用例错误连接 localhost。测试 fixture 改为只补缺失配置，隔离 Oracle 环境保持权威。

## 最终验证

- `P5_5_001` 首次/重复执行：PASS。
- 两 Enterprise 全读取面隔离：PASS。
- enrollment → credential → heartbeat/acquire → revoke，以及旧凭据/既有连接/OTA/投屏失效：PASS。
- 三类 quota 的两 Oracle session 并发 reservation/ledger：PASS。
- 媒体跨租户、伪造、过期、revoke：PASS。
- Python 164、Oracle 36、Android JVM、Web production build：全部 PASS。

`legacy/default` 仍按 ADR 作为兼容迁移保留；其删除是满足冻结退出条件后的独立迁移，不是 Phase 5.5 或 Phase 6 启动阻塞项。
