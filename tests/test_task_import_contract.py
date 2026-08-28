from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TaskImportContractTests(unittest.TestCase):
    def test_canonical_service_has_tenant_serialized_durable_replay(self):
        source = (ROOT / 'server/task_creation_service.py').read_text(encoding='utf-8')
        self.assertIn('lock_metric_scope(cur, enterprise_id=tenant.enterprise_id, metric=ACTIVE_TASK)', source)
        self.assertIn("JSON_VALUE(CONFIG_JSON, '$._submission.id'", source)
        self.assertIn("'payload_sha256': payload_sha256", source)
        self.assertIn("'idempotent': True", source)
        self.assertIn("'IDEMPOTENCY_CONFLICT'", source)
        self.assertIn('if body.task_type == TASK_COLLECT: create_jobs_for_task', source)

    def test_excel_compatibility_delegates_without_second_task_sql(self):
        source = (ROOT / 'server/routers/excel_match.py').read_text(encoding='utf-8')
        adapter = source[source.index('def unmatched_to_task'):]
        self.assertIn('create_canonical_task(', adapter)
        self.assertNotIn('INSERT INTO SJZQ_TASK', adapter)
        self.assertNotIn('INSERT INTO SJZQ_TASK_ITEM', adapter)

    def test_web_embedded_flow_uses_one_payload_builder_not_excel_dispatch(self):
        task_create = (ROOT / 'web/src/views/tasks/TaskCreate.vue').read_text(encoding='utf-8')
        excel = (ROOT / 'web/src/views/excel/ExcelMatch.vue').read_text(encoding='utf-8')
        self.assertIn("buildCanonicalPayload", task_create)
        self.assertIn("@draft-rows=\"setExcelRows\"", task_create)
        self.assertIn("v-if=\"!embedded\" type=\"warning\"", excel)
        self.assertIn("emit('draft-rows'", excel)
        self.assertNotIn("unmatched-to-task", task_create)


if __name__ == '__main__':
    unittest.main()
