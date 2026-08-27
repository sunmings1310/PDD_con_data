"""Opt-in Oracle ownership/membership gate for realtime WebSocket scope."""

from __future__ import annotations

import os
import unittest
import uuid

for _key, _value in {
    "APP_ENV": "test",
    "ORACLE_HOST": "127.0.0.1",
    "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST",
    "ORACLE_USER": "TEST",
    "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server.db import close_pool, get_conn, init_pool, next_id  # noqa: E402
from server.ws_hub import (  # noqa: E402
    RealtimeChannel,
    resolve_realtime_channel,
    resolve_task_event_channel,
)

ENABLED = os.getenv("REALTIME_WS_ORACLE_TEST_ENABLED") == "1"


@unittest.skipUnless(ENABLED, "Realtime WS Oracle sandbox test not enabled")
class RealtimeWsOracleGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_pool()

    @classmethod
    def tearDownClass(cls):
        close_pool()

    def test_membership_permission_revocation_and_resource_ownership_matrix(self):
        tag = uuid.uuid4().hex[:12]
        with get_conn() as conn:
            cur = conn.cursor()
            try:
                role_view = next_id(cur, "SJZQ_SEQ_ROLE")
                role_no_view = next_id(cur, "SJZQ_SEQ_ROLE")
                for role_id, suffix in ((role_view, "view"), (role_no_view, "none")):
                    cur.execute(
                        """INSERT INTO SJZQ_ROLE
                           (ROLE_ID,ROLE_CODE,ROLE_NAME) VALUES (:id,:code,:name)""",
                        {"id": role_id, "code": f"ws-{suffix}-{tag}", "name": f"WS {suffix} {tag}"},
                    )
                cur.execute(
                    "INSERT INTO SJZQ_ROLE_PERM (ROLE_ID,PERM_CODE) VALUES (:id,'device:view')",
                    {"id": role_view},
                )

                users = {}
                for suffix, status in (("valid", "enabled"), ("no_perm", "enabled"),
                                       ("disabled", "disabled"), ("other", "enabled")):
                    user_id = next_id(cur, "SJZQ_SEQ_USER")
                    users[suffix] = user_id
                    cur.execute(
                        """INSERT INTO SJZQ_USER
                           (USER_ID,USERNAME,PASSWORD_HASH,ROLE_ID,STATUS)
                           VALUES (:id,:username,'test-only',:role_id,:status)""",
                        {"id": user_id, "username": f"ws-{suffix}-{tag}",
                         "role_id": role_view, "status": status},
                    )

                tenants = []
                for suffix in ("a", "b"):
                    enterprise_id = next_id(cur, "SJZQ_SEQ_ENTERPRISE")
                    workspace_id = next_id(cur, "SJZQ_SEQ_WORKSPACE")
                    tenants.append((enterprise_id, workspace_id))
                    cur.execute(
                        """INSERT INTO SJZQ_ENTERPRISE
                           (ENTERPRISE_ID,ENTERPRISE_CODE,ENTERPRISE_NAME)
                           VALUES (:id,:code,:name)""",
                        {"id": enterprise_id, "code": f"ws-{suffix}-{tag}",
                         "name": f"WS {suffix} {tag}"},
                    )
                    cur.execute(
                        """INSERT INTO SJZQ_WORKSPACE
                           (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
                           VALUES (:workspace,:enterprise,'main','Main')""",
                        {"workspace": workspace_id, "enterprise": enterprise_id},
                    )
                (enterprise_a, workspace_a), (enterprise_b, workspace_b) = tenants
                workspace_a2 = next_id(cur, "SJZQ_SEQ_WORKSPACE")
                cur.execute(
                    """INSERT INTO SJZQ_WORKSPACE
                       (WORKSPACE_ID,ENTERPRISE_ID,WORKSPACE_CODE,WORKSPACE_NAME)
                       VALUES (:workspace,:enterprise,'restricted','Restricted')""",
                    {"workspace": workspace_a2, "enterprise": enterprise_a},
                )

                memberships = (
                    (enterprise_a, users["valid"], role_view),
                    (enterprise_a, users["no_perm"], role_no_view),
                    (enterprise_a, users["disabled"], role_view),
                    (enterprise_b, users["other"], role_view),
                )
                for enterprise_id, user_id, role_id in memberships:
                    cur.execute(
                        """INSERT INTO SJZQ_ENTERPRISE_MEMBERSHIP
                           (MEMBERSHIP_ID,ENTERPRISE_ID,USER_ID,ROLE_ID,STATUS)
                           VALUES (:id,:enterprise,:user_id,:role_id,'active')""",
                        {"id": next_id(cur, "SJZQ_SEQ_ENT_MEMBERSHIP"),
                         "enterprise": enterprise_id, "user_id": user_id, "role_id": role_id},
                    )
                # Presence of workspace rows makes workspace membership restrictive.
                cur.execute(
                    """INSERT INTO SJZQ_WORKSPACE_MEMBERSHIP
                       (ENTERPRISE_ID,WORKSPACE_ID,USER_ID,ROLE_ID)
                       VALUES (:enterprise,:workspace,:user_id,:role_id)""",
                    {"enterprise": enterprise_a, "workspace": workspace_a,
                     "user_id": users["valid"], "role_id": role_view},
                )
                cur.execute(
                    """INSERT INTO SJZQ_WORKSPACE_MEMBERSHIP
                       (ENTERPRISE_ID,WORKSPACE_ID,USER_ID,ROLE_ID)
                       VALUES (:enterprise,:workspace,:user_id,:role_id)""",
                    {"enterprise": enterprise_b, "workspace": workspace_b,
                     "user_id": users["other"], "role_id": role_view},
                )
                cur.execute(
                    """INSERT INTO SJZQ_WORKSPACE_MEMBERSHIP
                       (ENTERPRISE_ID,WORKSPACE_ID,USER_ID,ROLE_ID)
                       VALUES (:enterprise,:workspace,:user_id,:role_id)""",
                    {"enterprise": enterprise_a, "workspace": workspace_a2,
                     "user_id": users["no_perm"], "role_id": role_no_view},
                )

                devices = {}
                for suffix, enterprise_id, workspace_id, revoked in (
                    ("a", enterprise_a, workspace_a, False),
                    ("a_other", enterprise_a, workspace_a, False),
                    ("a_workspace_2", enterprise_a, workspace_a2, False),
                    ("revoked", enterprise_a, workspace_a, True),
                    ("b", enterprise_b, workspace_b, False),
                ):
                    device_id = next_id(cur, "SJZQ_SEQ_DEVICE")
                    devices[suffix] = device_id
                    cur.execute(
                        """INSERT INTO SJZQ_DEVICE
                           (DEVICE_ID,DEVICE_KEY,DEVICE_NAME,ENTERPRISE_ID,WORKSPACE_ID,REVOKED_AT)
                           VALUES (:id,:key,:name,:enterprise,:workspace,
                                   CASE WHEN :revoked=1 THEN SYSTIMESTAMP ELSE NULL END)""",
                        {"id": device_id, "key": f"ws-{suffix}-{tag}", "name": suffix,
                         "enterprise": enterprise_id, "workspace": workspace_id,
                         "revoked": 1 if revoked else 0},
                    )

                task_a = next_id(cur, "SJZQ_SEQ_TASK")
                cur.execute(
                    """INSERT INTO SJZQ_TASK
                       (TASK_ID,TASK_NAME,TASK_TYPE,PLATFORM_CODE,STATUS,PRIORITY,DEVICE_ID,
                        TARGET_COUNT,ENTERPRISE_ID,WORKSPACE_ID)
                       VALUES (:id,:name,'collect','pinduoduo','running',5,:device,0,:enterprise,:workspace)""",
                    {"id": task_a, "name": f"ws-task-{tag}", "device": devices["a"],
                     "enterprise": enterprise_a, "workspace": workspace_a},
                )

                expected = RealtimeChannel(enterprise_a, workspace_a, devices["a"])
                self.assertEqual(expected, resolve_realtime_channel(cur, users["valid"], devices["a"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["no_perm"], devices["a"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["disabled"], devices["a"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["valid"], devices["b"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["valid"], devices["a_workspace_2"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["valid"], devices["revoked"]))
                self.assertIsNone(resolve_realtime_channel(cur, users["other"], devices["a"]))
                self.assertEqual(expected, resolve_task_event_channel(cur, task_a, devices["a"]))
                self.assertIsNone(resolve_task_event_channel(cur, task_a, devices["a_other"]))
                self.assertIsNone(resolve_task_event_channel(cur, task_a, devices["a_workspace_2"]))
                self.assertIsNone(resolve_task_event_channel(cur, task_a, devices["b"]))
                self.assertIsNone(resolve_task_event_channel(cur, task_a, devices["revoked"]))
            finally:
                # The gate never persists sample tenants, users, devices, or tasks.
                conn.rollback()


if __name__ == "__main__":
    unittest.main()
