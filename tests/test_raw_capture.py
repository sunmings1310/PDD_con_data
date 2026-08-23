from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "raw-capture-test-secret-20260819-0123456789")

from server.raw_capture import persist_raw_capture, replay_capture, verify_capture
from server.data_quality import evaluate
from server.schemas import ProductUploadIn


def valid_body(capture_id: str = "cap-1123-12345678") -> ProductUploadIn:
    return ProductUploadIn(
        device_key="must-not-persist",
        lease_token="x" * 40,
        idempotency_key="product-raw-capture-1",
        task_id=1123,
        job_id=321,
        attempt_id=330,
        worker_id="android-device-6",
        platform_code="pinduoduo",
        item_id="972503815108",
        sell_name="真实测试商品",
        display_price=44.37,
        sales_num=100,
        sku_prices='[{"sku_id":"one","price":44.37}]',
        page_status="product",
        parse_status="success",
        quality_status="passed",
        field_sources={"item_id":"embedded_json", "title":"detail_text", "price":"detail_text", "sales_num":"dom", "sku":"sku_panel"},
        parser_version="pdd-android-1",
        quality_rules_version="phase3-1",
        raw_capture={
            "capture_id": capture_id,
            "platform": "pinduoduo",
            "platform_product_id": "972503815108",
            "collector_version": "1.0.76",
            "parser_version": "pdd-android-1",
            "sources": [
                {"type":"SEARCH", "source_identifier":"search-card:0", "content_type":"application/json", "payload":json.dumps({"title_hint":"真实测试商品", "page_text":"搜索结果"}, ensure_ascii=False)},
                {"type":"DETAIL", "source_identifier":"goods-detail", "payload":"真实测试商品\n￥44.37\nAuthorization: secret\n短信通知：个人消息\n电池电量为百分之 41。"},
                {"type":"SKU", "source_identifier":"sku-panel", "payload":"规格 一件 ￥44.37"},
            ],
        },
    )


class RawCaptureTest(unittest.TestCase):
    def test_empty_sku_array_is_not_observed(self):
        body = valid_body().model_copy(update={"sku_prices": "[]", "field_sources": {"item_id":"embedded_json", "title":"detail_text", "price":"detail_text", "sales_num":"dom", "sku":"none"}})
        decision = evaluate(body.model_dump())
        self.assertIn("sku_missing", decision.warnings)

    def test_persist_verify_and_offline_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = persist_raw_capture(
                valid_body(),
                {"device_id":6, "enterprise_id":1, "workspace_id":1},
                root=root,
            )
            self.assertEqual(["SEARCH", "DETAIL", "SKU"], [s["type"] for s in manifest["sources"]])
            self.assertTrue(verify_capture(manifest["capture_id"], root=root)["hashes_valid"])
            replay = replay_capture(manifest["capture_id"], root=root)
            self.assertTrue(replay["quality_gate"]["accepted"])
            self.assertFalse(replay["network_access"])
            stored = (root / manifest["capture_id"] / "parsed" / "product_upload.json").read_text("utf-8")
            self.assertNotIn("device_key", stored)
            self.assertNotIn("lease_token", stored)
            detail = (root / manifest["capture_id"] / "sources" / "02_DETAIL.txt").read_text("utf-8")
            self.assertNotIn("secret", detail)
            self.assertNotIn("个人消息", detail)

    def test_invalid_declared_json_is_preserved_as_raw_text(self):
        body = valid_body("cap-1123-invalid-json")
        raw_capture = dict(body.raw_capture)
        sources = [dict(source) for source in raw_capture["sources"]]
        sources[0]["payload"] = ""
        raw_capture["sources"] = sources
        body = body.model_copy(update={"raw_capture": raw_capture})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = persist_raw_capture(
                body,
                {"device_id": 6, "enterprise_id": 1, "workspace_id": 1},
                root=root,
            )
            search = manifest["sources"][0]
            self.assertEqual("invalid_json_preserved_as_text", search["parse_status"])
            self.assertEqual("application/json", search["declared_content_type"])
            self.assertTrue(search["storage_reference"].endswith("_SEARCH.txt"))
            self.assertTrue(verify_capture(manifest["capture_id"], root=root)["hashes_valid"])


if __name__ == "__main__":
    unittest.main()
