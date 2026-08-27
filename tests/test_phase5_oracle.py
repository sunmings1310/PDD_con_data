"""Real Oracle tenant fences; enabled only against the configured sandbox schema."""

from __future__ import annotations

import os
import time
import unittest
import uuid

from server import management_queries
from server.db import close_pool, get_conn, init_pool, next_id
from server.tenant import TenantContext, list_user_contexts

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

    def test_list_user_contexts_uses_membership_role_permissions_without_cross_tenant_leakage(self):
        tag = uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            role_a = next_id(cur, "SJZQ_SEQ_ROLE")
            role_limited = next_id(cur, "SJZQ_SEQ_ROLE")
            user_id = next_id(cur, "SJZQ_SEQ_USER")
            outsider_id = next_id(cur, "SJZQ_SEQ_USER")
            enterprise_a = next_id(cur, "SJZQ_SEQ_ENTERPRISE")
            enterprise_b = next_id(cur, "SJZQ_SEQ_ENTERPRISE")
            workspace_a = next_id(cur, "SJZQ_SEQ_WORKSPACE")
            workspace_a_hidden = next_id(cur, "SJZQ_SEQ_WORKSPACE")
            workspace_b = next_id(cur, "SJZQ_SEQ_WORKSPACE")
            try:
                for role_id, suffix in ((role_a, "a"), (role_limited, "limited")):
                    cur.execute(
                        """INSERT INTO SJZQ_ROLE
                           (ROLE_ID,ROLE_CODE,ROLE_NAME) VALUES (:id,:code,:name)""",
                        {"id": role_id, "code": f"p5ctx-{suffix}-{tag}",
                         "name": f"P5 Context {suffix} {tag}"},
                    )
                for permission in ("data:view", "excel:export"):
                    cur.execute(
                        "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID,PERM_CODE) VALUES (:id,:permission)",
                        {"id": role_a, "permission": permission},
                    )
                cur.execute(
                    "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID,PERM_CODE) VALUES (:id,'task:view')",
                    {"id": role_limited},
                )

                for current_user, suffix, global_role in (
                    (user_id, "selected", role_a),
                    (outsider_id, "outsider", role_limited),
                ):
                    cur.execute(
                        """INSERT INTO SJZQ_USER
                           (USER_ID,USERNAME,PASSWORD_HASH,ROLE_ID,STATUS)
                           VALUES (:id,:username,'test-only',:role_id,'enabled')""",
                        {"id": current_user, "username": f"p5ctx-{suffix}-{tag}",
                         "role_id": global_role},
                    )

                for enterprise_id, suffix in ((enterprise_a, "a"), (enterprise_b, "b")):
                    cur.execute(
                        """INSERT INTO SJZQ_ENTERPRISE
                           (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME)
                           VALUES (:id,:code,:name)""",
                        {"id": enterprise_id, "code": f"p5ctx-{suffix}-{tag}",
                         "name": f"P5CTX {suffix.upper()} {tag}"},
                    )
                for workspace_id, enterprise_id, code, name in (
                    (workspace_a, enterprise_a, "selected", "Selected"),
                    (workspace_a_hidden, enterprise_a, "hidden", "Hidden"),
                    (workspace_b, enterprise_b, "selected", "Selected"),
                ):
                    cur.execute(
                        """INSERT INTO SJZQ_WORKSPACE
                           (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
                           VALUES (:workspace,:enterprise,:code,:name)""",
                        {"workspace": workspace_id, "enterprise": enterprise_id,
                         "code": f"{code}-{tag}", "name": f"{name} {tag}"},
                    )

                memberships = (
                    (enterprise_a, user_id, role_a),
                    (enterprise_b, user_id, role_limited),
                    (enterprise_a, outsider_id, role_limited),
                )
                for enterprise_id, member_id, role_id in memberships:
                    cur.execute(
                        """INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
                           (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID,STATUS)
                           VALUES (:id,:enterprise,:user_id,:role_id,'active')""",
                        {"id": next_id(cur, "SJZQ_SEQ_ENT_MEMBERSHIP"),
                         "enterprise": enterprise_id, "user_id": member_id,
                         "role_id": role_id},
                    )
                for enterprise_id, workspace_id, member_id, role_id in (
                    (enterprise_a, workspace_a, user_id, role_a),
                    (enterprise_a, workspace_a_hidden, outsider_id, role_limited),
                    (enterprise_b, workspace_b, user_id, role_limited),
                ):
                    cur.execute(
                        """INSERT INTO SJZQ_WORKSPACE_MEMBERSHIP
                           (ENTERPRISE_ID,WORKSPACE_ID,USER_ID,ROLE_ID)
                           VALUES (:enterprise,:workspace,:user_id,:role_id)""",
                        {"enterprise": enterprise_id, "workspace": workspace_id,
                         "user_id": member_id, "role_id": role_id},
                    )

                contexts = list_user_contexts(cur, user_id)
                self.assertEqual(
                    [(enterprise_a, workspace_a), (enterprise_b, workspace_b)],
                    [(int(item["enterprise_id"]), int(item["workspace_id"])) for item in contexts],
                )
                context_a, context_b = contexts
                self.assertEqual(role_a, int(context_a["role_id"]))
                self.assertEqual(["data:view", "excel:export"], context_a["perms"])
                self.assertEqual(role_limited, int(context_b["role_id"]))
                self.assertEqual(["task:view"], context_b["perms"])
                self.assertNotIn("data:view", context_b["perms"])
                self.assertNotIn(
                    workspace_a_hidden,
                    [int(item["workspace_id"]) for item in contexts],
                )

                outsider_contexts = list_user_contexts(cur, outsider_id)
                self.assertEqual(1, len(outsider_contexts))
                self.assertEqual(enterprise_a, int(outsider_contexts[0]["enterprise_id"]))
                self.assertEqual(workspace_a_hidden, int(outsider_contexts[0]["workspace_id"]))
                self.assertEqual(["task:view"], outsider_contexts[0]["perms"])
            finally:
                conn.rollback()
                cleanup_checks = (
                    ("SJZQ_ROLE_PERM", "ROLE_ID", (role_a, role_limited)),
                    ("SJZQ_ROLE", "ROLE_ID", (role_a, role_limited)),
                    ("SJZQ_USER", "USER_ID", (user_id, outsider_id)),
                    ("SJZQ_ENTERPRISE_MEMBERSHIP", "USER_ID", (user_id, outsider_id)),
                    ("SJZQ_WORKSPACE_MEMBERSHIP", "USER_ID", (user_id, outsider_id)),
                    ("SJZQ_WORKSPACE", "WORKSPACE_ID", (workspace_a, workspace_a_hidden, workspace_b)),
                    ("SJZQ_ENTERPRISE", "ENTERPRISE_ID", (enterprise_a, enterprise_b)),
                )
                for table, column, values in cleanup_checks:
                    binds = {f"value_{index}": value for index, value in enumerate(values)}
                    placeholders = ",".join(f":value_{index}" for index in range(len(values)))
                    cur.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} IN ({placeholders})",
                        binds,
                    )
                    self.assertEqual(0, int(cur.fetchone()[0]), table)


if __name__ == "__main__": unittest.main()
