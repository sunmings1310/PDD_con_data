from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = ROOT / ".github/scripts/classify_oracle_scope.py"
SPEC = importlib.util.spec_from_file_location("oracle_scope", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class OracleScopeTest(unittest.TestCase):
    def test_every_canonical_oracle_test_file_is_required(self):
        for path in MODULE.CANONICAL_TEST_FILES:
            with self.subTest(path=path):
                self.assertTrue(MODULE.classify([path])[0])

    def test_canonical_runner_is_required(self):
        self.assertTrue(MODULE.classify(["scripts/test-baseline.ps1"])[0])

    def test_server_migration_and_oracle_named_tests_are_required(self):
        for path in ("server/repositories/jobs.py", "migrations/P7_001.sql", "scripts/migrate_v7.py", "tests/nested/test_oracle_contract.py"):
            with self.subTest(path=path):
                self.assertTrue(MODULE.classify([path])[0])

    def test_governance_docs_are_not_applicable(self):
        required, reason = MODULE.classify(["WORKFLOW.md", ".github/PULL_REQUEST_TEMPLATE.md"])
        self.assertFalse(required)
        self.assertEqual(reason, "no Oracle-sensitive file changed")


if __name__ == "__main__":
    unittest.main()
