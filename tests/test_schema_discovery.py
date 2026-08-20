from __future__ import annotations

import unittest

from scripts.schema_discovery import build_raw_only, observation_state, text_observations, variability


class SchemaDiscoveryTest(unittest.TestCase):
    def test_zero_is_value_but_missing_is_not_observed(self):
        self.assertEqual("VALUE", observation_state({"comment_num": 0, "field_sources": {"comment_num": "detail_text"}}, "comment_num"))
        self.assertEqual("NOT_OBSERVED", observation_state({"comment_num": None, "field_sources": {"comment_num": "none"}}, "comment_num"))

    def test_text_inventory_extracts_parameter_pair_and_video(self):
        rows = dict(text_observations("OTHER", "商品参数\n品牌\nTOCI\n规格类型\n常规单品\n播放"))
        self.assertEqual("TOCI", rows["$.attributes.品牌"])
        self.assertEqual("常规单品", rows["$.attributes.规格类型"])
        self.assertTrue(rows["$.ui.has_video_marker"])

    def test_variability_bands(self):
        self.assertEqual("constant", variability({"x"}, 10))
        self.assertEqual("high", variability({"a", "b", "c", "d"}, 4))

    def test_raw_only_prefers_unused_or_low_frequency_raw_fields(self):
        inventory = [{
            "source": "OTHER", "parser_used": False, "occurrence_rate": 0.25,
            "possibly_platform_specific": True, "field_path": "$.attributes.香型",
        }]
        result = build_raw_only(inventory)
        self.assertEqual(1, len(result))
        self.assertIn("Parser 未使用", result[0]["raw_only_reason"])


if __name__ == "__main__":
    unittest.main()
