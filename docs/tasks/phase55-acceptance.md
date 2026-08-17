# Phase 5.5 企业化硬化验收（2026-08-18）

- [x] 一次性 enrollment token 只存 hash，消费、轮换和撤销具备数据库原子门禁。
- [x] 被撤销设备不能 heartbeat、领取/续租、上报、OTA ack 或投屏发布。
- [x] 账号养护、设备管理、OTA、投屏查看/媒体、Excel 全部接入 TenantContext。
- [x] Active Task、Daily Snapshot、Storage 建立 usage/reservation/ledger，并在写入事务内执行。
- [x] 配额并发路径由 usage 行锁与唯一资源键封闭。
- [x] legacy/default 最终移除条件已冻结在 Phase 5.5 ADR。
- [x] 离线专项测试覆盖跨租户、撤销设备、配额并发和旁路访问。
- [x] 隔离 Oracle Phase 1～5.5 migration、并发、跨租户、撤销和媒体集成套件。

## 最终 Oracle 门禁

- Oracle 19c 隔离 schema 上 `P5_5_001_ENTERPRISE_HARDENING` 首次执行成功，立即重复执行两次均成功；migration 行保持 `applied`、checksum 与 `APPLIED_AT` 不变。
- 两个真实 Enterprise 的 Task ID、搜索、分页、Dashboard、Trace、Snapshot 和 Quarantine 均只返回本租户事实。
- enrollment 一次性消费、重放拒绝、credential 轮换、heartbeat/acquire、revoke 完整链路通过；revoke 后旧 credential、当前 credential、已有投屏连接、OTA 与设备绑定媒体 URL 全部失效。
- Active Task、Daily Snapshot、Storage 三类 quota 均由两个独立 Oracle session 并发争用；每类只允许一个 reservation/commit，另一个收到配额拒绝，usage/reservation/ledger 一致。
- 媒体短签名 URL 的跨租户替换、伪造路径、过期签名和设备 revoke 后访问均被拒绝。
- Phase 5.5 Oracle 专项：`4/4 PASS`；Phase 1～5.5 Oracle 回归：`36/36 PASS`。
- 全量门禁：Python `164/164 PASS`，Android `BUILD SUCCESSFUL`，Web production build `PASS`，统一入口 `PASS=4 FAIL=0 BLOCKED=0`。

## 验收结论

最终 Sol Review 无未关闭的 Phase 5.5 阻塞项。**Phase 5.5 ACCEPTED；Phase 6 UNBLOCKED**。本次只解除门禁，不开始 Phase 6，不合并 PR，等待批准。
