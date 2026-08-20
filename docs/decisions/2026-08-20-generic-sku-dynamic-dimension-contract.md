# Generic SKU Dynamic Dimension Contract

## 状态

冻结用于 PDD 真机验证；正式 Oracle Schema migration 暂停。

## 语义边界

`ProductAttribute` 描述商品详情参数；`SKU_PANEL` 描述购买时真实可选择的状态。属性名称包含“规格、包装、剂型、容量”等词时仍不产生 SKU。只有 `SKU_PANEL` 的直接选择证据可以产生 SKU Dimension 或 Combination。

## Dimension

Collector 按面板空间结构和交互结构发现维度，不根据维度名称分支：

```json
{
  "index": 0,
  "raw_name": "页面原文",
  "options": [],
  "observation_state": "VALUE",
  "evidence_ref": "SKU_PANEL.panel_opened.nodes"
}
```

`raw_name` 只作为数据保存。Collector 不为 color、size、capacity、model、package、dosage、quantity、flavor 或 style 建立固定字段。

## Option

每个 option 保存原文、维度位置、节点状态和证据引用。Collector 保留 disabled option，而不是从维度清单删除；未观察到的状态使用明确 Observation State。

## Combination Observation

```json
{
  "selected_options": [
    {"dimension_index": 0, "dimension_name": "页面原文", "value": "选项原文"}
  ],
  "platform_sku_id": {"state": "NOT_OBSERVED"},
  "price": {"state": "VALUE", "value": 0},
  "original_price": {"state": "NOT_OBSERVED"},
  "promotion_price": {"state": "NOT_OBSERVED"},
  "stock_state": {"state": "NOT_OBSERVED"},
  "available": {"state": "VALUE", "value": true},
  "disabled": {"state": "VALUE", "value": false},
  "selected_default": {"state": "NOT_OBSERVED"},
  "media_evidence": {"state": "NOT_OBSERVED"},
  "display_text": "页面原文",
  "captured_at_epoch_ms": 0,
  "evidence_ref": "SKU_PANEL.option_observations[n].snapshot"
}
```

平台 SKU ID 只能来自平台直接标识。规格文本、哈希或组合序号不能写入 `platform_sku_id`；系统后续生成的 `spec_fingerprint` 必须标记为内部 identity。

## 选择与稳定机制

Collector 对每个候选组合执行：捕获选择前签名 → 点击各维度 option → 轮询选择/价格/促销/availability 节点签名 → 连续观察到稳定签名后捕获 Raw。固定 sleep 只能作为轮询间隔或最终超时边界，不能单独证明状态已经更新。价格必须与稳定后的组合快照共同保存；Collector 不把一次主商品价格复制到所有组合。

## Observation States

统一状态为 `VALUE`、`NOT_OBSERVED`、`NOT_SUPPORTED`、`PARSE_FAILED`、`CONFLICT`、`REDACTED`、`NOT_APPLICABLE`。`VALUE(0)` 与 `NOT_OBSERVED` 永远不同。

## 交互边界

Collector 可以进入详情、打开 SKU Panel、选择 option 并观察状态。Collector 不点击确认订单、提交订单或支付入口，并在 Raw 中持续保存等价的三个 false guard 字段。
