"""Phase 5 tenant model, query-boundary and UI-context contracts."""

from __future__ import annotations

from pathlib import Path
import unittest

from server import management_queries
from server.schema_migrations import (
    P5_INDEXES, P5_MIGRATION_ID, P5_TABLES, P5_TENANT_COLUMNS,
)
from server.tenant import TenantContext

ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, owned: bool):
        self.owned = owned
        self.sql: list[str] = []
        self.params: list[dict] = []
        self._rows = []

    def execute(self, sql, params=None):
        self.sql.append(" ".join(str(sql).split()).upper())
        self.params.append(dict(params or {}))
        if self.sql[-1].startswith("SELECT 1 FROM"):
            self._rows = [(1,)] if self.owned else []
        else:
            self._rows = []

    def fetchone(self): return self._rows.pop(0) if self._rows else None
    def fetchall(self): rows, self._rows = self._rows, []; return rows


CTX_A = TenantContext(11, 101, 1, 1, "viewer", frozenset({"data:view", "task:view"}))


class Phase5TenantContractTest(unittest.TestCase):
    def test_enterprise_workspace_membership_quota_and_private_product_exist(self):
        ddl = "\n".join(sql for _, sql in P5_TABLES).upper()
        for table in ("SJZQ_ENTERPRISE", "SJZQ_WORKSPACE", "SJZQ_ENTERPRISE_MEMBERSHIP",
                      "SJZQ_WORKSPACE_MEMBERSHIP", "SJZQ_ENTERPRISE_QUOTA", "SJZQ_ENTERPRISE_PRODUCT"):
            self.assertIn(f"CREATE TABLE {table}", ddl)
        self.assertIn("UNIQUE (ENTERPRISE_ID,IDENTITY_ID)", ddl)
        self.assertIn("UNIQUE (ENTERPRISE_ID,WORKSPACE_ID)", ddl)

    def test_core_private_facts_have_explicit_tenant_columns(self):
        columns = {table: definition.upper() for table, definition in P5_TENANT_COLUMNS}
        for table in ("SJZQ_TASK", "SJZQ_COLLECTION_JOB", "SJZQ_COLLECTION_ATTEMPT",
                      "SJZQ_JOB_EVENT", "SJZQ_PRODUCT", "SJZQ_PRODUCT_SNAPSHOT",
                      "SJZQ_DATA_QUARANTINE", "SJZQ_QUALITY_RESULT", "SJZQ_OP_LOG"):
            self.assertIn("ENTERPRISE_ID", columns[table])
            self.assertIn("WORKSPACE_ID", columns[table])

    def test_cross_tenant_ids_are_indistinguishable_from_missing(self):
        for call, empty in (
            (lambda c: management_queries.task_trace(c, 9002, tenant=CTX_A), None),
            (lambda c: management_queries.quarantine_detail(c, 9002, tenant=CTX_A), None),
            (lambda c: management_queries.task_jobs(c, 9002, 1, 20, tenant=CTX_A),
             {"items": [], "total": 0, "page": 1, "limit": 20}),
            (lambda c: management_queries.job_attempts(c, 9002, 1, 20, tenant=CTX_A),
             {"items": [], "total": 0, "page": 1, "limit": 20}),
            (lambda c: management_queries.attempt_events(c, 9002, 1, 20, tenant=CTX_A),
             {"items": [], "total": 0, "page": 1, "limit": 20}),
        ):
            cursor = Cursor(owned=False)
            self.assertEqual(call(cursor), empty)
            self.assertEqual(cursor.params[0]["enterprise_id"], 11)
            self.assertEqual(cursor.params[0]["workspace_id"], 101)

    def test_search_pagination_metrics_and_dashboard_include_tenant_predicates(self):
        management = (ROOT / "server/management_queries.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "server/routers/dashboard.py").read_text(encoding="utf-8")
        products = (ROOT / "server/routers/products.py").read_text(encoding="utf-8")
        tasks = (ROOT / "server/routers/tasks.py").read_text(encoding="utf-8")
        for source in (management, dashboard, products, tasks):
            self.assertIn("ENTERPRISE_ID", source)
            self.assertIn("WORKSPACE_ID", source)
        self.assertIn("q.ENTERPRISE_ID=:enterprise_id", management)
        self.assertIn("OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY", management)

    def test_snapshot_predecessor_and_diff_are_workspace_private(self):
        source = (ROOT / "server/product_observation.py").read_text(encoding="utf-8")
        self.assertIn("ENTERPRISE_PRODUCT_ID=:enterprise_product_id", source)
        self.assertIn("ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id", source)
        self.assertIn("enterprise_product_id", source)

    def test_migration_is_versioned_restartable_and_indexed(self):
        migrate = (ROOT / "server/migrate.py").read_text(encoding="utf-8")
        self.assertEqual(P5_MIGRATION_ID, "P5_001_ENTERPRISE_TENANCY")
        self.assertIn("_ensure_phase5_enterprise_tenancy", migrate)
        self.assertIn("migration checksum mismatch", migrate)
        self.assertIn("WHERE ENTERPRISE_ID IS NULL", migrate)
        names = {name for name, _ in P5_INDEXES}
        self.assertIn("IDX_SJZQ_TASK_TENANT_PAGE", names)
        self.assertIn("IDX_SJZQ_SNAPSHOT_TENANT", names)

    def test_web_sends_and_selects_enterprise_workspace_context(self):
        http = (ROOT / "web/src/api/http.js").read_text(encoding="utf-8")
        client_context = (ROOT / "web/src/api/clientContext.js").read_text(encoding="utf-8")
        layout = (ROOT / "web/src/layout/AdminLayout.vue").read_text(encoding="utf-8")
        self.assertIn("headersForContext(requestContext.snapshot)", http)
        self.assertIn("X-Enterprise-Id", client_context)
        self.assertIn("X-Workspace-Id", client_context)
        self.assertIn("tenant-select", layout)
        self.assertIn("enterprise_name", layout)
        self.assertIn("workspace_name", layout)


if __name__ == "__main__":
    unittest.main()
