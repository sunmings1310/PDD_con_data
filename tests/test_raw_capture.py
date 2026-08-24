from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "raw-capture-test-secret-20260819-0123456789")

from server.raw_capture import (
    RawCaptureError,
    persist_raw_capture,
    replay_capture,
    resanitize_capture,
    verify_capture,
)
from server.routers.products import _raw_capture_result, _receipt_ack, media_ping
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
    @staticmethod
    def capture_dir(root: Path, capture_id: str, enterprise_id: int = 1, workspace_id: int = 1) -> Path:
        return root / f"enterprise-{enterprise_id}" / f"workspace-{workspace_id}" / capture_id

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
            self.assertTrue(verify_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
            )["hashes_valid"])
            replay = replay_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
            )
            self.assertTrue(replay["quality_gate"]["accepted"])
            self.assertFalse(replay["network_access"])
            capture_dir = self.capture_dir(root, manifest["capture_id"])
            stored = (capture_dir / "parsed" / "product_upload.json").read_text("utf-8")
            self.assertNotIn("device_key", stored)
            self.assertNotIn("lease_token", stored)
            detail = (capture_dir / "sources" / "02_DETAIL.txt").read_text("utf-8")
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
            self.assertTrue(verify_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
            )["hashes_valid"])

    def test_resanitize_creates_derived_evidence_without_mutating_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = valid_body("cap-1123-resanitize")
            manifest = persist_raw_capture(
                body, {"device_id": 6, "enterprise_id": 1, "workspace_id": 1}, root=root,
            )
            original = self.capture_dir(root, manifest["capture_id"])
            original_manifest = (original / "manifest.json").read_bytes()
            original_files = {
                source["storage_reference"]: (original / source["storage_reference"]).read_bytes()
                for source in manifest["sources"]
            }

            derived = resanitize_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
                filter_version="review-filter-v2", reason="review immutability proof",
            )

            self.assertEqual(original_manifest, (original / "manifest.json").read_bytes())
            for reference, expected in original_files.items():
                self.assertEqual(expected, (original / reference).read_bytes())
            self.assertEqual(manifest["capture_id"], derived["original_capture_id"])
            self.assertEqual("review-filter-v2", derived["filter_version"])
            self.assertIn("original_source_hashes", derived)
            self.assertIn("content_sha256", derived)
            self.assertTrue((original / "derived" / derived["derived_capture_id"] / "manifest.json").is_file())
            original_replay = replay_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
                version="original",
            )
            derived_replay = replay_capture(
                manifest["capture_id"], root=root, enterprise_id=1, workspace_id=1,
                version=derived["derived_capture_id"],
            )
            self.assertFalse(original_replay["derived"])
            self.assertTrue(derived_replay["derived"])

    def test_capture_identity_is_strictly_idempotent_within_tenant_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = valid_body("cap-1123-idempotent")
            device = {"device_id": 6, "enterprise_id": 1, "workspace_id": 1}
            first = persist_raw_capture(body, device, root=root)
            retry = persist_raw_capture(body, device, root=root)
            self.assertEqual(first["identity_sha256"], retry["identity_sha256"])
            self.assertEqual(first["content_sha256"], retry["content_sha256"])

    def test_same_capture_id_rejects_changed_payload_product_or_attempt(self):
        mutations = []
        original = valid_body("cap-1123-conflict")
        changed_raw = dict(original.raw_capture)
        changed_sources = [dict(source) for source in changed_raw["sources"]]
        changed_sources[1]["payload"] = "不同商品事实 ￥99.00"
        changed_raw["sources"] = changed_sources
        mutations.append(original.model_copy(update={"raw_capture": changed_raw}))

        changed_product_raw = dict(original.raw_capture)
        changed_product_raw["platform_product_id"] = "972503815109"
        mutations.append(original.model_copy(update={"item_id": "972503815109", "raw_capture": changed_product_raw}))
        mutations.append(original.model_copy(update={"task_id": 1124}))
        mutations.append(original.model_copy(update={"job_id": 322}))
        mutations.append(original.model_copy(update={"attempt_id": 331}))

        for index, conflicting in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                device = {"device_id": 6, "enterprise_id": 1, "workspace_id": 1}
                persist_raw_capture(original, device, root=root)
                with self.assertRaises(RawCaptureError) as raised:
                    persist_raw_capture(conflicting, device, root=root)
                self.assertEqual("RAW_CAPTURE_CONFLICT", raised.exception.code)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist_raw_capture(
                original, {"device_id": 6, "enterprise_id": 1, "workspace_id": 1}, root=root,
            )
            with self.assertRaises(RawCaptureError) as raised:
                persist_raw_capture(
                    original, {"device_id": 7, "enterprise_id": 1, "workspace_id": 1}, root=root,
                )
            self.assertEqual("RAW_CAPTURE_CONFLICT", raised.exception.code)

    def test_same_capture_id_isolated_across_enterprise_and_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = valid_body("cap-1123-tenant-scope")
            first = persist_raw_capture(
                body, {"device_id": 6, "enterprise_id": 1, "workspace_id": 1}, root=root,
            )
            other_enterprise = persist_raw_capture(
                body, {"device_id": 7, "enterprise_id": 2, "workspace_id": 1}, root=root,
            )
            other_workspace = persist_raw_capture(
                body, {"device_id": 8, "enterprise_id": 1, "workspace_id": 2}, root=root,
            )
            self.assertEqual(1, first["enterprise_id"])
            self.assertEqual(2, other_enterprise["enterprise_id"])
            self.assertEqual(2, other_workspace["workspace_id"])
            self.assertTrue(self.capture_dir(root, body.raw_capture["capture_id"], 1, 1).is_dir())
            self.assertTrue(self.capture_dir(root, body.raw_capture["capture_id"], 2, 1).is_dir())
            self.assertTrue(self.capture_dir(root, body.raw_capture["capture_id"], 1, 2).is_dir())
            with self.assertRaises(FileNotFoundError):
                verify_capture(body.raw_capture["capture_id"], root=root)

    def test_api_raw_references_are_opaque_not_filesystem_paths(self):
        result = _raw_capture_result({"capture_id": "cap-1123-opaque-ref"})
        self.assertEqual("cap-1123-opaque-ref", result["capture_id"])
        self.assertNotIn("capture_manifest", result)
        for value in result.values():
            self.assertFalse(Path(value).is_absolute())
            self.assertNotRegex(value, r"^[A-Za-z]:[\\/]")
        ping_data = media_ping().data
        rendered = json.dumps(ping_data, ensure_ascii=False)
        self.assertNotRegex(rendered, r"[A-Za-z]:[\\/]")
        self.assertNotIn("/home/", rendered)
        self.assertNotIn("image_dir", ping_data)
        replay = _receipt_ack({
            "result": {
                "capture_id": "cap-1123-opaque-ref",
                "capture_manifest": r"D:\server\raw-captures\cap-1123-opaque-ref\manifest.json",
            },
            "product_id": 9,
            "status": "acked",
        }, "receipt-key")
        replay_rendered = json.dumps(replay.data, ensure_ascii=False)
        self.assertNotIn("capture_manifest", replay.data)
        self.assertNotRegex(replay_rendered, r"[A-Za-z]:[\\/]")


if __name__ == "__main__":
    unittest.main()
