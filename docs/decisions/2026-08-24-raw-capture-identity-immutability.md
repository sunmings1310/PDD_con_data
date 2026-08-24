# ADR：Raw Capture 身份、租户隔离与不可变派生

- 状态：Accepted
- 日期：2026-08-24
- 任务：`BASELINE-REVIEW-FIX-001`
- 范围：Accepted Raw Evidence baseline；不包含 Generic SKU、P1 Schema 或 Phase 6B

## 决策

Raw Capture 的逻辑身份由以下字段共同约束：

`enterprise_id + workspace_id + platform + platform_product_id + task_id + job_id + attempt_id + device_id + capture_id + source inventory/content hashes`

`capture_id` 是客户端稳定请求标识，但不是全局路径或单独的业务身份。新 Capture 的内部存储按 Enterprise/Workspace 隔离；外部 DTO 只暴露 `capture_id`、`evidence_ref` 和 `manifest_ref` 等 opaque reference，不暴露服务器文件系统路径。

同一 Enterprise/Workspace 下再次写入同一 `capture_id` 时：

- identity hash 与 content hash 都相同：返回原 Manifest，视为幂等重放；
- 任一 identity 字段、Source Inventory、Source Content 或派生上传内容不同：返回 `RAW_CAPTURE_CONFLICT`，不得静默复用旧证据。

不同 Enterprise 或 Workspace 可以使用相同 `capture_id`，但各自存储、校验和重放，查询不得跨租户搜索命中。

## 不可变性

首次持久化后的 Original Evidence 永久不可变：

- Source bytes、原 SHA-256、Product Upload bytes、Field Inventory 和 Original Manifest 均不得原地改写；
- 重新脱敏或过滤升级必须创建 `derived_resanitized` 版本；
- Derived Manifest 必须记录 original capture、original manifest/source hashes、derived id、filter version、created_at、derived hashes 和 derivation reason；
- Offline Replay 必须显式选择 `original`、具体 derived id 或 `latest_safe`，不得用派生结果冒充 Original。

Legacy 平铺 Capture 仅由显式、不带租户参数的本地离线工具兼容读取；新租户 Capture 不按 `capture_id` 递归搜索，避免跨租户碰撞。

## 错误与 API

- 身份或内容冲突：`RAW_CAPTURE_CONFLICT`；
- 格式、缺少租户键、Hash 校验或敏感过滤失败：`RAW_CAPTURE_INVALID`；
- API 不返回 `D:\...`、`/home/...` 或其他 resolved path；物理目录不进入业务 Identity。

## 验证

`tests/test_raw_capture.py` 覆盖同租户同内容 retry、payload/product/task/job/attempt/device 冲突、跨 Enterprise/Workspace 隔离、Original/Derived Replay、Original bytes/hash/manifest 不变和 opaque API reference。

## 非目标

本 ADR 不启用 SKU_PANEL 交互，不引入 ProductAttribute/SKU/SkuSnapshot Oracle Schema，不回填历史数据，也不进入 Phase 6B。
