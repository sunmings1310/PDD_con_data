from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from server.data_quality import QUALITY_RULES_VERSION, evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "phase3" / "quality_cases.json"


class Phase3QualityFixtureTest(unittest.TestCase):
    def test_fixed_offline_quality_matrix(self) -> None:
        matrix = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for case in matrix["cases"]:
            with self.subTest(case=case["name"]):
                payload = copy.deepcopy(matrix["base"])
                payload.update(case["overrides"])
                result = evaluate(SimpleNamespace(**payload), quality_rules_version=QUALITY_RULES_VERSION)
                self.assertEqual(case["accepted"], result.accepted)
                if "error" in case:
                    self.assertIn(case["error"], result.error_codes)
                if "error_prefix" in case:
                    self.assertTrue(any(code.startswith(case["error_prefix"]) for code in result.error_codes))
                if "missing" in case:
                    self.assertIn(case["missing"], result.missing_fields)
                if "warning" in case:
                    self.assertIn(case["warning"], result.warnings)


if __name__ == "__main__":
    unittest.main()
