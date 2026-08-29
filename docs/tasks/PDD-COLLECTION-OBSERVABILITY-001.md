# PDD-COLLECTION-OBSERVABILITY-001：未匹配候选观察证据与 Task Detail 可见性

- **Task ID**：PDD-COLLECTION-OBSERVABILITY-001
- **Title**：未匹配候选观察证据与 Task Detail 可见性
- **Status**：IN_PROGRESS（保留策略已批准，进入实现）

## Goal

目标未匹配时仍向用户展示本次实际观察事实，同时保持 `not_matched` 非成功终态。候选观察不得创建 canonical Product、ProductSnapshot、QualityResult、Quarantine 或成功 Receipt，也不得影响商品资料库、成功统计和质量指标。

## Context

- 起点：已通过代码与真机 Review 的 `PDD-TARGET-MATCH-TERMINAL-001@e15f50f`；该前置 Task 暂停创建 PR。
- 现状：Android 在 `TaskEngine.collectOne()` 已取得详情字段与 Raw evidence，但匹配失败只返回 `CandidateResult.NOT_MATCHED`；服务端只保存 Item 原因，Task Detail 的本次采集结果为 0。
- 产品要求：有候选但不匹配时展示受限候选观察；完全无候选时展示明确的 `no_candidate`；两者均不得冒充采集成功。

## Scope

### Allowed

1. 新增 `candidate_observation` 上报契约，绑定当前 Task/TaskItem/Job/Attempt/Lease、租户/工作区和稳定 idempotency key。
2. 复用 `SJZQ_RAW_COLLECTION` 保存不可变、脱敏、限量的观察证据，`SOURCE_TYPE='candidate_observation'`；不创建第二套 Raw 存储。
3. payload 至少包含：`matched=false`、`candidate_present`、`reason_code`、候选序号、目标字段、观察字段、逐字段比较结果、采集时间、parser/collector 版本和来源摘要。
4. `candidate_present=false / reason_code=no_candidate` 表示完全无候选；不得伪造商品 ID、字段或截图。
5. Management Task results 增加独立 `candidate_observation` result kind，并复用现有 Task-bound Raw resource 下钻。
6. Task Detail 将候选观察与正式结果分区显示，明确“未匹配观察，不进入商品资料库”；无候选时显示可解释 empty state。
7. 每个 TaskItem 最多保存 3 条候选观察，每条结构化 JSON 不超过 64 KiB，最多 1 个脱敏截图引用；超限时保留计数和截断原因。
8. 候选观察写入必须经过当前 lease/attempt fence、tenant/workspace fence、幂等与 ACK；ACK 丢失重放不得重复写。

### Forbidden

- 将未匹配候选写入 Product、ProductSnapshot、QualityResult、Quarantine、成功 Receipt 或成功统计。
- 改变 `not_matched → business_rejection/TARGET_NOT_MATCHED` 与 Task 非 complete 语义。
- Generic SKU、SKU_PANEL runtime、P1 Schema、Phase 6B、购物车、订单、支付、release。
- 保存账号、Token、Cookie、手机号、收货信息、完整页面文本或未脱敏截图/网络包。

## Non-goals

- 不提升搜索召回、排序或自动确认匹配。
- 不建设通用媒体库或第二套观察数据平台。
- 不让候选观察参与 Product diff、Quality KPI 或资料库保存。
- 不自动 merge 前置 Task 或本 Task。

## Dependencies

- 代码依赖：`PDD-TARGET-MATCH-TERMINAL-001` tested code `b5edf6e`；本 Task 使用独立 stacked branch 保留提交边界。
- PR 依赖：前置 Task 未进入 main 前，本 Task 不创建指向 main 的可合并 PR。
- 产品决策：Product Owner 已批准候选观察 Raw 与受控脱敏截图默认保留 30 天，到期删除；永久保留 TaskItem 的 `not_matched` 终态和必要摘要。

## Affected Modules

- Android：`TaskEngine.collectOne`、候选比较结果 DTO、`OutboxPayload`、`AgentCoordinator`、`ApiClient`、Room outbox 与 JVM tests。
- Server：新增候选观察 API/service；复用 `SJZQ_RAW_COLLECTION`；Job lease/tenant/idempotency/quota fence；`management_queries.task_results/resource`。
- Web：`TaskDetail.vue` 候选观察分区、no-candidate empty state、Raw 下钻与权限/stale-request 行为。
- Tests：Android targeted、Python contract/API、Oracle persistence/tenant/idempotency/cleanup、Web mounted component、真机 E2E。

## ADR

最小架构决定候选：复用现有 immutable Raw 事实表，以 `SOURCE_TYPE='candidate_observation'` 区分业务用途；payload 内保存受限比较结构，Task/Job/Attempt 和 tenant/workspace 使用现有列。Management 查询将该 Raw 作为独立 result kind 展示，不创建 Quality/Quarantine/Product/Snapshot。该方案不新增长期状态，不要求 Oracle migration；保留期限确认后在 Task 内形成简短 Accepted ADR/contract note。

## Acceptance Criteria

- [ ] 有候选但不匹配时，至少一条可审计 observation 与对应 TaskItem/Job/Attempt/Raw ID 可追溯，字段差异和拒绝原因可解释。
- [ ] 完全无候选时，Task Detail 显示 `no_candidate`，不伪造候选字段或 Raw 页面内容。
- [ ] 两种路径均保持 Item=`not_matched`、Job/Attempt 非重试失败、Task 非 complete。
- [ ] Product/Snapshot/Quality/Quarantine/成功 Receipt 和成功统计均不增加。
- [ ] 上报受 lease、tenant/workspace、幂等和 payload hash 保护；ACK 丢失重放只产生一条 Raw。
- [ ] 每 Item 的数量、payload、截图均受限；敏感字段扫描通过；来源、采集时间与版本可追踪。
- [ ] Task Detail 明确区分“正式采集结果”和“未匹配候选观察”，候选观察不可选择保存到资料库。
- [ ] tenant/workspace/route 切换的 stale response 不覆盖新上下文；403/404 保持既有不可枚举语义。
- [ ] Android/Python/Web targeted 与 full regression、真实隔离 Oracle、独立 Review、受控真机 E2E 通过。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Android targeted | 待 Dev 固定 | 有候选不匹配、完全无候选、ACK 丢失 | observation outbox 正确且正式结果为 0 | pending |  | BLOCKED |
| Python targeted | 待 Dev 固定 | lease/tenant/idempotency/payload limits | 单一 Raw、无正式业务结果 | pending |  | BLOCKED |
| Web mounted | 待 Dev 固定 | candidate/no_candidate/403/404/stale | 分区和 empty state 正确 | pending |  | BLOCKED |
| Full regression | `scripts/test-baseline.ps1` 分层门禁 | fixed Head | Python/Android/Web 继续通过 | pending |  | BLOCKED |

## Oracle Gate

- Required：Yes
- Reason：复用真实 `SJZQ_RAW_COLLECTION`，涉及 lease/tenant/idempotency/quota/transaction 与 cleanup；虽然当前方案不改 Schema，仍必须运行隔离 Oracle。
- Local isolated environment identifier：项目已批准专用可写可清理 Oracle；不得记录秘密。
- Fixed Head SHA：pending
- Canonical command / test count / literal result hash / exit：pending
- Evidence generated at / expiry：pending
- Four artifacts / rollback / persistent business changes：pending；测试清理必须为 0，persistent=false。
- Hosted evidence validator：pending；GitHub 不连接 Oracle。
- Independent Reviewer provenance check：pending

## Real-device Gate

- Required：Yes
- Device/scenario：既有连续授权；至少覆盖一轮有候选不匹配和一轮完全无候选，不进入 SKU/购物车/订单/支付。
- Command or steps / result：pending

## Rollback

- Code rollback：revert 本 Task commits；保留前置目标门禁 commits。
- Configuration rollback：移除候选观察 runtime 开关/保留策略配置；不改生产配置。
- Data recovery：测试数据按 Task/tenant request key 清理；正式证据按获批保留策略处置，不与 Product/Quality 表级联。
- Irreversible items：无。

## Human Decision Points

- Product Owner 已确认：默认保留 30 天；到期删除候选 Raw 与受控脱敏截图；永久保留 TaskItem `not_matched` 终态和必要摘要；不影响 Product、Snapshot、Quality、资料库或成功统计。
- Schema/migration、改变 Product/Quality/Task 成功语义、PR、merge、release 仍需单独批准。

## Stop Condition

- 实现必须覆盖 30 天清理边界和 TaskItem 摘要保留；若清理需要超出现有 Raw 关系或删除非候选事实，立即停止。
- 若现有 Raw 表无法在不污染质量/产品语义的前提下满足事务、租户或分页性能，提交最小 migration ADR 并暂停。
- Review `ACCEPT`、E2E `PASS` 后停在 Draft PR/merge 批准门禁；不得自动 merge/release。

## Evidence

- Original evidence：`PDD-TARGET-MATCH-TERMINAL-001` 三轮真机 `not_matched`，正式结果与 Raw 均为 0。
- Derived artifacts：`docs/tasks/PDD-COLLECTION-OBSERVABILITY-001-verification/`。
- Review findings：pending
- Commit / PR：pending
