from __future__ import annotations

import os
import unittest
import uuid

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


if __name__ == "__main__":
    unittest.main()
