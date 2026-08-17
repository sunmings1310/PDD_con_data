"""T004 offline fixture and minimum quality-gate contract tests.

These tests deliberately use only JSON fixtures.  They do not navigate or issue
HTTP requests; the fixture metadata is the replay contract consumed by future
page-state/quality implementations.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from detail_parser import _compose_detail


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pinduoduo"
REQUIRED_FIELDS = {
    "fixture_id",
    "page_status",
    "parse_status",
    "quality_status",
    "field_sources",
    "parser_version",
    "quality_rules_version",
    "should_emit_product",
    "page_url",
    "page_text",
    "detail_raw",
    "expected",
}
PAGE_STATUSES = {
    "product",
    "login_required",
    "challenge",
    "busy",
    "sold_out",
    "not_found",
    "malformed",
}
PARSE_STATUSES = {"success", "not_attempted", "partial", "failed"}
QUALITY_STATUSES = {"passed", "warning", "quarantined"}
FIELD_SOURCE_VALUES = {
    "list_card", "detail_text", "sku_panel", "share_link", "network",
    "embedded_json", "dom", "list", "url", "inferred", "derived", "none",
}
ABNORMAL_PAGE_STATUSES = PAGE_STATUSES - {"product"}


def load_fixtures() -> list[dict[str, Any]]:
    fixtures = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        value["_path"] = path
        fixtures.append(value)
    return fixtures


def fixture_quality_gate(record: dict[str, Any]) -> bool:
    """Reference gate for the fixture contract.

    The production collector must make the same decision before upload.  Keeping
    this small and deterministic lets CI prove the expected policy without a
    browser or Oracle connection.
    """

    if record["page_status"] != "product":
        return False
    if record["quality_status"] == "quarantined":
        return False
    raw = record.get("detail_raw") or {}
    item_id = str(raw.get("item_id") or "").strip()
    title = str(raw.get("sell_name") or raw.get("product_name") or "").strip()
    has_price = any(
        any(float(value) > 0 for value in (raw.get(key) if isinstance(raw.get(key), list) else [raw.get(key)]) if value not in (None, ""))
        for key in ("display_price", "panel_price", "group_price_candidates", "single_price_candidates")
    )
    return bool(item_id and title and record.get("page_url") and has_price)


class CollectionFixtureContractTest(unittest.TestCase):
    def test_fixture_inventory_covers_required_states(self):
        fixtures = load_fixtures()
        self.assertGreaterEqual(len(fixtures), 10)
        statuses = {fixture["page_status"] for fixture in fixtures}
        self.assertTrue(PAGE_STATUSES <= statuses)
        descriptions = " ".join(fixture["description"] for fixture in fixtures)
        for marker in ("价格缺失", "SKU", "销量缺失", "结构"):
            self.assertIn(marker, descriptions)

    def test_schema_and_version_metadata_are_present(self):
        for fixture in load_fixtures():
            with self.subTest(path=str(fixture["_path"])):
                self.assertTrue(REQUIRED_FIELDS <= fixture.keys())
                self.assertIn(fixture["page_status"], PAGE_STATUSES)
                self.assertIn(fixture["parse_status"], PARSE_STATUSES)
                self.assertIn(fixture["quality_status"], QUALITY_STATUSES)
                self.assertEqual(fixture["parser_version"], "pdd-android-1")
                self.assertEqual(fixture["quality_rules_version"], "phase1-1")
                self.assertEqual(fixture["platform"], "pinduoduo")
                self.assertTrue(fixture["page_url"].startswith("https://"))
                self.assertIsInstance(fixture["field_sources"], dict)
                self.assertTrue(set(fixture["field_sources"].values()) <= FIELD_SOURCE_VALUES)

    def test_abnormal_pages_never_emit_pseudo_products(self):
        for fixture in load_fixtures():
            if fixture["page_status"] not in ABNORMAL_PAGE_STATUSES:
                continue
            with self.subTest(path=str(fixture["_path"])):
                self.assertFalse(fixture["should_emit_product"])
                self.assertFalse(fixture_quality_gate(fixture))
                self.assertEqual(fixture["quality_status"], "quarantined")
                self.assertIn(fixture["parse_status"], {"not_attempted", "failed"})

    def test_missing_price_is_rejected_without_zero_substitution(self):
        fixture = next(x for x in load_fixtures() if x["fixture_id"] == "pdd-price-missing-001")
        self.assertFalse(fixture["should_emit_product"])
        self.assertEqual(fixture["quality_status"], "quarantined")
        self.assertEqual(fixture["field_sources"]["price"], "none")
        self.assertNotIn(0, fixture["detail_raw"].get("group_price_candidates", []))
        self.assertFalse(fixture_quality_gate(fixture))

    def test_missing_optional_fields_are_explicit_warnings(self):
        for fixture_id, field, expected_count in (
            ("pdd-sku-missing-001", "sku", 0),
            ("pdd-sales-missing-001", "sales_num", None),
        ):
            fixture = next(x for x in load_fixtures() if x["fixture_id"] == fixture_id)
            with self.subTest(fixture_id=fixture_id):
                self.assertTrue(fixture["should_emit_product"])
                self.assertEqual(fixture["quality_status"], "warning")
                self.assertEqual(fixture["field_sources"][field], "none")
                if field == "sku":
                    self.assertEqual(len(fixture["detail_raw"].get("sku_rows") or []), expected_count)
                else:
                    self.assertIn(fixture["detail_raw"].get("sales_raw"), (None, ""))

    def test_normal_fixture_replays_current_parser_without_network(self):
        fixture = next(x for x in load_fixtures() if x["fixture_id"] == "pdd-normal-001")
        self.assertTrue(fixture_quality_gate(fixture))
        result = _compose_detail(
            fixture["detail_raw"],
            {
                "item_id": fixture["expected"]["item_id"],
                "price": 15.99,
                "item_url": fixture["page_url"],
            },
            fixture["page_url"],
        )
        expected = fixture["expected"]
        self.assertEqual(result["item_id"], expected["item_id"])
        self.assertEqual(result["title"], expected["title"])
        self.assertEqual(result["price"], expected["price"])
        self.assertEqual(result["group_price"], expected["group_price"])
        self.assertEqual(result["deal_price"], expected["deal_price"])
        self.assertEqual(result["sales_num"], expected["sales_num"])
        self.assertEqual(len(result["sku_prices"]), expected["sku_count"])


if __name__ == "__main__":
    unittest.main()
