from __future__ import annotations

import unittest

from server.product_quality import (
    PageStatus,
    ParseStatus,
    QualityStatus,
    classify_page,
    evaluate_product,
)


def valid_product(**overrides):
    value = {
        "platform_code": "pinduoduo",
        "item_id": "100000000001",
        "sell_name": "示例商品",
        "item_url": "https://mobile.yangkeduo.com/goods.html?goods_id=100000000001",
        "display_price": 12.99,
        "sales_num": 10,
        "sku_prices": '[{"name":"单件","price":12.99}]',
        "page_status": "product",
    }
    value.update(overrides)
    return value


class ProductQualityTest(unittest.TestCase):
    def test_page_classifier_rejects_non_product_states(self):
        cases = {
            "手机号登录 登录后继续": PageStatus.LOGIN_REQUIRED,
            "操作频繁 请完成验证后继续": PageStatus.CHALLENGE,
            "系统繁忙 请稍后再试": PageStatus.BUSY,
            "商品已下架 看看其他商品": PageStatus.SOLD_OUT,
            "抱歉 商品不存在": PageStatus.NOT_FOUND,
            "完全不认识的页面": PageStatus.MALFORMED,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify_page(text), expected)

    def test_normal_product_passes(self):
        result = evaluate_product(valid_product())
        self.assertTrue(result.accepted)
        self.assertEqual(result.parse_status, ParseStatus.SUCCESS)
        self.assertEqual(result.quality_status, QualityStatus.PASSED)

    def test_optional_sku_and_sales_are_warning_not_zero(self):
        result = evaluate_product(valid_product(sku_prices="", sku_prices_text="", sales_num=None))
        self.assertTrue(result.accepted)
        self.assertEqual(result.parse_status, ParseStatus.PARTIAL)
        self.assertEqual(result.quality_status, QualityStatus.WARNING)
        self.assertEqual(set(result.warnings), {"sku_missing", "sales_missing"})

    def test_missing_price_is_quarantined(self):
        result = evaluate_product(
            valid_product(price=None, display_price=None, group_price=None, deal_price=None)
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.parse_status, ParseStatus.FAILED)
        self.assertEqual(result.quality_status, QualityStatus.QUARANTINED)
        self.assertIn("price", result.missing_fields)

    def test_item_url_must_match_pdd_item_id(self):
        result = evaluate_product(
            valid_product(item_url="https://mobile.yangkeduo.com/goods.html?goods_id=999")
        )
        self.assertFalse(result.accepted)
        self.assertIn("item_url_mismatch", result.errors)

    def test_abnormal_page_never_emits_product_even_with_fields(self):
        for status in (
            "login_required",
            "challenge",
            "busy",
            "sold_out",
            "not_found",
            "malformed",
        ):
            with self.subTest(status=status):
                result = evaluate_product(valid_product(page_status=status))
                self.assertFalse(result.accepted)
                self.assertEqual(result.parse_status, ParseStatus.NOT_ATTEMPTED)
                self.assertEqual(result.quality_status, QualityStatus.QUARANTINED)


if __name__ == "__main__":
    unittest.main()
