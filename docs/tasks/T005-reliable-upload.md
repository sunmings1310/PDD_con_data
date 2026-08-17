# T005：Android 可靠上报与完成语义

## 已实现闭环

```text
解析/质量通过
  → Room(product + product outbox，同事务)
  → POST product(stable idempotency key)
  → Oracle(product + task count + receipt，同事务)
  → optional image upload + image receipt
  → Android marks product outbox acked
  → finish outbox(expected product/image receipt counts)
  → Oracle verifies manifest and commits terminal task + finish receipt
  → Android receives finish acknowledgement
  → clears local remoteTaskId
```

`Task Complete` 不以页面操作、Parser 对象或 HTTP 200 为依据。服务端只有在
finish manifest 与已确认 receipts 完全一致后才提交终态；Agent 只有收到带
`acknowledged=true` 的最终响应后才清除远程任务关联。

## 故障语义

| 故障 | 结果 |
|---|---|
| 断网 / HTTP 5xx | outbox 转 `retry`，指数退避；Task 不 Complete |
| 商品响应丢失 | 同 idempotency key 重放，服务端返回既有 product receipt |
| 图片响应丢失 | `product-key:images` 重放，服务端返回既有 image receipt |
| Agent/App 重启 | `in_flight` 重置为 `retry`；未完成本地任务转 failed 并补 finish；已执行完但未入队 finish 也会补偿 |
| 重复提交 | 同 key/同 payload 返回相同业务结果；同 key/不同 payload 返回 `IDEMPOTENCY_CONFLICT` |
| finish 失败/响应丢失 | finish outbox 保留；相同 finish key 重放，不重复迁移任务 |
| manifest 缺确认 | 服务端返回 `FINISH_INCOMPLETE`，任务保持 running |

## 当前边界

- Outbox 解决 Agent 到 API/Oracle 的至少一次投递与服务端幂等，不替代 Phase 2 的 lease/checkpoint。
- App 进程被系统杀死后，恢复在联机 Agent 下次启动时触发；无人再次启动 App 的后台唤醒由 Phase 2 WorkManager/前台服务解决。
- 证照过滤属于服务端确认的策略处置，不计静默丢失；图片响应必须满足 `saved + skipped == submitted`。
- Product/ProductSnapshot 大迁移未执行；Phase 1 receipt 是请求幂等层，不是快照身份。
- 专用 Oracle 19c 测试 Schema 已执行并通过并发、回滚、业务去重、finish 门禁和最小成功闭环测试。

## 自动化证据

- `AppDatabaseMigrationTest`：Room 1→2 数据保留、销量列 nullable、Product+Outbox 原子回滚、in-flight 恢复、数据库关闭重开后任务/outbox 保留。
- `ApiClientReliabilityTest`：HTTP 5xx、无效 JSON、缺 acknowledgement、永久质量/幂等冲突、图片失败、finish ack 门禁。
- `test_phase1_reliability_contract.py`：商品/图片 receipt 重放与冲突、异常页写入前拒绝、finish manifest 不完整拒绝。
- `test_task_state_r2_oracle.py`：8 项真实 Oracle 验收全部通过，包含 Task 创建→审核→领取→商品持久化→finish 确认→任务成功的最小闭环。
