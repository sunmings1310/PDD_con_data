# T003 服务端权威任务状态决策

> 日期：2026-08-13
> 状态：Accepted

## 决策

- 服务端任务状态为 `pending/running/succeeded/partially_succeeded/failed/cancelled/timed_out`。
- 现有 Oracle `VARCHAR2(16)` 在 T003 不改 schema；`partially_succeeded` 暂集中编码为存储兼容值 `partial_success`，API 输出仍为权威逻辑值。
- 任务项状态为 `pending/running/succeeded/not_matched/failed/cancelled`。
- 状态枚举、合法迁移、终态、聚合和客户端兼容映射集中在 `server/task_state.py`；Oracle 更新集中在 `server/task_state_service.py`。
- 终态单调且不可互相覆盖；重复同结果视为幂等；旧进度、错误设备及非法迁移返回稳定错误数据。
- Android `finished` 发送 `complete` 事件，由服务端聚合最终结果；`stopped/failed` 显式映射为 `cancelled/failed`。桌面端保持隔离，仅提供显式兼容映射。
- 设备连接/运行状态不等于任务业务状态；清设备占用必须匹配 `CURRENT_TASK_ID`。

## 不在本决策范围

Lease、attempt/version、超时回收、retry queue、outbox、dead letter、历史数据迁移和旧桌面端正式定位继续由后续任务处理。
