# 拼多多离线采集 fixture 契约

这些 JSON 是脱敏、可重复的详情页输入样本，测试不访问真实网络。每个样本包含：

- `page_status`: 页面可采集状态；异常页不得进入商品解析成功分支。
- `parse_status`: `success`、`not_attempted`、`partial` 或 `failed`。
- `quality_status`: `passed`、`warning` 或 `quarantined`。
- `field_sources`: 字段来源使用 ADR 的开放枚举；fixture 主要使用 `dom`、`embedded_json`、`list`、`url`、`none`，禁止把缺失字段伪造为 0 或空商品。
- `parser_version` / `quality_rules_version`: 可回放的规则版本。
- `should_emit_product`: 是否允许生成可上传商品对象。

页面状态枚举：`product`、`login_required`、`challenge`、`busy`、`sold_out`、`not_found`、`malformed`、`unknown`。

基础质量门禁：

1. 商品身份至少需要 `platform`、`item_id`、`item_url`，且 `page_status=product`。
2. 登录、验证、繁忙、下架、不存在、结构异常页面一律 `should_emit_product=false`。
3. 价格缺失是 `quarantined`，不允许用 `0` 代替。
4. SKU 或销量缺失可以保留商品，但必须 `warning` 且来源为 `none`；不能把销量缺失变为真实销量 0。
5. 只有 `quality_status=passed` 或规则明确允许的 `warning` 才能进入上传；`quarantined` 永远不得生成上传事件。
