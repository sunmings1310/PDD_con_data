from __future__ import annotations

import os
import unittest
from pathlib import Path

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server.device_enrollment import consume, token_hash  # noqa: E402
from server.quota import ACTIVE_TASK, QuotaExceeded, reserve_and_commit  # noqa: E402
from server.schema_migrations import P55_TABLES  # noqa: E402


class EnrollmentCursor:
    def __init__(self, digest: str):
        self.digest = digest
        self.status = "active"
        self.rowcount = 0
        self._row = None

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).upper()
        params = params or {}
        self.rowcount = 0
        if normalized.startswith("SELECT TOKEN_ID"):
            self._row = (9, 101, 202, self.status, 1) if params.get("token_hash") == self.digest else None
        elif normalized.startswith("UPDATE SJZQ_DEVICE_ENROLL_TOKEN SET STATUS='USED'"):
            if self.status == "active":
                self.status, self.rowcount = "used", 1
            else:
                self.rowcount = 0
        else:
            self._row = None

    def fetchone(self):
        row, self._row = self._row, None
        return row


class QuotaCursor:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self.reserved = 0
        self.seq = 0
        self.reservations = {}
        self._row = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        n = " ".join(sql.split()).upper()
        p = params or {}
        self._row, self.rowcount = None, 0
        if "FROM SJZQ_QUOTA_RESERVATION" in n and "resource_key" in p:
            found = next((r for r in self.reservations.values() if r["resource_key"] == p["resource_key"]), None)
            self._row = (found["id"], found["status"], found["amount"]) if found else None
        elif n.startswith("SELECT USED_VALUE,RESERVED_VALUE FROM SJZQ_QUOTA_USAGE"):
            self._row = (self.used, self.reserved)
        elif n.startswith("SELECT MAX_ACTIVE_TASKS"):
            self._row = (self.limit,)
        elif ".NEXTVAL FROM DUAL" in n:
            self.seq += 1
            self._row = (self.seq,)
        elif n.startswith("INSERT INTO SJZQ_QUOTA_RESERVATION"):
            self.reservations[p["id"]] = {"id": p["id"], "enterprise_id": p["enterprise_id"],
                "workspace_id": p["workspace_id"], "metric": p["metric"], "period": p["period"],
                "amount": p["amount"], "resource_type": p["resource_type"],
                "resource_key": p["resource_key"], "status": "held"}
        elif n.startswith("UPDATE SJZQ_QUOTA_USAGE SET RESERVED_VALUE=RESERVED_VALUE+"):
            self.reserved += p["amount"]
        elif n.startswith("SELECT ENTERPRISE_ID,WORKSPACE_ID,METRIC_CODE"):
            r = self.reservations[p["id"]]
            self._row = (r["enterprise_id"], r["workspace_id"], r["metric"], r["period"],
                         r["amount"], r["resource_type"], r["resource_key"], r["status"])
        elif "SET RESERVED_VALUE=RESERVED_VALUE-" in n:
            self.reserved -= p["amount"]
            self.used += p["amount"]
        elif n.startswith("UPDATE SJZQ_QUOTA_RESERVATION SET STATUS='COMMITTED'"):
            self.reservations[p["id"]]["status"] = "committed"

    def fetchone(self):
        row, self._row = self._row, None
        return row


class Phase55EnterpriseHardeningTest(unittest.TestCase):
    def test_enrollment_token_is_hash_only_and_consumed_once(self):
        bearer = "enr_once-only-secret-value"
        cur = EnrollmentCursor(token_hash(bearer))
        scope = consume(cur, bearer=bearer, device_id=77)
        self.assertEqual((scope.enterprise_id, scope.workspace_id), (101, 202))
        with self.assertRaisesRegex(ValueError, "ALREADY_USED_OR_REVOKED"):
            consume(cur, bearer=bearer, device_id=78)
        ddl = "\n".join(value for _, value in P55_TABLES)
        self.assertIn("TOKEN_HASH VARCHAR2(64)", ddl)
        self.assertNotIn("TOKEN_VALUE", ddl)

    def test_quota_reservation_serializes_and_rejects_second_writer(self):
        cur = QuotaCursor(limit=1)
        first = reserve_and_commit(cur, enterprise_id=5, workspace_id=6, metric=ACTIVE_TASK,
                                   amount=1, resource_type="task", resource_key="100")
        self.assertEqual((first.status, cur.used, cur.reserved), ("committed", 1, 0))
        with self.assertRaises(QuotaExceeded):
            reserve_and_commit(cur, enterprise_id=5, workspace_id=6, metric=ACTIVE_TASK,
                               amount=1, resource_type="task", resource_key="101")
        source = Path("server/quota.py").read_text(encoding="utf-8")
        self.assertIn("SJZQ_QUOTA_USAGE", source)
        self.assertIn("FOR UPDATE", source)
        self.assertIn("used + held + amount > maximum", source)

    def test_revoked_device_is_fenced_from_agent_and_cast_paths(self):
        services = Path("server/services.py").read_text(encoding="utf-8")
        devices = Path("server/routers/devices.py").read_text(encoding="utf-8")
        cast = Path("server/routers/cast.py").read_text(encoding="utf-8")
        self.assertIn("REVOKED_AT IS NULL", services)
        self.assertIn('"DEVICE_REVOKED"', devices)
        self.assertIn("get_device_by_key(cur, device_key)", cast)

    def test_side_paths_have_tenant_context_and_static_media_bypass_is_closed(self):
        for path in ("server/routers/accounts.py", "server/routers/ota.py",
                     "server/routers/cast.py", "server/routers/excel_match.py"):
            source = Path(path).read_text(encoding="utf-8")
            self.assertIn("require_tenant_perms", source, path)
            self.assertIn("ENTERPRISE_ID", source.upper(), path)
            self.assertIn("WORKSPACE_ID", source.upper(), path)
        main = Path("server/main.py").read_text(encoding="utf-8")
        self.assertNotIn('app.mount("/media"', main)
        self.assertIn("verify_media_signature", main)

    def test_legacy_device_pull_is_scoped_to_enrolled_tenant(self):
        source = Path("server/routers/tasks.py").read_text(encoding="utf-8")
        pull_source = source[source.index("def pull_task("):source.index("def task_progress(")]
        self.assertEqual(2, pull_source.count("AND ENTERPRISE_ID = :enterprise_id"))
        self.assertEqual(2, pull_source.count("AND WORKSPACE_ID = :workspace_id"))
        self.assertEqual(2, pull_source.count('"enterprise_id": device["enterprise_id"]'))
        self.assertEqual(2, pull_source.count('"workspace_id": device["workspace_id"]'))

    def test_migration_declares_usage_reservation_ledger_and_enrollment(self):
        names = {name for name, _ in P55_TABLES}
        self.assertEqual(names, {"SJZQ_DEVICE_ENROLL_TOKEN", "SJZQ_QUOTA_USAGE",
                                 "SJZQ_QUOTA_RESERVATION", "SJZQ_QUOTA_LEDGER"})
        migration = Path("server/migrate.py").read_text(encoding="utf-8")
        self.assertIn("P5_5_001_ENTERPRISE_HARDENING", Path("server/schema_migrations.py").read_text(encoding="utf-8"))
        self.assertIn("p55-backfill", migration)


if __name__ == "__main__":
    unittest.main()
