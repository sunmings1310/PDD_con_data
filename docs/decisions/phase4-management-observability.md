# ADR：Phase 4 管理查询与可观测性

- 状态：Implemented（最终验收见 `docs/tasks/phase4-acceptance.md`）
- 日期：2026-08-17
- 决策者：Phase 4 Sol Tech Lead
- 前置：Phase 1～3 ADR

## 1. 决策

Phase 4 只在既有 Oracle 事实之上增加只读管理查询，不建立第二套日志或质量模型：

- Quarantine 以 `SJZQ_DATA_QUARANTINE + RAW_COLLECTION + QUALITY_RESULT` 为事实；隔离记录尚无正常 Snapshot 时，商品身份从脱敏 `EVIDENCE_JSON` 读取。
- Product 时间线以不可变 `PRODUCT_SNAPSHOT` 为事实，并直接展示既有 `SNAPSHOT_DIFF` 与 `FIELD_PROVENANCE`。
- Task 执行轨迹复用 `COLLECTION_JOB / ATTEMPT / LEASE / JOB_EVENT`，Task、Job、Attempt 和事件分别分页；摘要不携带无限子集合。
- 质量指标由服务端聚合 `QUALITY_RESULT`，前端只展示 API 结果。

所有可能增长的列表使用 `page/limit/total/items`，数据库执行 `COUNT + OFFSET/FETCH`。稳定排序在时间列后增加唯一 ID；事件时间线使用正序，其余管理列表使用倒序。

`P4_001_MANAGEMENT_INDEXES` 以独立 checksum migration 增加 Attempt Event、Quarantine、Snapshot、Task/Product 分页索引，不修改已发布的 Phase 3 migration checksum。

## 2. 指标语义

- 总采集量：`QUALITY_RESULT` 行数（一条 Raw 对应一条质量结果）。
- PASS/Quality pass rate：`ACCEPTED=1`，包括 passed 与 warning；不把 warning 误计为隔离。
- QUARANTINE：`ACCEPTED=0`；同时保留 Quarantine 实体计数用于一致性排查。
- Parser failure：错误码精确属于 `PARSE_FAILED / PARSE_NOT_ATTEMPTED`；`PARSE_STATUS=failed` 另作诊断计数，因为 QualityGate 会把其他质量拒绝映射为 failed。
- 关键字段缺失率：按 identity/title/price 的 `MISSING_FIELDS_JSON` 成员统计，分母为全部质量结果。
- price 缺失率：关键字段 price 的缺失数 / 全部质量结果。
- SKU 异常率：`SKU_INVALID_*` 错误码 / 全部质量结果；SKU 缺失 warning 不等于 SKU 异常。
- Parser/规则版本表现：直接按 `QUALITY_RESULT` 版本分组聚合。

简单异常提示只使用当前查询窗口中的可靠聚合阈值，不建设告警平台。

## 3. API 与权限

统一前缀 `/api/management`：

- `GET /quarantines`、`GET /quarantines/{id}`
- `GET /products/{master_product_id}/snapshots`
- `GET /quality/metrics`
- `GET /tasks/{task_id}/trace`
- `GET /tasks/{task_id}/jobs`、`GET /jobs/{job_id}/attempts`
- `GET /tasks/{task_id}/events`、`GET /attempts/{attempt_id}/events`

质量、隔离、Snapshot 沿用 `data:view`；执行轨迹沿用 `task:view`。Phase 4 不新增 RBAC 模型。

## 4. 明确不做

- 不修改或覆盖历史 Snapshot；
- 不增加 Quarantine 人工修复状态机；
- 不复制 Phase 2 Job Event；
- 不建设日志平台、完整告警中心、BI、企业租户或多平台 Collector。
