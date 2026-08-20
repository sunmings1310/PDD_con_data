# ADR: Field Observation Model（先在 Parser/Normalizer 边界落地）

- 日期：2026-08-20
- 状态：Proposed（等待正式 Schema Proposal 确认）
- 范围：PDD Raw Capture replay、Parser、Normalizer；本阶段不执行 Oracle migration

## 决策

统一使用带状态的字段观察语义，而不是用 `null`、空字符串和 `0` 混合表达：

| 状态 | 含义 | 是否允许 value |
|---|---|---|
| `VALUE` | Raw 中存在可验证事实且解析成功 | 必须；允许 `0`、`false`、空集合（仅当原始事实确实为空集合） |
| `NOT_OBSERVED` | 本次采集能力支持该字段，但本次 Raw 未出现证据 | 禁止 |
| `NOT_SUPPORTED` | 当前商品形态、Source 或 Collector capability 不支持该字段 | 禁止 |
| `PARSE_FAILED` | Raw 中有候选证据，但 Parser 未能得到合法值 | 禁止；必须带 error/evidence_ref |
| `CONFLICT` | 两个可信 Source 给出无法按优先级消解的不同值 | 禁止；必须保留 candidates |
| `REDACTED` | 原始值因敏感信息规则被过滤 | 禁止；保留过滤规则版本 |

建议逻辑结构：

```json
{
  "state": "VALUE",
  "value": 0,
  "source": "DETAIL",
  "evidence_ref": "capture_id/sources/02_DETAIL.txt#评价",
  "parser_version": "pdd-android-2"
}
```

`VALUE(0)` 与 `NOT_OBSERVED` 在类型、传输和质量门三层都不等价。

## 当前阶段落地

1. Android `ProductEntity` 暂不触发 Room/Oracle 全表迁移；本地兼容字段仍可保存数值占位，但 `field_sources` 明确记录 `detail_text` 或 `none`。
2. Outbox/API 在 `comment_num=NOT_OBSERVED` 时发送 JSON `null`，观察到真实 `0` 时发送 `0`。
3. SKU 只有独立 SKU panel Raw 才可标为 `VALUE`；DETAIL 推导结果不再伪装为 Raw SKU。
4. Server QualityGate 将空 SKU 数组视为 `NOT_OBSERVED`，而不是“存在 SKU”。
5. Raw Capture 保留不可变证据；状态模型只影响 derived replay 结果，不回写 Raw。

## 后续迁移选项

确认 Schema 后优先采用“业务值列 + observation_state/source/error 列”或统一 Observation JSON；不为每个低价值字段立即增加状态列。高频查询字段使用显式列，低频字段继续保留在 Raw/Observation JSON 中。
