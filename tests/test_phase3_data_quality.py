from __future__ import annotations

import copy
import unittest

from server.data_quality import (
    QUALITY_RULES_VERSION,
    content_sha256,
    detect_difference,
    evaluate,
    normalized_snapshot,
)


def valid(**overrides):
    value = {
        "platform_code": "pinduoduo",
        "item_id": "100000000001",
        "sell_name": "示例商品",
        "item_url": "https://mobile.yangkeduo.com/goods.html?goods_id=100000000001",
        "display_price": 12.99,
        "sales_num": 230,
        "shop_name": "示例店铺",
        "shop_id": "shop-1",
        "sku_prices": '[{"sku_id":"sku-1","price":12.99}]',
        "page_status": "product",
        "parse_status": "success",
        "quality_status": "passed",
        "field_sources": {
            "item_id": "embedded_json", "name": "detail_text", "price": "embedded_json",
            "sales_num": "dom", "shop": "detail_response", "sku": "sku_panel",
        },
        "parser_version": "pdd-android-1",
        "quality_rules_version": "phase1-1",
    }
    value.update(overrides)
    return value


class Phase3QualityGateTest(unittest.TestCase):
    def test_normal_product_is_versioned_and_traceable(self):
        decision = evaluate(valid())
        self.assertTrue(decision.accepted)
        self.assertEqual(QUALITY_RULES_VERSION, decision.quality_rules_version)
        snapshot = normalized_snapshot(valid(), decision)
        self.assertEqual("embedded_json", snapshot["field_sources"]["price"])
        self.assertEqual("detail_text", snapshot["field_sources"]["title"])
        self.assertNotIn("name", snapshot["field_sources"])
        self.assertEqual("pdd-android-1", snapshot["parser_version"])

    def test_price_empty_and_abnormal_are_quarantined(self):
        empty = evaluate(valid(price=None, display_price=None, group_price=None, deal_price=None))
        negative = evaluate(valid(display_price=-1))
        huge = evaluate(valid(display_price=10_000_001))
        self.assertIn("price", empty.missing_fields)
        self.assertIn("DISPLAY_PRICE_INVALID", negative.error_codes)
        self.assertIn("DISPLAY_PRICE_INVALID", huge.error_codes)
        self.assertFalse(empty.accepted or negative.accepted or huge.accepted)

    def test_identity_missing_or_invalid_is_quarantined(self):
        self.assertIn("platform_product_id", evaluate(valid(item_id="")).missing_fields)
        self.assertIn("IDENTITY_INVALID", evaluate(valid(item_id="not-a-number")).error_codes)

    def test_sku_missing_is_warning_but_malformed_is_quarantined(self):
        missing = evaluate(valid(sku_prices="", field_sources={
            "item_id": "embedded_json", "name": "detail_text", "price": "embedded_json",
            "sales_num": "dom", "shop": "detail_response",
        }))
        malformed = evaluate(valid(sku_prices="not-json"))
        bad_price = evaluate(valid(sku_prices='[{"price":-1}]'))
        self.assertTrue(missing.accepted)
        self.assertIn("sku_missing", missing.warnings)
        self.assertIn("SKU_INVALID_JSON", malformed.error_codes)
        self.assertIn("SKU_INVALID_PRICE", bad_price.error_codes)

    def test_sales_missing_is_null_warning_and_negative_is_error(self):
        sources = dict(valid()["field_sources"])
        sources.pop("sales_num")
        missing = evaluate(valid(sales_num=None, field_sources=sources))
        invalid = evaluate(valid(sales_num=-1))
        self.assertTrue(missing.accepted)
        self.assertIn("sales_missing", missing.warnings)
        self.assertIn("SALES_INVALID", invalid.error_codes)

    def test_abnormal_page_and_partial_parser(self):
        self.assertIn("PAGE_LOGIN_REQUIRED", evaluate(valid(page_status="login_required")).error_codes)
        partial = evaluate(valid(parse_status="partial"))
        self.assertTrue(partial.accepted)
        self.assertEqual("partial", partial.parse_status)
        failed = evaluate(valid(parse_status="failed"))
        self.assertIn("PARSE_FAILED", failed.error_codes)
        unknown = evaluate(valid(parse_status="garbage"))
        self.assertFalse(unknown.accepted)
        self.assertIn("PARSE_STATUS_UNKNOWN", unknown.error_codes)

    def test_field_source_missing_and_unknown_are_explainable(self):
        missing = evaluate(valid(field_sources={"item_id": "embedded_json"}))
        unknown_sources = copy.deepcopy(valid()["field_sources"])
        unknown_sources["price"] = "magic"
        unknown = evaluate(valid(field_sources=unknown_sources))
        self.assertTrue(any(code.startswith("FIELD_SOURCE_MISSING") for code in missing.error_codes))
        self.assertIn("FIELD_SOURCE_UNKNOWN:price:magic", unknown.error_codes)

    def test_source_aliases_are_normalized(self):
        sources = dict(valid()["field_sources"])
        sources.update({"item_id": "fixture", "price": "detail"})
        decision = evaluate(valid(field_sources=sources))
        self.assertTrue(decision.accepted)
        snapshot = normalized_snapshot(valid(field_sources=sources), decision)
        self.assertEqual("normalized_result", snapshot["field_sources"]["item_id"])
        self.assertEqual("detail_response", snapshot["field_sources"]["price"])

    def test_difference_detection_is_separate_from_quality(self):
        first_input = valid()
        first = normalized_snapshot(first_input, evaluate(first_input))
        changed_input = valid(
            display_price=10.5, sales_num=300, sell_name="新标题", shop_name="新店",
            sku_prices='[{"sku_id":"sku-1","price":10.5}]', page_status="product",
        )
        changed = normalized_snapshot(changed_input, evaluate(changed_input))
        diff = detect_difference(first, changed)
        self.assertEqual({"price", "sales", "sku", "title", "shop"}, set(diff.changed_fields))
        self.assertFalse(diff.changed("availability"))

    def test_identical_observation_has_stable_hash_and_empty_diff(self):
        source = valid()
        snapshot = normalized_snapshot(source, evaluate(source))
        self.assertEqual(content_sha256(snapshot), content_sha256(copy.deepcopy(snapshot)))
        self.assertEqual((), detect_difference(snapshot, copy.deepcopy(snapshot)).changed_fields)

    def test_parser_and_rule_versions_are_business_fields(self):
        one = valid(parser_version="pdd-android-1")
        two = valid(parser_version="pdd-android-2")
        first = normalized_snapshot(one, evaluate(one))
        second = normalized_snapshot(two, evaluate(two))
        self.assertNotEqual(content_sha256(first), content_sha256(second))
        self.assertEqual("phase3-1", first["quality_rules_version"])
        next_rules = normalized_snapshot(one, evaluate(one, quality_rules_version="phase3-2"))
        self.assertEqual("phase3-2", next_rules["quality_rules_version"])
        self.assertNotEqual(content_sha256(first), content_sha256(next_rules))


if __name__ == "__main__":
    unittest.main()
