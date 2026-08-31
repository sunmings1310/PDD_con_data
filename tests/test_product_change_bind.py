from __future__ import annotations

import os
import unittest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server.routers import products


class _RecordingCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = {}

    def execute(self, sql, params=None) -> None:
        self.sql = " ".join(str(sql).split())
        self.params = dict(params or {})


class ProductChangeBindContractTest(unittest.TestCase):
    def test_record_change_uses_non_reserved_actor_user_bind(self):
        cursor = _RecordingCursor()

        products._record_change(
            cursor,
            product_id=73,
            action="update",
            before={"task_id": 51, "product_name": "before"},
            after={"task_id": 51, "product_name": "after"},
            user={"user_id": 19, "username": "operator"},
        )

        self.assertIn("USER_ID, USERNAME", cursor.sql)
        self.assertIn(":actor_user_id", cursor.sql)
        self.assertNotIn(":uid", cursor.sql)
        self.assertEqual(19, cursor.params["actor_user_id"])
        self.assertNotIn("uid", cursor.params)
        self.assertEqual(
            {"pid", "tid", "action", "before_v", "after_v", "actor_user_id", "username"},
            set(cursor.params),
        )


if __name__ == "__main__":
    unittest.main()
