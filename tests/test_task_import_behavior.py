"""Pure canonical-import behavior checks that complement the Oracle gate."""
import os
from types import SimpleNamespace
import unittest

for key, value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(key, value)

from server.task_creation_service import _targets
from server.quota import ACTIVE_TASK, release


class CanonicalImportBehaviorTests(unittest.TestCase):
    def body(self, targets):
        return SimpleNamespace(
            targets=[SimpleNamespace(model_dump=lambda target=target: target) for target in targets],
            keywords=[], source="manual", platform_code="pinduoduo",
        )

    def test_semantic_duplicate_platform_product_id_is_rejected(self):
        targets, error = _targets(self.body([
            {"row_id": "a", "source": "manual", "source_row_index": 1,
             "platform_product_id": "123", "keyword": "first"},
            {"row_id": "b", "source": "manual", "source_row_index": 2,
             "platform_product_id": "123", "keyword": "second"},
        ]))
        self.assertEqual([], targets)
        self.assertEqual("DUPLICATE_TARGET", error)

    def test_product_id_target_keeps_identity_without_title_inference(self):
        targets, error = _targets(self.body([
            {"row_id": "a", "source": "manual", "source_row_index": 1,
             "platform_product_id": "123"},
        ]))
        self.assertIsNone(error)
        self.assertEqual("123", targets[0]["platform_product_id"])
        self.assertEqual("123", targets[0]["keyword"])

    def test_legacy_release_without_reservation_or_quota_is_noop(self):
        class Cursor:
            def __init__(self): self.calls = []
            def execute(self, sql, binds): self.calls.append((sql, binds))
            def fetchone(self): return None

        cur = Cursor()
        self.assertFalse(release(cur, enterprise_id=999999, metric=ACTIVE_TASK,
                                 resource_type="legacy", resource_key="missing"))
        self.assertEqual(1, len(cur.calls))
        self.assertIn("SJZQ_QUOTA_RESERVATION", cur.calls[0][0])
        self.assertNotIn("SJZQ_ENTERPRISE_QUOTA", cur.calls[0][0])


if __name__ == "__main__":
    unittest.main()
