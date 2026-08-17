# ADR：Phase 2 Task / Job / Attempt / Lease / Checkpoint / Outbox

- 状态：Implemented / Verified
- 日期：2026-08-17
- 决策者：Phase 2 Sol Tech Lead
- 范围：Android/FastAPI/Oracle 的服务端调度采集链；旧桌面采集链保持隔离
- 前置：`phase1-success-data-contract.md`

## 1. 背景与目标

Phase 1 已保证“商品和图片全部得到服务端确认后 Task 才能完成”，但执行所有权仍以 Task/Device 为中心，缺少可过期 Lease、独立 Attempt、权威 Checkpoint 和服务端 reconciliation。Phase 2 要保证断网、进程/App/Worker 崩溃、设备掉线、超时、重复请求及服务重启后，工作不会永久卡死，旧执行者不会覆盖新执行者，已确认结果不会重复。

本 ADR 不引入 Enterprise/Workspace、ProductSnapshot 全量迁移、其他平台 Collector 或管理后台重构。

## 2. 核心对象和职责

### 2.1 CollectionTask

用户层面的目标和聚合对象，对应现有 `SJZQ_TASK`。

负责：

- 用户输入、平台、审核、优先级和总体 deadline；
- 是否允许调度（审核、用户 pause）；
- Job 聚合进度和最终状态；
- 所有必要 Job 到达确定终态后的最终完成条件。

不负责：Worker、Lease token、某次错误、某次开始/结束时间或重试退避。Task 的 `STATUS` 继续表达总体生命周期；`PAUSE_STATE` 独立表达用户主动暂停，避免把系统降载、设备不可用和 retry wait 都映射为 paused。

### 2.2 CollectionJob

可独立执行、重试、恢复的最小业务单元。Phase 2 首个实现以一个 Task Item/关键词为一个 `collect_item` Job；没有 Task Item 的兼容任务生成一个 `collect_task` Job。后续可增加 `search_page/detail/upload/sku_set`，但本阶段不拆分 UI 动作流水线。

Job identity 是稳定的 `JOB_KEY`：

```text
collect_item: task/{task_id}/item/{task_item_id}
collect_task: task/{task_id}/default
```

同一业务 Job 在 Worker/App 重启后 identity 不变。创建使用唯一约束幂等；Attempt 重建不改变 Job 含义。

Job 保存目标 payload、状态、优先级、最大尝试数、下次可运行时间、最新确认 Checkpoint、当前有效 Attempt，以及结果关联。Job 不保存某次执行日志的全部历史。

### 2.3 CollectionAttempt

Job 的一次执行尝试。每次成功 acquire/reclaim 都创建新的 Attempt，并递增 `ATTEMPT_NO`。

Attempt 记录：

- device_id、worker_id、lease_token、trace_id；
- leased/started/heartbeat/expires/ended 时间；
- attempt status；
- error class/code/message、retryable、backoff；
- 起始和最终 checkpoint version。

Attempt 不等于 Job。Attempt timeout/reclaimed 后 Job 可以回到 `retry_wait/pending`，历史 Attempt 保持终态审计记录。

### 2.4 Lease

Lease 是 Attempt 的限时执行权。`SJZQ_COLLECTION_LEASE` 保存租约的不可变身份、当前 active/released/reclaimed 状态和释放原因；Attempt 保存执行历史，Job 镜像 `ACTIVE_ATTEMPT_ID/LEASE_TOKEN_HASH/LEASE_EXPIRES_AT` 以便单行原子校验。三处只能在同一事务内一起变化，提交权限始终以锁定后的 Job active identity 与 active Lease 联合校验为准，禁止把 Lease 表实现成可独立漂移的第二套所有权。

Lease identity：`(job_id, attempt_id, lease_token)`。所有 heartbeat、checkpoint、progress、product/image result、complete/fail 都必须带该 identity。服务端使用数据库时间 `SYSTIMESTAMP`，不信任 Worker 时钟。

### 2.5 Checkpoint

Checkpoint 只表示服务端已经确认的进度，不表示 Worker 的 UI 光标估计。

首版 Android payload 只记录服务端已经确认上传的稳定采集槽位；槽位由关键词和确定性的采集位置组成：

```json
{
  "local_status": "running|paused|complete",
  "confirmed_slots": ["keyword|default_top_1", "keyword|price_asc_first"]
}
```

每个 Job 使用单调 `VERSION`，并保存 history。槽位只有在对应 product receipt 已收到服务端 ACK 后才进入 Checkpoint；恢复时服务端返回 `CHECKPOINT_JSON`，Android 同时合并本地已 ACK outbox，已确认槽位不会再次生成业务结果。Checkpoint 请求有稳定 idempotency key 和 payload hash：同 key 同 payload返回既有结果；同 key 不同 payload冲突；低于当前 version 的乱序写拒绝。后续真正分页 Collector 可在不改变协议的前提下增加 `sort/page_or_cursor/last_confirmed_item`。

### 2.6 Outbox

Android Room Outbox 是“需要向服务端交付的意图”，不是全局真相。服务端 receipt 是确认事实；Oracle Job/Attempt/Lease 是执行真相。App 重启后先恢复本地 outbox，再查询服务端 active lease/recoverable work，二者按服务端 lease identity 对齐。过期 lease 的本地事件进入 rejected/dead-letter，不能恢复旧执行权。

## 3. 状态模型

### 3.1 Job 状态

| 状态 | 语义 | 可分配 |
|---|---|---:|
| `pending` | 已创建、满足依赖且可立即领取 | 是 |
| `leased` | Attempt 已创建并持有 Lease，Worker 尚未确认开始 | 否 |
| `running` | 当前 Lease 持有者已开始执行 | 否 |
| `paused` | 用户暂停后，Job 已安全释放执行权并保留 Checkpoint | 否 |
| `retry_wait` | transient failure/reclaim 后等待 `NEXT_RUN_AT` | 否；reconciliation 到期后转 pending |
| `success` | 业务结果和必要 receipt 已确认 | 否，终态 |
| `failed` | permanent error 或尝试上限耗尽 | 否，终态 |
| `cancelled` | Task/Job 被用户取消 | 否，终态 |
| `dead` | 系统无法自动判定一致性，需要人工处理 | 否，终态 |
| `quarantined` | 数据质量/认证/人工验证阻断，保留证据待处置 | 否，终态 |

`dead` 仅用于执行/一致性损坏；`quarantined` 仅用于可解释的业务/质量/人工介入。两者不作为普通 retry 上限的同义词。

### 3.2 Attempt 状态

`leased → running → success|failed|timeout|cancelled|reclaimed`。`leased` 可直接到 `failed/timeout/cancelled/reclaimed`。所有终态不可修改，迟到请求返回稳定冲突。

### 3.3 允许的 Job 转换

```text
pending    -> leased | paused | cancelled
leased     -> running | retry_wait | paused | failed | cancelled | dead
running    -> success | retry_wait | paused | failed | cancelled | quarantined | dead
paused     -> pending | cancelled
retry_wait -> pending | paused | failed | cancelled | dead
```

同状态重复是幂等读取，不重复副作用。其他转换禁止。

转换执行者：

- acquire：调度服务；
- leased→running/heartbeat/checkpoint/result：当前 Lease 持有者；
- retry_wait：当前持有者 fail 或 reconciliation reclaim；
- pause/resume/cancel：授权用户 API；
- timeout/reclaimed/dead：reconciliation；
- success：当前持有者提交且结果 receipt/完成条件满足；
- quarantined：质量/认证/人工介入分类器。

## 4. 原子 Lease 协议

### 4.1 Acquire

单一事务和锁顺序：

1. 选择候选 Task/Job：`FOR UPDATE SKIP LOCKED`；Task 必须 approved、非用户暂停、非终态；Job 必须为 `pending`。到期 `retry_wait` 只能由 reconciliation 正式迁移为 `pending`，acquire 不绕过状态机。
2. 锁 Device（按 `DEVICE_ID`），确认设备未持有其他 active Job；
3. 锁 Task；
4. 锁 Job；
5. 再次校验状态/时间；
6. 生成 Attempt ID、随机 256-bit lease token 和 trace ID；
7. INSERT Attempt；
8. UPDATE Job 为 `leased` 并写 active lease 镜像；
9. UPDATE Device active attempt/job；
10. commit 后返回。

并发 Worker 通过行锁/`SKIP LOCKED` 分流，同一 Job 同时只有一个 active Attempt。不得采用“先 SELECT pending，再无条件 UPDATE”。

### 4.2 Start / Heartbeat

Start 将当前 Attempt/Job 从 leased 转 running。Heartbeat 使用条件：

```text
job.active_attempt_id = request.attempt_id
job.lease_token = request.lease_token
attempt.status in (leased,running)
lease_expires_at > database_now - allowed_grace
```

重复 heartbeat 只把过期时间延长到 `max(current_expiry, database_now + lease_duration)`，不缩短 Lease。已 reclaim 的 token 返回 `STALE_LEASE`，不恢复执行权。

### 4.3 Result / Complete

所有副作用前先按 Device → Task → Job → Attempt 锁顺序验证当前 Lease。商品/图片 receipt、Checkpoint、Job success 和 Task 聚合在同一事务或通过稳定 receipt 分步确认；最后一步只认可数据库已持久化 receipt。一个关键词 Job 可以产生多个商品，Android 完成时提交全部已确认 product receipt manifest；服务端逐项验证并以 TaskItem 已绑定商品为 canonical result。任一商品永久拒绝则 Job 进入 `data_quality` 失败路径；零确认结果进入 `business_rejection/NO_CONFIRMED_RESULT`，两者均禁止伪成功。旧 Lease 即使网络恢复也只能得到 `STALE_LEASE`。

## 5. Expiration、Reclaim 与超时

默认值是可配置技术参数：

| 语义 | 默认值 | 结果 |
|---|---:|---|
| HTTP connect/read | 15s/30s；图片 30s/120s | 客户端 transient retry，不改 Lease 所有权 |
| Lease duration | 120s | heartbeat 可延长 |
| Heartbeat interval | 30s | 允许多次丢失但必须早于 Lease 到期 |
| Attempt start timeout | 60s | leased 未 start → reclaim |
| Attempt execution timeout | 30min | timeout → retry/dead |
| Job max attempts | 5 | 超限 → failed/dead，按错误类别 |
| Task deadline | 默认 24h，可空 | 到期后停止新分配，reconciliation 终结/人工处理 |

Reclaim 事务锁定 Job/Attempt，确认 `LEASE_EXPIRES_AT <= SYSTIMESTAMP` 且仍为 active，Attempt→reclaimed，清除 Job lease。若 Task paused，则 Job→paused；transient 且尝试数未满则 Job→retry_wait；永久/超限则 failed；不确定一致性则 dead。创建新 Attempt 只发生在下一次 acquire，不在 reclaim 事务中预先创建空 Attempt。

## 6. Pause / Resume

- 用户 pause 设置 Task `PAUSE_STATE='paused'`，立即阻止新 acquire。
- `pending/retry_wait` Job 转 paused。
- `leased/running` Job 设置 `PAUSE_REQUESTED=1`：Worker 在安全点提交 Checkpoint 并调用 yield，随后 Attempt cancelled、Job paused；Worker 失联则 Lease 到期后 reconciliation 转 paused。
- 系统降载只停止 scheduler/acquire，不修改用户 pause 状态。
- 设备不可用只影响 Lease/reclaim，不把 Task 标为 paused。
- retry wait 保持独立状态。
- resume 清除 Task pause，paused Job 转 pending；最新确认 Checkpoint 保留。

## 7. Retry 分类

| 分类 | 默认行为 |
|---|---|
| `transient` | 指数退避+jitter，最多 5 Attempt |
| `permanent` | Job failed，不自动重试 |
| `business_rejection` | Job failed/not-matched，由 Task 聚合 |
| `data_quality` | Job quarantined |
| `authentication_required` | quarantined，等待账号状态恢复/人工动作 |
| `manual_intervention_required` | dead 或 quarantined，取决于数据是否可信 |

退避：`min(15s * 2^(attempt_no-1), 15min) + deterministic jitter`。服务端保存 `NEXT_RUN_AT`，客户端不得自行绕过。

## 8. Reconciliation

周期任务和管理 API 共用纯服务函数，扫描并审计：

1. leased/running 且 Lease 过期；
2. Task 终态但存在非终态 Job；
3. success Job 缺业务结果/receipt；
4. 结果 receipt 已存在但 Job 未 success；
5. 多个 active Attempt；
6. Device active job/attempt 与 Job 不一致；
7. Job active token/Attempt 无效；
8. 长时间 outbox receipt 未完成；
9. 长时间停留在 leased/retry_wait/paused-requested。

确定性修复在同一事务完成并写 `SJZQ_JOB_EVENT`；不确定问题转 `dead` 并记录 `RECONCILIATION_MANUAL_REQUIRED`。服务启动只启动巡检，不盲目重置 running。

## 9. Android 生命周期与降级

采用组合：

- `WorkManager` 唯一周期/网络恢复入口，约束 `NetworkType.CONNECTED`；
- 需要持续无障碍 UI 操作时使用可见 Foreground Service；
- App 启动立即 enqueue unique recovery work；
- `BOOT_COMPLETED` receiver 只重新排队 WorkManager，不直接无限后台执行；
- 网络恢复由 WorkManager constraint 触发；
- Android 12+ 后台启动、厂商省电和无障碍授权限制可能推迟恢复，ADR 不承诺无限常驻。

降级不变量：Android 未恢复时 Lease 必然到期；服务端 reclaim 后可以由其他设备或后续启动重新执行；旧 App 的 token 永久失效，因此服务端 Job 不会永久 running。

## 10. 可观测性

每次状态变化写结构化事件，最少字段：

`task_id, job_id, attempt_id, device_id, worker_id, lease_token_hash, trace_id, event, old_status, new_status, error_class, error_code, timestamp, detail_json`。

日志只保存 lease token hash/后 8 位，不输出完整 token。通过 Job events + Attempt + receipt 可重建执行轨迹。

## 11. 兼容与发布顺序

1. 先部署 additive Oracle schema 和服务端 API；旧 `/tasks/pull` 暂时保留但不领取已生成 Job 的新任务。
2. 新 Android 使用 Job 协议并在所有写入携带 attempt/lease identity。
3. 确认版本覆盖后禁用 legacy task pull 创建新执行；历史任务可由 lazy backfill 生成 Job。
4. Phase 1 product/image/finish idempotency receipt 继续使用，不降低成功门禁。

## 12. 明确不做

- Enterprise/Workspace/RBAC 重构；
- ProductSnapshot 全量迁移；
- 京东/淘宝/1688；
- 完整管理 UI；
- 假设无限后台常驻或以 Android 本地状态作为任务真相。
