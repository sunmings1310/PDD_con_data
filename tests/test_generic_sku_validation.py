import json
from pathlib import Path
import tempfile
import unittest

from scripts.generic_sku_validation import build


class GenericSkuValidationTest(unittest.TestCase):
    def test_zero_price_and_missing_panel_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "raw"
            for capture_id, with_panel in (("with-panel", True), ("without-panel", False)):
                directory = root / capture_id
                (directory / "parsed").mkdir(parents=True)
                (directory / "sources").mkdir()
                (directory / "parsed/product_upload.json").write_text(json.dumps({"spec_list": "[]"}), encoding="utf-8")
                sources = []
                if with_panel:
                    panel = {"dimension_inventory": [{"name": "任意名称", "options": ["A", "B"]}], "option_observations": [{"selected_options": ["A"], "selected_price": 0, "available": True}]}
                    (directory / "sources/sku.json").write_text(json.dumps(panel), encoding="utf-8")
                    sources.append({"type": "SKU_PANEL", "storage_reference": "sources/sku.json", "sha256": "fixture"})
                manifest = {"capture_id": capture_id, "sources": sources, "product_upload": {"storage_reference": "parsed/product_upload.json"}}
                (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = build(root, Path(temporary) / "out", ["with-panel", "without-panel"])
            self.assertEqual(0, result["combinations"][0]["price"])
            self.assertEqual("AVAILABLE", result["combinations"][0]["availability"])
            self.assertEqual("NOT_OBSERVED", result["samples"][1]["sku_panel_state"])


if __name__ == "__main__":
    unittest.main()
