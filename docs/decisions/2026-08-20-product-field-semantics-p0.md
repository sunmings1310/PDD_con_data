# ADR：商品字段语义、Canonical Read Model 与编辑边界（P0）

- 日期：2026-08-20
- 状态：Accepted
- 范围：Phase 1～6A 兼容读取；不进入 Phase 6B；不创建正式 SKU/ProductAttribute Oracle 表

## 字段语义

| Canonical 字段 | 定义 | 兼容列 |
|---|---|---|
| `platform_title` | 平台页面观察到的真实完整标题 | `SJZQ_PRODUCT.SELL_NAME` |
| `canonical_name` | 规范商品名/通用名，不包含促销及购买组合 | `SJZQ_PRODUCT.PRODUCT_NAME` |
| `product_attribute_spec` | 商品自身参数规格，属于 ProductAttribute 语义 | `SJZQ_PRODUCT.SPEC_TEXT` |
| `sku_dimensions` | 购买面板直接观察到的动态选择维度 | P0 无正式列；未观察时为空并标记状态 |
| `sku_combinations` | 购买面板实际组合及组合级观察 | `SKU_PRICES_JSON`，优先读取 Snapshot `SKU_JSON` |

“品名/标题”不再是 API 或 Web 业务字段。兼容列名只允许在单一 persistence adapter 中出现。

## 价格语义

| 字段 | 来源 | 兼容列 |
|---|---|---|
| `list_price` | 搜索/列表卡片观察价格 | `PRICE` |
| `detail_price` | 商品详情页面主价格 | `DISPLAY_PRICE` |
| `single_purchase_price` | 单独购买入口显示价格 | `DEAL_PRICE` |
| `group_price` | 拼单/组团入口显示价格 | `GROUP_PRICE` |
| `original_price` | 平台明确标注的原价/划线价 | `ORIGINAL_PRICE` |

五个字段始终独立保存。需要单值统计时使用唯一 Effective Price 优先级：

```text
single_purchase_price → detail_price → group_price → list_price → original_price
```

权威实现在 `server/product_contract.py`；Report 等调用方不得自行建立优先级。

## Canonical Product Read Model

`server/product_read_model.py` 是 legacy 和 strict protocol 的共同读取层，输出 Identity、Stable Profile、Latest Observation、SKU、Media、Provenance、Quality 和 Capture Context。

Strict 商品优先读取关联 Snapshot 的动态观察；Snapshot 尚未覆盖的兼容字段从同次上传的 `SJZQ_PRODUCT` 读取。Legacy 商品从 `SJZQ_PRODUCT` 读取，且 provenance 明确返回 `unavailable`，不得伪造 Raw/Snapshot 关联。

## DTO 边界

- `ProductDetailDTO`：完整只读商品视图。
- `ProductEditDTO`：资料库稳定资料编辑视图。
- `CaptureResultDTO`：完整采集结果。
- `CaptureEditDTO`：采集结果阶段稳定资料纠错视图。
- `SnapshotDTO`：不可变动态观察；没有对应写 DTO。

两个 Edit DTO 使用相同 canonical 字段名和来源。Web 打开编辑窗口必须请求 `/api/products/{id}/edit?scope=...`，不得复制列表行。

## Editable Field Policy

普通 `PUT /api/products/{id}` 只允许：

```text
platform_title, canonical_name, brand, product_attribute_spec,
approval_number, manufacturer, dosage_form, category, expiry
```

价格、销量、店铺销量、评价数、促销、库存、availability、SKU 观察、Snapshot、Raw 和 provenance 均不可通过该接口修改。P0 不实现 Manual Override；未来必须采用 `Observed Value + Manual Override → Effective Value`，且不修改 Raw/Snapshot。

## 兼容性

- 不新增业务表，不执行破坏性迁移。
- `LIBRARY_STATUS draft → saved` 只改变资料库状态，不改变商品业务字段。
- 旧上传同步方法委托给 `OutboxPayload.product()`，后者是唯一权威 Android Upload Mapper。
- P1 再决定正式 ProductAttribute、SKU Dimension/Combination/SkuSnapshot Schema。
