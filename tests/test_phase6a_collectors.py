from __future__ import annotations

import unittest

from server.collectors import (
    CollectorCapability,
    CollectorException,
    CollectorRegistry,
    DynamicField,
    PlatformIdentity,
    SystemCollectorError,
    collector_registry,
)
from server.collectors.pdd import PddCollector
from server.product_quality import evaluate_product


class CollectorContractTest(unittest.TestCase):
    def test_registry_exposes_only_migrated_pdd_collector(self):
        self.assertEqual(collector_registry.platforms(), ("pinduoduo",))
        collector = collector_registry.require(" PINDUODUO ")
        self.assertTrue(collector.capabilities.supports(CollectorCapability.SEARCH))
        self.assertTrue(collector.capabilities.supports(CollectorCapability.DETAIL))
        self.assertTrue(collector.capabilities.supports(CollectorCapability.PRICE_SORT))
        self.assertTrue(collector.capabilities.supports(CollectorCapability.SALES_SORT))
        self.assertIn(DynamicField.SALES, collector.capabilities.dynamic_fields)

    def test_registry_rejects_duplicate_and_unknown_platform(self):
        registry = CollectorRegistry()
        registry.register(PddCollector())
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(PddCollector())
        with self.assertRaises(CollectorException) as raised:
            registry.require("jd")
        self.assertEqual(raised.exception.code, SystemCollectorError.PLATFORM_NOT_SUPPORTED)

    def test_pdd_identity_url_and_error_mapping_are_adapter_owned(self):
        collector = collector_registry.require("pinduoduo")
        identity = PlatformIdentity("pinduoduo", "12345678")
        self.assertTrue(collector.validate_identity(identity))
        self.assertFalse(collector.validate_identity(PlatformIdentity("pinduoduo", "abc")))
        self.assertTrue(collector.validate_item_url(identity, "https://mobile.yangkeduo.com/goods.html?goods_id=12345678"))
        self.assertFalse(collector.validate_item_url(identity, "https://example.test/?goods_id=12345678"))
        self.assertEqual(collector.map_error("login_required"), SystemCollectorError.AUTH_REQUIRED)
        self.assertEqual(collector.map_error("busy"), SystemCollectorError.RATE_LIMITED)
        self.assertEqual(collector.map_error("sold_out"), SystemCollectorError.ITEM_UNAVAILABLE)

    def test_quality_gate_preserves_pdd_url_compatibility(self):
        source = {
            "platform_code": "pinduoduo",
            "item_id": "12345678",
            "sell_name": "测试商品",
            "item_url": "https://mobile.yangkeduo.com/goods.html?goods_id=12345678",
            "page_status": "product",
            "display_price": 9.9,
            "sku_prices": "[]",
            "sales_num": 1,
        }
        self.assertTrue(evaluate_product(source).accepted)
        source["item_url"] = "https://example.test/?goods_id=12345678"
        result = evaluate_product(source)
        self.assertFalse(result.accepted)
        self.assertIn("item_url_mismatch", result.errors)


if __name__ == "__main__":
    unittest.main()
