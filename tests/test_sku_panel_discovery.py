import json
from pathlib import Path
import tempfile
import unittest

from scripts.sku_panel_discovery import build


class SkuPanelDiscoveryTest(unittest.TestCase):
    def test_build_preserves_not_observed_sku_id_and_value_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            root = tmp_path / "raw"
            capture = root / "cap-test"
            (capture / "sources").mkdir(parents=True)
            (capture / "parsed").mkdir()
            panel = {
                "before_interaction": {"nodes": [{"text": "详情"}]},
                "panel_opened": {"nodes": [{"text": "颜色"}, {"text": "黑色"}]},
                "dimension_inventory": [{"name": "颜色", "options": ["黑色"]}],
                "option_observations": [{"selected_options": ["黑色"], "selected_text": "黑色", "available": True, "selected_price": 0}],
                "interaction_guard": {"order_confirmation_clicked": False, "order_submitted": False, "payment_started": False},
            }
            panel_bytes = json.dumps(panel, ensure_ascii=False).encode()
            (capture / "sources" / "03_SKU_PANEL.json").write_bytes(panel_bytes)
            (capture / "parsed" / "product_upload.json").write_text(json.dumps({"spec": "", "spec_list": "[]"}), encoding="utf-8")
            manifest = {
                "capture_id": "cap-test", "task_id": 1, "collector_version": "test", "platform_product_id": "p1",
                "sources": [{"type": "SKU_PANEL", "storage_reference": "sources/03_SKU_PANEL.json", "sha256": "fixture", "size": len(panel_bytes)}],
                "product_upload": {"storage_reference": "parsed/product_upload.json"},
            }
            (capture / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            result = build(root, tmp_path / "out", ["cap-test"])

            self.assertEqual(0, result["raw_combinations"][0]["selected_price"])
            self.assertIsNone(result["raw_combinations"][0]["sku_id"])
            self.assertEqual("NOT_OBSERVED", result["samples"][0]["sku_id_state"])
            self.assertFalse(result["samples"][0]["order_submitted"])


if __name__ == "__main__":
    unittest.main()
