# Phase 5.5 企业化硬化验收

- [x] 一次性 enrollment token 只存 hash，消费、轮换和撤销具备数据库原子门禁。
- [x] 被撤销设备不能 heartbeat、领取/续租、上报、OTA ack 或投屏发布。
- [x] 账号养护、设备管理、OTA、投屏查看/媒体、Excel 全部接入 TenantContext。
- [x] Active Task、Daily Snapshot、Storage 建立 usage/reservation/ledger，并在写入事务内执行。
- [x] 配额并发路径由 usage 行锁与唯一资源键封闭。
- [x] legacy/default 最终移除条件已冻结在 Phase 5.5 ADR。
- [x] 离线专项测试覆盖跨租户、撤销设备、配额并发和旁路访问。
- [ ] 隔离 Oracle Phase 5/5.5 migration、并发与跨租户集成套件（当前环境未配置）。

停止点：完成回归与 Sol Review 后停止，不进入 Phase 6。
