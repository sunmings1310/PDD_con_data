from __future__ import annotations

import os
import unittest
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import oracledb

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ORACLE_HOST", "127.0.0.1")
os.environ.setdefault("ORACLE_PORT", "1521")
os.environ.setdefault("ORACLE_SERVICE", "TEST")
os.environ.setdefault("ORACLE_USER", "TEST")
os.environ.setdefault("ORACLE_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET", "Test-only-JWT-secret-32-characters!")

from server.routers import products


CONFIGURED = os.getenv("T003_ORACLE_TEST_ENABLED") == "1" and all(
    os.getenv(name) for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
)


@unittest.skipUnless(CONFIGURED, "BLOCKED_BY_ENVIRONMENT: isolated Oracle test schema not configured")
class ProductChangeBindOracleTest(unittest.TestCase):
    def test_record_change_executes_and_cleans_up_in_oracle(self):
        conn = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )
        cur = conn.cursor()
        tag = "PCB-" + uuid.uuid4().hex[:20]
        product_id = 800_000_000_000_000 + uuid.uuid4().int % 100_000_000_000_000
        actor_user_id = 700_000_000 + uuid.uuid4().int % 100_000_000
        try:
            products._record_change(
                cur,
                product_id=product_id,
                action="bind_hotfix_test",
                before={"task_id": None, "tag": tag, "value": "before"},
                after={"task_id": None, "tag": tag, "value": "after"},
                user={"user_id": actor_user_id, "username": tag},
            )
            conn.commit()

            cur.execute(
                """SELECT USER_ID, USERNAME, ACTION_CODE
                     FROM SJZQ_PRODUCT_CHANGE
                    WHERE PRODUCT_ID=:product_id AND USERNAME=:test_username""",
                {"product_id": product_id, "test_username": tag},
            )
            self.assertEqual(
                (actor_user_id, tag, "bind_hotfix_test"),
                tuple(cur.fetchone()),
            )
        finally:
            cur.execute(
                "DELETE FROM SJZQ_PRODUCT_CHANGE WHERE PRODUCT_ID=:product_id AND USERNAME=:test_username",
                {"product_id": product_id, "test_username": tag},
            )
            conn.commit()
            cur.execute(
                "SELECT COUNT(*) FROM SJZQ_PRODUCT_CHANGE WHERE PRODUCT_ID=:product_id AND USERNAME=:test_username",
                {"product_id": product_id, "test_username": tag},
            )
            remaining = int(cur.fetchone()[0])
            cur.close()
            conn.close()
        self.assertEqual(0, remaining)

    def test_save_batch_updates_product_records_change_commits_and_cleans_up(self):
        conn = oracledb.connect(
            dsn=os.environ["T003_ORACLE_DSN"],
            user=os.environ["T003_ORACLE_USER"],
            password=os.environ["T003_ORACLE_PASSWORD"],
        )
        cur = conn.cursor()
        tag = "PCB-SAVE-" + uuid.uuid4().hex[:16]
        cur.execute("SELECT SJZQ_SEQ_PRODUCT.NEXTVAL FROM DUAL")
        product_id = int(cur.fetchone()[0])
        actor_user_id = 700_000_000 + uuid.uuid4().int % 100_000_000
        cur.execute(
            """INSERT INTO SJZQ_PRODUCT
                 (PRODUCT_ID,PLATFORM_CODE,PRODUCT_NAME,PRICE,LIBRARY_STATUS,IS_DELETED,
                  ENTERPRISE_ID,WORKSPACE_ID)
               VALUES (:product_id,'pinduoduo',:product_name,1,'draft',0,1,1)""",
            {"product_id": product_id, "product_name": tag},
        )
        conn.commit()

        @contextmanager
        def transaction():
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        tenant = SimpleNamespace(
            role_code="super_admin",
            binds={"enterprise_id": 1, "workspace_id": 1},
        )
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
        user = {"user_id": actor_user_id, "username": tag}
        try:
            with (
                patch.object(products, "get_conn", transaction),
                patch.object(products, "write_op_log"),
            ):
                result = products.save_products(
                    {"product_ids": [product_id]}, request, user=user, tenant=tenant
                )

            self.assertTrue(result.ok)
            self.assertEqual(1, result.data["saved"])
            cur.execute(
                "SELECT LIBRARY_STATUS,SAVED_BY FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:product_id",
                {"product_id": product_id},
            )
            self.assertEqual(("saved", actor_user_id), tuple(cur.fetchone()))
            cur.execute(
                """SELECT USER_ID,USERNAME,ACTION_CODE
                     FROM SJZQ_PRODUCT_CHANGE
                    WHERE PRODUCT_ID=:product_id AND USERNAME=:test_username""",
                {"product_id": product_id, "test_username": tag},
            )
            self.assertEqual(
                (actor_user_id, tag, "save_library"), tuple(cur.fetchone())
            )
        finally:
            cur.execute(
                "DELETE FROM SJZQ_PRODUCT_CHANGE WHERE PRODUCT_ID=:product_id",
                {"product_id": product_id},
            )
            cur.execute(
                "DELETE FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:product_id",
                {"product_id": product_id},
            )
            conn.commit()
            cur.execute(
                """SELECT
                     (SELECT COUNT(*) FROM SJZQ_PRODUCT_CHANGE WHERE PRODUCT_ID=:product_id),
                     (SELECT COUNT(*) FROM SJZQ_PRODUCT WHERE PRODUCT_ID=:product_id)
                     FROM DUAL""",
                {"product_id": product_id},
            )
            remaining = tuple(int(value) for value in cur.fetchone())
            cur.close()
            conn.close()
        self.assertEqual((0, 0), remaining)


if __name__ == "__main__":
    unittest.main()
