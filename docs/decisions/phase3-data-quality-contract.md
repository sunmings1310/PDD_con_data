# ADR：Phase 3 Product / Snapshot / Provenance / Quality / Quarantine

- 状态：Implemented / Verified
- 日期：2026-08-17
- 决策者：Phase 3 Sol Tech Lead
- 前置：`phase1-success-data-contract.md`、`phase2-job-attempt-lease.md`
- 范围：拼多多上传 → FastAPI → Oracle 的数据质量事实链

## 1. 核心定义

### Product

Product 是平台内稳定身份，唯一业务键为：

```text
(platform_code, platform_product_id)
```

`platform_product_id` 当前来自拼多多 `goods_id/item_id`。URL、标题、店铺、SKU、批准文号均不参与 Product identity，避免标题变化造成重复，也避免不同平台 ID 被错误合并。

现有 `SJZQ_PRODUCT` 混合了身份与采集事实，且历史数据可能重复。Phase 3 不删除、合并或破坏性改写历史行，而是新增 `SJZQ_PRODUCT_MASTER` 作为稳定 Product，并用 `MASTER_PRODUCT_ID/SNAPSHOT_ID` 桥接现有表。历史回填另行设计，不阻塞新数据使用新契约。

### ProductSnapshot

Snapshot 是某次服务端确认的、不可覆盖的采集事实。它保存动态字段、规范化结果、字段来源、Parser/规则版本和上一次可信 Snapshot 引用。价格、销量、SKU、availability、标题和店铺变化只写新 Snapshot，不覆盖旧 Snapshot。

语义 identity：

```text
request idempotency key -> exactly one accepted Snapshot
```

- 同一 key 同 payload：返回同一 Snapshot。
- 同一 key 不同 payload：`IDEMPOTENCY_CONFLICT`。
- 不同 key 即使内容相同，也代表不同的已确认采集时间，因此创建新 Snapshot；Diff 可以为空。
- 质量失败不创建正常 Snapshot，只创建 Raw + QualityResult + Quarantine。

### SKU

当前采集契约只有 SKU JSON/文本，尚不能保证每个 SKU 都有平台稳定 `platform_sku_id`。Phase 3 把 SKU 集合作为 Snapshot 内不可变事实，不创建伪稳定 SKU 主档；在 Collector 能稳定提供 SKU ID 后再增加 `SKU/SKUSnapshot`，避免错误合并。

### Raw Collection / Raw Reference

`SJZQ_RAW_COLLECTION` 保存一次请求的脱敏结构化原始引用、payload hash、任务/Job/Attempt 和采集时间。它不保存 device secret、lease token。Raw 是 provenance 和 quarantine 的证据，不直接成为业务商品。

### Field Provenance

`SJZQ_FIELD_PROVENANCE` 按 Snapshot + field 保存来源类型。关键字段至少包括 identity、title、price；当 sales/shop/SKU 有值时也必须有来源。允许来源：

`search_response, detail_response, embedded_state, list_card, detail_text, sku_panel, share_link, network, embedded_json, dom, url, normalized_result, inferred, derived, none`。

来源缺失或未知时 QualityGate 给出稳定错误码，不把最终值当作无来源事实。

### QualityResult / Quarantine

QualityGate 是 Parser/Normalizer 与正常持久化之间的唯一服务端入口：

```text
Raw -> Parser result -> Normalizer -> QualityGate
    -> PASS/WARNING -> Product + Snapshot + Provenance + Diff
    -> QUARANTINE   -> Raw + QualityResult + Quarantine（无正常 Snapshot）
```

Quarantine 记录 request、可识别 Product identity、Task/Job/Attempt、版本、状态、失败原因和证据。重复拒绝请求通过 request key 返回同一 quarantine，不静默丢弃，也不污染正常 Product/Snapshot。

## 2. 统一 QualityGate

服务端规则版本：`phase3-1`。客户端仍必须提交明确 `parser_version` 和其本地规则版本，二者保留在 Raw；最终 QualityResult/Snapshot 使用实际执行的服务端规则版本。

最小规则：

1. `page_status=product`；异常页面进入 quarantine。
2. `parse_status=success|partial`；failed/not_attempted 不进入正常数据。
3. 平台和 platform product ID 非空且格式合法。
4. title 和至少一个正价格存在；数字必须有限且在版本化范围内。URL 是可选证据，不参与商品 identity。
5. 销量不能为负；缺失为 warning，不伪造 0。
6. SKU 缺失为 warning；存在但 JSON/价格结构异常则 quarantine。
7. 关键字段必须存在合法 provenance。
8. 客户端自报 `quality_status` 只是输入证据，不能覆盖服务端判断。

QualityResult 输出：`accepted, page_status, parse_status, quality_status, missing_fields, error_codes, warnings, parser_version, quality_rules_version`。

## 3. Difference Detection

Diff 只比较连续两个可信 Snapshot，与 QualityGate 分离。首条 Snapshot 的 `previous_snapshot_id=NULL`，changed fields 为空。至少检测：

- `price_changed`
- `sales_changed`
- `sku_changed`
- `availability_changed`
- `title_changed`
- `shop_changed`

比较使用规范化值；每项记录 before/after。相同内容的新观察仍创建 Snapshot，但 Diff 为空。

## 4. 事务与成功语义

一次 accepted upload 在单一 Oracle 事务内完成：

1. Lease/Task ownership 验证；
2. Raw 写入；
3. QualityResult；
4. Product master 原子 get-or-create；
5. legacy Product 兼容写入/关联；
6. Snapshot、Provenance、Diff；
7. TaskItem/计数；
8. receipt 写入并关联 master/snapshot；
9. commit 后才返回 acknowledgement。

任何一步失败全部回滚。Task/Job success 继续以 Phase 1/2 receipt 门禁为准。

## 5. Migration 决策

- 仅 additive migration；不删除、合并或覆盖已有数据。
- 增加 `SJZQ_SCHEMA_MIGRATION`，migration ID、checksum、状态和时间可查询。
- Oracle DDL 会隐式提交，因此每一步必须可重入；全部对象验证成功后才记录 migration applied。
- 首版 migration：`P3_001_DATA_QUALITY`。
- clean init 与 upgrade path 必须生成相同 schema；专用 Oracle 环境重复执行两次验证。

## 6. 非目标

- 不决定跨 Enterprise 共享 Product；当前 identity 只定义平台商品语义。
- 不实现其他平台 Collector、租户隔离、完整管理 UI。
- 不以 Git commit 替代业务 Parser/Quality 版本。
- 不回填或清理历史重复 Product；该操作需要单独迁移与数据决策。

## 7. 验证记录

- 固定离线矩阵：正常、价格空/异常、identity 缺失、SKU 缺失/异常、销量缺失、异常页、partial parser、来源缺失。
- Oracle 集成：同 key replay 只返回原 Snapshot；不同 key 的相同商品复用 Master 并追加 Snapshot；变化生成 Diff；拒绝数据只产生 Raw/Quality/Quarantine。
- `P3_001_DATA_QUALITY` 在专用 Oracle 测试 schema 连续执行两次成功，schema contract 与 Phase 1/2 回归通过。
- 已确认的纯 replay 例外：同 key/same payload 已持久化后的 ACK 或 Quarantine 查询不再写业务状态，因此允许在 Lease 释放后返回原结果；任何新写入仍须通过当前 Lease/Task fence。
