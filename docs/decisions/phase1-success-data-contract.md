# ADR：Phase 1 成功语义、采集数据契约与幂等边界

- 状态：Accepted（Phase 1）
- 日期：2026-08-16
- 范围：拼多多 Android Agent → FastAPI → Oracle 最小闭环
- 非目标：本阶段不实施 Product/ProductSnapshot 大规模迁移，不决定跨企业共享商品主档

## 1. 决策

### 1.1 成功不变量

`Task Complete` 只表示：

1. 每个计划执行的采集项已到达明确终态；
2. 每个声称成功的商品都通过页面分类、解析和基础质量门禁；
3. 每个成功商品及其必需图片都已由服务端返回业务确认；
4. 服务端已在同一业务幂等键下持久化且可读取该商品；
5. Agent 的持久化 outbox 中不存在该任务未确认的必需事件；
6. finish 请求携带的期望商品确认数与服务端 receipt 数一致；
7. 服务端返回终态确认后，Agent 才清除当前远程任务。

页面操作完成、Parser 返回对象、Room 写入、HTTP 2xx、JSON `ok=true` 中任一单独条件均不构成任务成功。

### 1.2 商品身份与采集事实

- **Product identity**：平台内 `(platform, item_id)`。`item_id` 必须为平台稳定商品 ID，URL、标题、SKU 不是商品身份。
- **ProductSnapshot**：在确定 CollectionAttempt 中，对 Product 的一次不可变观察；价格、销量、SKU、availability、字段来源、解析/质量版本属于 Snapshot。
- **Snapshot identity**：未来由 `snapshot_id` 标识；语义唯一键为 `(collection_attempt_id, product_id, observation_ordinal)`。
- **请求幂等键**不是 Snapshot identity。相同幂等键表示同一业务写入的重放，必须返回同一 `product_id`，不得创建第二条业务数据或重复计数。
- Phase 1 保持现有 `SJZQ_PRODUCT` 表，但把每行视为“已确认采集事实”；后续迁移为 Product + ProductSnapshot 时必须保留 receipt 到事实记录的映射。

### 1.3 Task / Job / Attempt

- `CollectionTask`：用户提交的长期意图与配置。
- `CollectionJob`：Task 的一次可调度执行单元，包含目标集合和执行状态。
- `CollectionAttempt`：Job 被某设备领取后的单次尝试，未来持有 lease/checkpoint。
- Phase 1 不新增完整 Job/Attempt 表；Android 本地任务与远程 `task_id` 的绑定、outbox 事件和服务端 receipt 构成最小 attempt 证据。

### 1.4 页面、解析与质量状态

```text
page_status:
  product | login_required | challenge | busy | sold_out |
  not_found | malformed | unknown

parse_status:
  success | partial | failed | not_attempted

quality_status:
  passed | warning | quarantined
```

规则：

- 非 `product` 页面不得生成成功商品。
- `item_id`、商品名称、商品 URL 和至少一个正价格是成功必填项。
- SKU 缺失、销量缺失在没有“页面明确存在但解析失败”的证据时先记 `warning`，不伪造为 0。
- 价格缺失、非法业务键、结构异常进入 `quarantined`，不得上传为成功商品。
- `field_sources` 是 JSON object，记录字段到来源类型。Phase 1 允许：`list_card`、`detail_text`、`sku_panel`、`share_link`、`network`、`embedded_json`、`dom`、`url`、`inferred`、`derived`、`none`；后续新增值必须向后兼容。
- `parser_version` 与 `quality_rules_version` 必须随上传持久化，Phase 1 初始值分别为 `pdd-android-1`、`phase1-1`。

### 1.5 可靠上传与确认

- 每个商品事件在首次网络调用前原子写入 Room outbox。
- `idempotency_key` 由 Agent 生成一次并持久化；所有重试复用同一值。
- 服务端用唯一 receipt 原子保护商品 INSERT、成功计数和任务项迁移。
- 本地图片以最多 12 张的批次使用派生键 `<product-key>:images`，响应必须逐张给出“已保存”或“策略过滤”的确认；重复批次返回原确认。
- 网络错误、HTTP 5xx、无效 JSON、`ok=false`、缺少确认字段均不算 acknowledgement。
- 重试采用有上限的指数退避；永久业务错误保留为 failed/dead-letter，不静默删除。
- finish 是 outbox 事件；只在商品事件全部 ack 后发送。finish 失败继续重试，成功响应必须返回服务端最终状态。

## 2. 创建 Snapshot、重复和失败的判定

| 情况 | 处理 |
|---|---|
| 新 attempt 首次确认一个合法商品 | 创建新的采集事实；未来对应新 Snapshot |
| 同一 idempotency key 重放 | 返回原 `product_id`，不创建 Snapshot，不重复计数 |
| 同一 Task 用不同请求 key 重复提交同一 `(platform,item_id)` | Phase 1 返回同一业务 `product_id`，为每个请求写 receipt，但商品和成功计数只写一次 |
| 不同 attempt 采集到同一 `(platform,item_id)` | 属于新的采集事实；未来创建新 Snapshot |
| 页面为登录/验证/繁忙 | 不解析为商品；记录可重试页面状态 |
| 页面下架/不存在 | 记录 availability 结果，不创建成功商品 |
| product 页面但必填/价格失败 | `quarantined`，不创建成功商品 |
| 商品已确认但图片未确认 | 保持 outbox pending，Task 不得 Complete |
| finish HTTP 2xx 但响应 `ok=false`/无终态 | 未确认，继续重试 |
| App 在采集过程中重启 | 已入 outbox 的数据继续重放；中断的本地 running 任务不得自动 Complete |

## 3. 兼容策略

- 新 Android 必须发送质量元数据和幂等键。
- 服务端对携带 `idempotency_key` 的新采集链执行严格门禁；旧无 key 手工上传只保留兼容入口，不参与 Phase 1 闭环验收。
- Oracle DDL 仅新增表/列；Android Room 1→2 为保留数据的表重建，以支持销量 NULL 和持久 outbox。
- Product 是否跨企业共享留给 Phase 5 业务决策。

## 4. 验收映射

- fixtures 证明正常商品稳定解析，异常页不生成商品。
- mock/API/Oracle 测试证明重复 key 只落一条、只计数一次。
- Android JVM/Room 测试证明 outbox 跨重启保留、只在 ack 后结束。
- 断网、5xx、图片失败、finish 失败测试证明 Task 不进入成功终态。
