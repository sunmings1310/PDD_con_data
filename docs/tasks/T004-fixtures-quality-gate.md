# T004：离线 fixture 与成功门禁

`tests/fixtures/pinduoduo/` 保存 10 类脱敏、合法、离线 JSON 样本：正常商品、登录、验证、繁忙、下架、不存在、价格缺失、SKU 缺失、销量缺失、结构异常。

统一枚举：

- `page_status`: `product | login_required | challenge | busy | sold_out | not_found | malformed | unknown`
- `parse_status`: `success | partial | failed | not_attempted`
- `quality_status`: `passed | warning | quarantined`

Android 在写 Product/outbox 前执行 `ProductQualityGate`；服务端在持久化前重新计算最小质量结果。异常页、身份/链接不合法、名称或价格缺失均 quarantined，不生成伪商品。SKU/销量缺失保留 NULL/空值并标记 warning，不伪造为 0。

每个上传对象携带 `field_sources`、`parser_version`、`quality_rules_version`，服务端持久化这些元数据。离线 fixture contract、服务端纯质量规则、Android JVM 门禁均已纳入统一测试入口。
