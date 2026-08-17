# Phase 2 执行计划：任务系统稳定

> 日期：2026-08-17
> 分支：`codex/phase2-task-stability`
> ADR：`../decisions/phase2-job-attempt-lease.md`

## 工作包

| ID | 内容 | 依赖 | 推荐 Agent | 并行 |
|---|---|---|---|---:|
| P2-001 | Task/Job/Attempt/Lease/Checkpoint/Outbox ADR 与状态机 | Phase 1 | Sol | 否 |
| P2-002 | Oracle additive schema、索引、约束与迁移 | P2-001 | Terra | 是 |
| P2-003 | Job/Attempt/Lease acquire/start/heartbeat/guard API | P2-001/002 | Terra + Sol review | 是 |
| P2-004 | Task 创建幂等生成 Job；Pause/Resume/Cancel 聚合 | P2-002/003 | Terra | 否 |
| P2-005 | Checkpoint、结果提交和 Task 聚合事务 | P2-003/004 | Sol | 否 |
| P2-006 | Retry 分类、timeout、reclaim、reconciliation | P2-003 | Terra | 是 |
| P2-007 | Android Attempt/Lease/Checkpoint 本地缓存与 API | P2-003/005 | Terra | 是 |
| P2-008 | WorkManager + Foreground Service + Boot/app/network 恢复 | P2-007 | Terra | 否 |
| P2-009 | 18 类故障注入、Oracle 并发和 Android 生命周期测试 | P2-003..008 | Luna 测试 + Sol review | 部分 |
| P2-010 | 全量回归、Code Review、GAP/架构/验收报告 | 全部 | Sol | 否 |

## Phase 边界

本阶段不实施 Enterprise/Workspace、ProductSnapshot 全量模型、其他平台 Collector、完整管理 UI 或大规模前端重构。旧桌面采集保持隔离，只记录协议边界。

## 验收证据要求

每项实现必须同时具备：

1. 纯状态/策略单测；
2. Fake DB/API 事务与错误码测试；
3. 需要 Oracle 语义的多连接真实集成测试；
4. Android Room/MockWebServer/Robolectric 生命周期测试；
5. 统一严格入口继续覆盖 Phase 1；
6. 可重复故障输入、明确终态和无残留检查。

## 故障矩阵

| # | 场景 | 预期确定结果 |
|---:|---|---|
| 1 | Worker 执行中断网 | Lease 到期 reclaim；无永久 running |
| 2 | 上传时断网 | Outbox 重放；业务结果唯一 |
| 3 | Heartbeat 丢失 | Lease 过期；旧 heartbeat `STALE_LEASE` |
| 4 | App 被 kill | 本地 outbox 保留；服务端 reclaim |
| 5 | Agent 进程崩溃 | 不 finish 假失败；恢复查询服务端 |
| 6 | 完成后 ACK 丢失 | 重放返回 receipt；无重复完成 |
| 7 | Server 500 | 有限 backoff；不 Complete |
| 8 | 同 Worker 重复 acquire | 最多一个 active Attempt |
| 9 | 两设备抢同 Job | 仅一个有效 Lease |
| 10 | Lease 刚过期旧提交 | `STALE_LEASE`，无副作用 |
| 11 | 新 Worker reclaim 后旧 Worker 恢复 | 新 Attempt 权威，旧写拒绝 |
| 12 | Pause 时有 running Job | 禁止新分配，安全 checkpoint/yield 或等待 reclaim |
| 13 | Resume | 从确认 checkpoint 重新 pending/acquire |
| 14 | Checkpoint 前崩溃 | 从上一确认版本恢复 |
| 15 | Checkpoint 后 ACK 丢失 | 同 key 重放，版本不前进两次 |
| 16 | 服务端重启 | DB Lease 保留，按 DB 时间 reconciliation |
| 17 | DB 短暂异常 | 整个事务回滚，无半写 |
| 18 | Outbox 重复投递 | event/receipt 唯一，副作用一次 |

所有故障统一断言：无静默丢失、无错误 Complete、无重复业务结果、旧 Attempt 不覆盖新 Attempt、Job 最终进入确定状态。
