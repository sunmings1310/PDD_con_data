"""Contract coverage for tenant-scoped Product timeline resource IDs."""
from __future__ import annotations

import os
from pathlib import Path
import unittest

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server import management_queries as queries
from server.tenant import TenantContext


ROOT = Path(__file__).resolve().parents[1]
TENANT_A = TenantContext(11, 101, 1, 1, "viewer", frozenset({"data:view"}))


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.description = []
        self.rows = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), dict(params or {})))
        columns, rows = self.responses.pop(0)
        self.description = [(name,) for name in columns]
        self.rows = list(rows)

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class ProductTimelineResourceIdTest(unittest.TestCase):
    def test_tenant_snapshot_route_resolves_enterprise_product_resource_before_internal_master(self):
        product_columns = ["MASTER_PRODUCT_ID", "PLATFORM_CODE", "PLATFORM_PRODUCT_ID", "STATUS", "FIRST_SEEN_AT", "LAST_SEEN_AT"]
        cursor = Cursor([
            (["IDENTITY_ID"], [(600,)]),
            (product_columns, [(600, "pinduoduo", "1182", "active", "a", "b")]),
            (["COUNT"], [(1,)]),
            (["SNAPSHOT_ID", "MASTER_PRODUCT_ID", "SKU_JSON", "DIFF_ID", "CHANGED_FIELDS_JSON", "PRICE_CHANGED", "SALES_CHANGED", "SKU_CHANGED", "AVAILABILITY_CHANGED", "TITLE_CHANGED", "SHOP_CHANGED"], [(1050, 600, None, None, None, 0, 0, 0, 0, 0, 0)]),
            (["SNAPSHOT_ID", "FIELD_NAME", "SOURCE_TYPE", "SOURCE_REF", "TRANSFORMATION"], []),
        ])

        result = queries.list_snapshots(cursor, 588, page=1, limit=20, tenant=TENANT_A)

        self.assertEqual((600, 1050), (result["product"]["master_product_id"], result["items"][0]["snapshot_id"]))
        owner_sql, owner_params = cursor.calls[0]
        self.assertIn("ENTERPRISE_PRODUCT_ID=:enterprise_product_id", owner_sql)
        self.assertEqual({"enterprise_product_id": 588, "enterprise_id": 11}, owner_params)
        self.assertIn("s.ENTERPRISE_ID=:enterprise_id AND s.WORKSPACE_ID=:workspace_id", cursor.calls[3][0])

    def test_product_and_quarantine_timeline_entries_use_enterprise_product_id(self):
        products_api = (ROOT / "server/routers/products.py").read_text(encoding="utf-8")
        product_list = (ROOT / "web/src/views/data/ProductList.vue").read_text(encoding="utf-8")
        quarantine_list = (ROOT / "web/src/views/management/QuarantineList.vue").read_text(encoding="utf-8")
        management_router = (ROOT / "server/routers/management.py").read_text(encoding="utf-8")

        list_block = products_api[products_api.index("def list_products("):products_api.index("def _attach_product_images")]
        self.assertIn("ENTERPRISE_PRODUCT_ID", list_block)
        self.assertIn("row.enterprise_product_id", product_list)
        self.assertNotIn("row.master_product_id}/timeline", product_list)
        self.assertIn("detail.enterprise_product_id", quarantine_list)
        self.assertNotIn("detail.master_product_id}/timeline", quarantine_list)
        self.assertIn("/products/{enterprise_product_id}/snapshots", management_router)


if __name__ == "__main__":
    unittest.main()
