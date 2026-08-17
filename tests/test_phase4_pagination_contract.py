from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase4PaginationContractTest(unittest.TestCase):
    def test_management_growth_paths_have_versioned_indexes(self) -> None:
        from server.schema_migrations import P4_INDEXES, P4_MIGRATION_ID

        ddl = "\n".join(statement for _, statement in P4_INDEXES)
        self.assertEqual("P4_001_MANAGEMENT_INDEXES", P4_MIGRATION_ID)
        self.assertIn("SJZQ_JOB_EVENT(ATTEMPT_ID, CREATE_TIME, EVENT_ID)", ddl)
        self.assertIn("SJZQ_DATA_QUARANTINE(TASK_ID, COLLECTED_AT, QUARANTINE_ID)", ddl)
        self.assertIn("SJZQ_PRODUCT_SNAPSHOT(MASTER_PRODUCT_ID, COLLECTED_AT, SNAPSHOT_ID)", ddl)
        migrate = (ROOT / "server" / "migrate.py").read_text(encoding="utf-8")
        self.assertIn("_ensure_phase4_management_indexes(conn, cur)", migrate)

    def test_product_list_uses_database_count_and_stable_page(self) -> None:
        source = (ROOT / "server" / "routers" / "products.py").read_text(encoding="utf-8")
        block = source[source.index("def list_products("):source.index("def _attach_product_images")]
        self.assertIn("SELECT COUNT(*) FROM SJZQ_PRODUCT", block)
        self.assertIn("OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY", block)
        self.assertIn("ORDER BY COLLECT_TIME DESC NULLS LAST, PRODUCT_ID DESC", block)
        self.assertNotIn("rows[offset : offset + limit]", block)
        self.assertIn('"page": page', block)

    def test_task_list_uses_database_count_and_stable_page(self) -> None:
        source = (ROOT / "server" / "routers" / "tasks.py").read_text(encoding="utf-8")
        block = source[source.index("def list_tasks("):source.index('@router.get("/{task_id}")')]
        self.assertIn("SELECT COUNT(*) FROM SJZQ_TASK", block)
        self.assertIn("OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY", block)
        self.assertIn("ORDER BY CREATE_TIME DESC, TASK_ID DESC", block)
        self.assertIn('"page": page', block)

    def test_web_consumes_paged_task_shape(self) -> None:
        source = (ROOT / "web" / "src" / "views" / "tasks" / "TaskList.vue").read_text(encoding="utf-8")
        self.assertIn("res.data?.items", source)
        self.assertIn("res.data?.total", source)
        self.assertIn("v-model:current-page", source)
        self.assertIn("v-if=\"error\"", source)


if __name__ == "__main__":
    unittest.main()
