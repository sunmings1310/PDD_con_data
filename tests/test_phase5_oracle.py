"""Real Oracle tenant fences; enabled only against the configured sandbox schema."""

from __future__ import annotations

import os
import time
import unittest

from server import management_queries
from server.db import get_conn, init_pool, close_pool
from server.tenant import TenantContext

ENABLED = os.getenv("PHASE5_ORACLE_TEST_ENABLED") == "1"


@unittest.skipUnless(ENABLED, "Phase 5 Oracle sandbox test not enabled")
class Phase5OracleIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_pool()

    @classmethod
    def tearDownClass(cls):
        close_pool()

    def test_cross_tenant_task_id_and_pagination_are_isolated(self):
        seed = int(time.time() * 1000) % 100000000
        ea, eb, wa, wb = 800000000 + seed, 810000000 + seed, 820000000 + seed, 830000000 + seed
        ta, tb = 840000000 + seed, 850000000 + seed
        with get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO SJZQ_ENTERPRISE (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME) VALUES (:id,:code,:name)",
                            {"id":ea,"code":f"p5a{seed}","name":"P5 A"})
                cur.execute("INSERT INTO SJZQ_ENTERPRISE (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME) VALUES (:id,:code,:name)",
                            {"id":eb,"code":f"p5b{seed}","name":"P5 B"})
                cur.execute("INSERT INTO SJZQ_WORKSPACE (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME) VALUES (:w,:e,'main','Main')", {"w":wa,"e":ea})
                cur.execute("INSERT INTO SJZQ_WORKSPACE (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME) VALUES (:w,:e,'main','Main')", {"w":wb,"e":eb})
                base = """INSERT INTO SJZQ_TASK
                    (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,TARGET_COUNT,ENTERPRISE_ID,WORKSPACE_ID)
                    VALUES (:task_id,:name,'collect','pinduoduo','pending',5,0,:enterprise_id,:workspace_id)"""
                cur.execute(base,{"task_id":ta,"name":"A private","enterprise_id":ea,"workspace_id":wa})
                cur.execute(base,{"task_id":tb,"name":"B private","enterprise_id":eb,"workspace_id":wb})
                ctx_a = TenantContext(ea,wa,1,1,"viewer",frozenset({"task:view"}))
                self.assertIsNotNone(management_queries.task_trace(cur,ta,tenant=ctx_a))
                self.assertIsNone(management_queries.task_trace(cur,tb,tenant=ctx_a))
                cur.execute("SELECT COUNT(*) FROM SJZQ_TASK WHERE ENTERPRISE_ID=:e AND WORKSPACE_ID=:w", {"e":ea,"w":wa})
                self.assertEqual(int(cur.fetchone()[0]),1)
            finally:
                conn.rollback()

    def test_migration_is_applied_with_expected_checksum(self):
        with get_conn() as conn:
            cur=conn.cursor()
            cur.execute("SELECT STATUS,CHECKSUM FROM SJZQ_SCHEMA_MIGRATION WHERE VERSION_ID='P5_001_ENTERPRISE_TENANCY'")
            row=cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(str(row[0]).lower(),"applied")
            self.assertEqual(len(str(row[1])),64)


if __name__ == "__main__": unittest.main()
