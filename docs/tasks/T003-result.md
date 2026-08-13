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
