from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from server.product_contract import (
    DYNAMIC_IMMUTABLE_FIELDS, EDITABLE_STABLE_FIELDS, EFFECTIVE_PRICE_PRIORITY,
    LEGACY_FIELD_MAP, effective_price, normalize_stable_edit,
)
from server.routers import products
from server.schemas import CaptureEditDTO, ProductDetailDTO, ProductEditDTO


MODEL = {
    "identity": {"product_id": 73, "platform_code": "pinduoduo", "platform_product_id": "985843042423"},
    "stable_profile": {
        "platform_title": "太极 藿香正气口服液 10ml*10支/盒",
        "canonical_name": "藿香正气口服液", "brand": "太极",
        "product_attribute_spec": "10ml*10支/盒", "approval_number": "国药准字Z50020409",
        "manufacturer": "太极集团重庆涪陵制药厂有限公司", "attributes": [],
    },
    "latest_observation": {"source": "legacy_product_observation", "list_price": 33.2,
                           "detail_price": 33.2, "single_purchase_price": 33.2, "sales": 66000},
    "sku": {"sku_dimensions": [], "sku_dimensions_state": "not_observed",
            "sku_combinations": [{"spec_text": "1盒", "detail_price": 33.2}],
            "source": "legacy_sku_prices_json"},
    "media": [{"media_id": 293, "media_type": "image", "url": "/media/example"}],
    "provenance": {"status": "unavailable", "reason": "legacy_product_has_no_raw_or_snapshot_link",
                   "field_sources": {}},
    "quality": {}, "capture_context": {"task_id": 51, "library_status": "saved"},
}


class _Cursor:
    def __init__(self):
        self.sql, self.description, self._row = [], [], None

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        self.sql.append(statement)
        upper = statement.upper()
        if upper.startswith("SELECT 1 FROM SJZQ_PRODUCT"):
            self.description, self._row = [("ONE",)], (1,)
        elif upper.startswith("SELECT * FROM SJZQ_PRODUCT"):
            self.description = [("PRODUCT_ID",), ("TASK_ID",), ("LIBRARY_STATUS",),
                                ("ENTERPRISE_ID",), ("WORKSPACE_ID",), ("SELL_NAME",)]
            self._row = (73, 51, "saved", 1, 1, "old title")
        else:
            self.description, self._row = [], None

    def fetchone(self): return self._row


class _Connection:
    def __init__(self, cursor): self._cursor = cursor
    def cursor(self): return self._cursor


class ProductConsistencyP0Test(unittest.TestCase):
    def test_frozen_name_spec_and_price_semantics(self):
        self.assertEqual("sell_name", LEGACY_FIELD_MAP["platform_title"])
        self.assertEqual("product_name", LEGACY_FIELD_MAP["canonical_name"])
        self.assertEqual("spec_text", LEGACY_FIELD_MAP["product_attribute_spec"])
        self.assertEqual("sku_prices_json", LEGACY_FIELD_MAP["sku_combinations"])
        self.assertEqual("single_purchase_price", EFFECTIVE_PRICE_PRIORITY[0])
        self.assertEqual(9, effective_price({"list_price": 10, "detail_price": 9}))

    def test_detail_is_complete_but_edit_dtos_have_only_stable_fields(self):
        detail = ProductDetailDTO.model_validate(MODEL)
        self.assertEqual(66000, detail.latest_observation.sales)
        self.assertEqual(1, len(detail.sku.sku_combinations))
        self.assertEqual(1, len(detail.media))
        for dto_type, scope in ((ProductEditDTO, "library"), (CaptureEditDTO, "capture")):
            payload = {"product_id": 73, "scope": scope,
                       **{key: MODEL["stable_profile"].get(key) for key in EDITABLE_STABLE_FIELDS}}
            fields = dto_type.model_validate(payload).model_dump()
            self.assertFalse(set(fields) & DYNAMIC_IMMUTABLE_FIELDS)
            self.assertEqual(MODEL["stable_profile"]["canonical_name"], fields["canonical_name"])

    def test_legacy_aliases_translate_once_and_dynamic_fields_are_unsupported(self):
        stable, unsupported = normalize_stable_edit({"sell_name": "new", "product_name": "canonical",
                                                     "price": 1, "sales_num": 2})
        self.assertEqual({"platform_title": "new", "canonical_name": "canonical"}, stable)
        self.assertEqual({"price", "sales_num"}, unsupported)

    def test_put_rejects_dynamic_observation_before_any_update(self):
        cursor = _Cursor()
        @contextmanager
        def connection(): yield _Connection(cursor)
        tenant = SimpleNamespace(role_code="super_admin", binds={"enterprise_id": 1, "workspace_id": 1})
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        with patch.object(products, "get_conn", connection):
            result = products.update_product(73, {"detail_price": 1.0}, request,
                                             user={"user_id": 1, "username": "admin"}, tenant=tenant)
        self.assertFalse(result.ok)
        self.assertEqual("OBSERVED_FIELD_IMMUTABLE", result.data["error_code"])
        self.assertFalse(any(sql.startswith("UPDATE") for sql in cursor.sql))

    def test_stable_update_never_updates_snapshot_or_raw(self):
        cursor = _Cursor()
        @contextmanager
        def connection(): yield _Connection(cursor)
        tenant = SimpleNamespace(role_code="super_admin", binds={"enterprise_id": 1, "workspace_id": 1})
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        with patch.object(products, "get_conn", connection), patch.object(products, "_record_change"), \
             patch.object(products, "write_op_log"), patch.object(products, "load_canonical_product", return_value=MODEL):
            result = products.update_product(73, {"canonical_name": "新规范名", "scope": "library"}, request,
                                             user={"user_id": 1, "username": "admin"}, tenant=tenant)
        self.assertTrue(result.ok)
        updates = [sql for sql in cursor.sql if sql.startswith("UPDATE")]
        self.assertEqual(1, len(updates))
        self.assertIn("UPDATE SJZQ_PRODUCT SET PRODUCT_NAME=:canonical_name", updates[0])
        self.assertNotIn("SNAPSHOT", updates[0])
        self.assertNotIn("RAW", updates[0])


if __name__ == "__main__": unittest.main()
