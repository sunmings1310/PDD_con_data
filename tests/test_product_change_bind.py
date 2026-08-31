from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

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


class _SaveBatchCursor:
    def __init__(self) -> None:
        self.calls = []
        self._row = None

    def execute(self, sql, params=None) -> None:
        statement = " ".join(str(sql).split())
        values = dict(params or {})
        self.calls.append((statement, values))
        if statement.startswith("SELECT 1 FROM SJZQ_PRODUCT"):
            self._row = (1,)
        else:
            self._row = None

    def fetchone(self):
        row, self._row = self._row, None
        return row


class _SaveBatchConnection:
    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor


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

    def test_save_batch_uses_valid_bind_then_records_change_in_one_context(self):
        cursor = _SaveBatchCursor()
        connection = _SaveBatchConnection(cursor)

        @contextmanager
        def transaction():
            yield connection
            connection.committed = True

        before = {"product_id": 73, "task_id": None, "library_status": "draft"}
        after = {"product_id": 73, "task_id": None, "library_status": "saved"}
        tenant = SimpleNamespace(
            role_code="super_admin",
            binds={"enterprise_id": 1, "workspace_id": 1},
        )
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        user = {"user_id": 19, "username": "operator"}

        with (
            patch.object(products, "get_conn", transaction),
            patch.object(products, "_snapshot", side_effect=[before, after]),
            patch.object(products, "write_op_log"),
        ):
            result = products.save_products(
                {"product_ids": [73]}, request, user=user, tenant=tenant
            )

        self.assertTrue(result.ok)
        self.assertEqual(1, result.data["saved"])
        self.assertTrue(connection.committed)
        update_sql, update_params = next(
            (sql, params)
            for sql, params in cursor.calls
            if sql.startswith("UPDATE SJZQ_PRODUCT SET LIBRARY_STATUS='saved'")
        )
        self.assertIn("SAVED_BY=:saved_by_user_id", update_sql)
        self.assertNotIn(":uid", update_sql)
        self.assertEqual({"saved_by_user_id": 19, "id": 73}, update_params)
        change_sql, change_params = next(
            (sql, params)
            for sql, params in cursor.calls
            if sql.startswith("INSERT INTO SJZQ_PRODUCT_CHANGE")
        )
        self.assertIn(":actor_user_id", change_sql)
        self.assertEqual(19, change_params["actor_user_id"])
        self.assertLess(
            next(i for i, call in enumerate(cursor.calls) if call[0] == update_sql),
            next(i for i, call in enumerate(cursor.calls) if call[0] == change_sql),
        )


if __name__ == "__main__":
    unittest.main()
