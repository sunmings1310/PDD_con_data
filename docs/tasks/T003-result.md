# T003 实施结果

> 日期：2026-08-13
> 分支：`task/T003-task-state-machine`
> 实施依据：`docs/tasks/T003-analysis.md`

## 1. 最终状态模型

服务端任务权威状态：

- 非终态：`pending`、`running`
- 终态：`succeeded`、`partially_succeeded`、`failed`、`cancelled`、`timed_out`
- 初始状态：`pending`
- 可取消：`pending`、`running`
- 可重采（创建新任务，不回退原记录）：`partially_succeeded`、`failed`、`cancelled`、`timed_out`

现有 Oracle `STATUS VARCHAR2(16)` 无法容纳 19 字符的 `partially_succeeded`。因 T003 禁止修改 schema，数据库兼容值集中存为 `partial_success`，API/业务模型统一规范化为 `partially_succeeded`；后续由 BL-004 扩列并迁移。

任务项状态：`pending`、`running`、`succeeded`、`not_matched`、`failed`、`cancelled`。审核状态保持独立：`pending/approved/rejected`。设备 `STATUS/RUN_STATE/CURRENT_TASK_ID` 描述连接和执行占用，不作为任务业务状态。

## 2. 状态迁移

实际合法任务迁移：

- `pending -> running`
- `pending -> cancelled`
- `running -> succeeded`
- `running -> partially_succeeded`
- `running -> failed`
- `running -> cancelled`
- `running -> timed_out`

同状态重复为幂等；其他迁移返回 `TASK_STATE_CONFLICT`。终态不能切换到另一终态或回到非终态。

任务项允许 `pending -> running/任一项终态`、`running -> 任一项终态`；终态不可改写。完成事件按任务项及普通任务已有计数聚合为成功、部分成功或失败。分析中未确定的“全未命中是否独立任务终态”未新增状态，按分析暂归 `failed`。

## 3. 修改文件

新增：

- `server/task_state.py`
- `server/task_state_service.py`
- `tests/test_task_state.py`
- `tests/test_task_state_api.py`
- `android_collector/app/src/main/java/com/collector/pdd/net/TaskStatusMapping.kt`
- `android_collector/app/src/test/java/com/collector/pdd/net/TaskStatusMappingTest.kt`
- `docs/decisions/T003-authoritative-task-state.md`
- `docs/tasks/T003-result.md`

修改：

- `server/routers/tasks.py`
- `server/routers/devices.py`
- `server/routers/products.py`
- `server/routers/ota.py`
- `server/schemas.py`
- `android_collector/app/src/main/java/com/collector/pdd/net/AgentCoordinator.kt`
- `android_collector/app/src/main/java/com/collector/pdd/net/ApiClient.kt`
- `task_runner.py`
- `web/src/views/tasks/TaskList.vue`
- `web/src/views/tasks/TaskDetail.vue`
- `web/src/views/devices/DeviceLive.vue`
- `server/static/index.html`
- `server/static/app.js`
- `server/static/style.css`
- `docs/architecture.md`
- `docs/backlog.md`

分析产物：`docs/tasks/T003-analysis.md`。

## 4. 服务端改动

- 权威定义：`server/task_state.py`，包含 Enum、合法迁移、终态、可取消/重采集合、结果聚合和兼容映射。
- 状态入口：`server/task_state_service.py`，包含任务/任务项条件迁移、运行态和设备归属校验、未完成项收口、结果聚合。
- `pull/progress/finish/cancel`、设备 abort、OTA abort、商品上传任务项回填均通过统一入口或运行态守卫。
- 非法转换返回 `ApiOk(ok=false)` 及稳定 `error_code/current_status/requested_status`；未更改现有 URL 和统一响应外形。
- finish 只接受 `complete/failed/cancelled/timed_out`；旧客户端 `done` 在集中兼容层解释为 `complete`，未知值明确拒绝。
- 设备心跳的 `CURRENT_TASK_ID` 同时校验任务为 `running` 且归属本设备；finish/abort 只条件清除相同 task ID，避免迟到请求清除新任务。
- 审核写入增加 `STATUS='pending' AND REVIEW_STATUS='pending'` 条件，避免重复/竞态改审。

## 5. Android 映射

集中位置：`TaskStatusMapping.kt`。

| 本地状态 | 服务端事件/状态 |
|---|---|
| `finished` | `complete`（服务端聚合最终结果） |
| `failed` | `failed` |
| `stopped` | `cancelled` |
| item matched | `succeeded` |
| item not matched | `not_matched` |

未知本地状态抛出明确异常并进入 Coordinator 失败日志，不再默认成功。`ApiClient.finish` 也限制可发送值。本地 idle + 残留 remote ID 不再主动覆盖服务端终态；完整恢复等待 attempt/outbox 后续任务。

## 6. Desktop 映射

`task_runner.py` 增加显式兼容映射：

- `running/paused/pause -> running`
- `stopped/stop -> cancelled`
- `finished -> complete`
- `failed/interrupted -> failed`

未知值抛出异常。旧桌面端是否纳入生产服务端调度仍为 UNKNOWN，因此未删除链路、未双写 Oracle、未改变 SQLite 现有持久化状态。

## 7. Task Item 处理

- `not_matched` 与技术 `failed` 分离；Android 未命中不再上报失败。
- item 更新前验证父任务仍为 `running`；终态任务拒绝迟到 progress/product 修改。
- item 终态不可互相覆盖，同结果重复幂等。
- complete 前收口未完成项，再由服务端聚合最终任务状态。
- 成功/失败计数对目标任务由 `succeeded` 与 `failed/not_matched` 聚合；兼容读取历史 `done`。

## 8. API 影响

- URL 无破坏性变化。
- 新增 `POST /api/tasks/{task_id}/cancel`。
- `/api/tasks/finish` 默认状态由 `done` 改为 `complete`；请求中的旧 `done` 继续兼容并标记 deprecated。
- `/api/tasks/progress` 兼容旧 item `done -> succeeded`；新 Android 使用 `succeeded/not_matched`。
- 任务查询新增 `terminal/dispatchable/can_cancel/can_retry` 派生字段。
- Web 和静态管理页已同步新任务/任务项枚举，并继续兼容历史 `done` 显示。

## 9. 自动化测试

| 命令 | 结果 | 摘要 |
|---|---|---|
| `.venv-t001\Scripts\python.exe -m unittest discover -s tests -p 'test_task_state*.py' -v` | PASS | 12/12；合法/非法迁移、终态保护、重复完成、旧进度、Android/Desktop 映射、未知值、聚合、存储兼容、API 错误 |
| `.venv-t001\Scripts\python.exe -m unittest discover -s tests -v` | PASS | 26/26，含既有服务端测试与 T003 测试 |
| `.venv-t001\Scripts\python.exe -m compileall -q server tests task_runner.py storage_exporter.py` | PASS | 退出 0 |
| `gradle.bat :app:testDebugUnitTest --tests 'com.collector.pdd.net.TaskStatusMappingTest' --no-daemon --console=plain` | PASS | Android 映射 3/3 |
| `gradle.bat assembleDebug testDebugUnitTest --no-daemon --console=plain` | FAIL（KNOWN EXISTING FAILURE） | 共 18 项，T003 新增 3 项通过；仅 `DetailReaderTest` 既有 3 项失败，与 T001 记录一致 |

## 10. 回归结果

### Python：PASS

- 26/26 自动化测试通过。
- compileall 通过。
- 注入 test 环境后导入状态模块和 tasks/devices/products/ota router，输出 `T003_IMPORTS_OK`。

### Web build：PASS

命令：Node 22.18.0 下 `npm run build`。结果：1665 modules transformed，`built in 779ms`，退出 0。保留既有大 chunk 警告。

### Android assembleDebug：PASS

命令：Gradle 8.4/JDK 17 下 `gradle.bat assembleDebug --no-daemon --console=plain`。结果：`BUILD SUCCESSFUL`，退出 0。

Android 全量 unit test：FAIL（KNOWN EXISTING FAILURE），仅 `DetailReaderTest` 3 项；T003 状态映射单独运行 PASS 3/3。没有 NEW FAILURE。

## 11. 遗留问题

- 没有隔离 Oracle 测试 schema，因此未执行真实 Oracle API 集成/并发事务测试；沿用 BL-010 阻塞。
- 历史 `done/failed` 数据无法可靠拆分成功、部分成功、未命中与技术失败，未做 schema/数据迁移。
- 普通多商品任务仍有商品上传增量计数；完整幂等由 BL-007 处理。
- Agent 结束上报失败后没有持久化恢复；属于 BL-008 outbox。
- 桌面端正式定位仍为 UNKNOWN，只实现隔离映射。

## 12. Backlog 建议

- BL-006：attempt、lease、超时阈值和 reconciliation；当前 `timed_out` 只定义并受状态机约束，不自动产生。
- BL-007：progress/product/image/finish 幂等键和单调序号，替代普通任务 delta 计数风险。
- BL-008：Android 持久化 outbox，处理 finish/progress 网络失败和 App 重启。
- BL-010/BL-004：提供隔离 Oracle 并完成新状态值、历史数据及约束的版本化迁移验证。
- BL-106：结构化 `error_code/stage/retryable`，区分技术失败与业务未命中后的重试策略。
- 既有 BL-011：`DetailReaderTest` 3 项失败；T003 未处理。

## 13. T003 完成判断

**DONE**

依据：服务端权威枚举、合法迁移、终态保护、聚合、Android/Desktop 映射和统一 Oracle 入口已实现；任务相关直接状态写已收敛；Python、Web、Android build 与 T003 Android 测试通过。Android 全量测试没有新增失败，仅保留 T001 已登记的 3 项既有失败。Lease、retry queue、outbox、schema 迁移和 reconciliation 均未越界实现。

## PR Review R1

PR Reviewer 提出七类 Blocking Issues：heartbeat 覆盖设备占用、pull 缺少设备级原子互斥、progress 终态保护与 delta 重放、product upload 事务原子性、device/OTA abort 归属、complete 幂等过宽、接口/事务/竞态测试不足。

## PR Review R1 Resolution

### 1. Heartbeat

- 修复：heartbeat 不再写 `CURRENT_TASK_ID`、`RUN_STATE`、`RUN_STARTED_AT`、`REST_UNTIL`；客户端 task ID 仅为观察输入。服务端依据已有 `CURRENT_TASK_ID` 派生本次在线/忙状态。
- 测试：普通 heartbeat 不清占用；旧 task heartbeat 不覆盖新 task；SQL 断言 heartbeat 无任务归属写入。

### 2. Pull atomicity

- 修复：`pull` 在事务内以 `SELECT ... FOR UPDATE` 锁定设备行，先确认 `CURRENT_TASK_ID IS NULL`，再 claim task，并以条件 UPDATE 建立占用。相同设备的并发 pull 被 Oracle 行锁串行化。
- 测试：验证设备行锁、条件占用及第二个 pull 在首个提交后观察到占用而不能领取。

### 3. Progress / replay

- 修复：progress 使用 `require_running_task(..., for_update=True)` 将运行态/归属判断与写入放在同一事务；终态及错误设备拒绝。delta 请求新增 `progress_id`，在 `SJZQ_PROGRESS_RECEIPT` 以主键持久化去重；重复请求安全 no-op。没有 delta 的日志/item 结果保持兼容。
- 测试：终态迟到 progress 拒绝；delta 缺 ID 拒绝；相同 ID 重放不累计；receipt 重放识别。

### 4. Product Upload transaction

- 修复：插入前锁定并验证 task 和显式 item 可变；商品、图片元数据、计数、item 迁移继续共用 `get_conn` 事务；item 迁移冲突显式 rollback 后返回失败，异常由 context manager rollback。
- 测试：非运行态在 INSERT 前拒绝；item 迁移失败触发 rollback；终态/迟到由运行态和 item 终态守卫拒绝。正常提交依赖现有 upload 流程及 Oracle 集成环境，真实 Oracle 集成测试仍由 BL-010 提供。

### 5. Abort ownership

- 修复：device abort 与 OTA abort 均在终止前调用 `require_running_task(..., expected_device_id, for_update=True)`；清占用继续要求 `CURRENT_TASK_ID` 精确匹配。错设备、已重分配、任务不存在均不终止权威任务。
- 测试：代码路径断言归属锁及条件清理；状态服务已有 device mismatch/not found 错误覆盖。

### 6. Complete idempotency

- 修复：重复 `complete` 只在已有 `succeeded/partially_succeeded` 且设备归属相同时幂等成功；`failed/cancelled -> complete` 返回冲突；错误设备及旧 Agent 被拒绝。
- 测试：成功终态重复 complete 幂等；failed/cancelled complete 拒绝；错误设备拒绝；首次 running complete 仍由聚合路径覆盖。

### 7. Race/transaction tests

- 新增 `tests/test_task_state_r1.py`，覆盖 heartbeat、pull 设备互斥、progress receipt、upload rollback、abort ownership、complete 精确幂等和迟到请求保护。
- T003 专项：26 项通过；Python 全量：40 项通过（最终专项补充后总数）。

### R1 事务边界与兼容影响

- Heartbeat 不再是设备任务归属写入口。
- Pull 在单一 Oracle 事务中锁设备、claim task、写设备占用。
- Progress 锁 task 后领取持久化 `progress_id` 再应用 delta。
- Product upload 在单一连接事务中验证、插入、迁移；业务失败显式 rollback。
- API URL 不变；有 delta 的 `/api/tasks/progress` 现在必须传 8～64 字符 `progress_id`。Android 已自动生成 UUID。旧客户端若实际发送非零 delta，升级前会收到 `PROGRESS_ID_REQUIRED`，这是防止重复累计所需的最小兼容收紧。

### R1 数据库变化

- 新增最小表 `SJZQ_PROGRESS_RECEIPT(PROGRESS_ID PK, TASK_ID, DEVICE_ID, CREATE_TIME)`，仅用于持久化 delta replay protection；未引入 attempt、lease、outbox 或 retry queue。

### R1 回归

- Python：40/40 PASS；compile/import PASS（`T003_R1_IMPORTS_OK`）。
- Web production build：PASS，1665 modules，保留既有大 chunk warning。
- Android `assembleDebug` + `TaskStatusMappingTest`：PASS。
- Android 全量 `DetailReaderTest` 的 3 项已知失败仍为 KNOWN EXISTING FAILURE；R1 未产生新失败。

## PR Review R2

第二轮 Reviewer 结论为 `REQUEST_CHANGES`。阻塞项集中在 Complete/Cancel 的锁顺序反转风险，以及缺少真实 Oracle 多连接、多事务并发验证。

## R2 Resolution

### 1. R1 Commit

- commit：`bcc6e43`
- message：`fix: harden task state transactions and idempotency`
- 内容：R1 的 heartbeat 权威归属、pull 设备互斥、progress receipt、product rollback、abort ownership、complete 幂等收紧及专项测试已独立提交。

### 2. Canonical Lock Order

任务执行写事务统一采用以下顺序：

1. `SJZQ_DEVICE`
2. `SJZQ_TASK`
3. `SJZQ_TASK_ITEM`
4. receipt/product/image/log 等从属写入

路径可以跳过无需修改的对象，但不得在取得较后层级锁后再取得较前层级锁。设备批量路径按 `DEVICE_ID` 升序锁定，避免不同事务以不同设备顺序形成环路。

各路径实际顺序：

| 路径 | 锁顺序 |
|---|---|
| Pull | Device → Task；无 Item 写锁 |
| Complete | Device → Task → 全部 Task Item |
| Cancel | Device（任务无设备时跳过）→ Task → 未完成 Task Item |
| Product Upload | Device → Task → 指定/匹配 Task Item → Product/Image 从属写入 |
| Progress | Device → Task → 指定 Task Item；无 item 回报时跳过 Item |
| Device Abort | Device → Task → 未完成 Task Item |
| OTA Abort | Device（按 DEVICE_ID 升序）→ Task → 未完成 Task Item |
| Task 聚合 | 调用方已持有 Device，随后 Task → 全部 Task Item；纯服务调用为 Task → Item |

### 3. Complete / Cancel

- Complete 在读取/校验 running task 前先锁设备，再锁 Task 和 Item。
- Cancel 先只读取得设备标识，随后按 Device → Task → Item 加锁，并在锁内重新执行权威迁移。
- `transition_task` 强制以 `FOR UPDATE` 读取 Task；非法的不同状态迁移抛出 `StateConflict`，不再以 `changed=False` 静默继续副作用。
- `transition_item` 强制按 Task → Item 加锁；聚合读取也锁定 Task 与 Item，避免 Complete/Cancel 与 progress/product 交叉覆盖。

### 4. Concurrent Pull Test

- 新增：`tests/test_task_state_r2_oracle.py::test_concurrent_pull_same_device_claims_at_most_one_task`。
- 方法：`ThreadPoolExecutor` 两线程、Oracle pool 两个独立连接/事务，同时调用真实 `pull_task` API 函数。
- 断言：仅一个请求获得任务；设备只有一个 `CURRENT_TASK_ID`；两个候选任务最多一个为 running。
- 当前结果：`BLOCKED_BY_ENVIRONMENT`。环境未配置隔离 Oracle 测试 schema；测试没有降级为 mock，也没有伪报 PASS。

### 5. Complete vs Cancel Race Test

- 新增：`test_complete_cancel_race_twenty_times_without_deadlock`。
- 方法：每轮创建 running Task/Item，两个独立 Oracle 事务同步发起真实 Complete 与 Cancel 路径，共执行 20 轮。
- 断言：每轮在超时内返回；Task 仅有一个合法终态；Item 为合法终态；设备 `CURRENT_TASK_ID` 最终为空。
- 当前结果：`BLOCKED_BY_ENVIRONMENT`（隔离 Oracle 未配置）。

### 6. Receipt Concurrency Test

- 新增：`test_duplicate_receipt_two_transactions_increment_once`。
- 方法：两个独立连接同时插入相同 `PROGRESS_ID`，仅取得数据库主键声明权的事务累加计数。
- `claim_progress_id` 只把 Oracle `ORA-00001` 识别为重复；其他数据库异常继续抛出。
- 断言：一真一假两个 claim 结果、receipt 仅一行、计数仅增加一次。
- 当前结果：`BLOCKED_BY_ENVIRONMENT`（隔离 Oracle 未配置）。

### 7. Product Upload Rollback Test

- 新增：`test_product_upload_api_failure_rolls_back_real_writes`。
- 方法：真实 Oracle 事务通过 upload API 完成 Task 校验、Product 与 Product Image 写入后，在 Item 迁移点注入确定的 `StateConflict`。
- 断言：API 返回失败；Product 与关联 Image 均不存在；Item 仍为 pending；Task 计数不变。
- 当前结果：`BLOCKED_BY_ENVIRONMENT`（隔离 Oracle 未配置）。

### 8. Test Environment Contract

真实数据库套件仅在显式设置以下隔离测试参数后运行：

- `T003_ORACLE_TEST_ENABLED=1`
- `T003_ORACLE_DSN`
- `T003_ORACLE_USER`
- `T003_ORACLE_PASSWORD`

当前四项均未设置，因此 unittest 将四项真实 Oracle 测试明确报告为 `skipped: BLOCKED_BY_ENVIRONMENT`。普通应用 `.env` 不会被该套件当作测试数据库使用，避免在非隔离库写入竞态数据。

### 9. Remaining Risks

- 真实 Oracle 多连接并发执行仍被测试环境阻塞；在该验证完成前，本轮并发阻塞项不能标记为 FIXED。
- Oracle 套件依赖隔离 schema 已包含当前表、序列及 R1 receipt 迁移；未配置时不会自行修改 schema。
- `DetailReaderTest` 的 3 项失败仍为 T001 已登记的 `KNOWN_EXISTING_FAILURE`，不属于 T003 新增失败。
