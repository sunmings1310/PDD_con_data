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
        self.assertIn("'DUPLICATE_TARGET'", source)
        self.assertIn("SELECT ENABLED FROM SJZQ_PLATFORM", source)
        self.assertIn("ACCEPTED_COLLECTOR_PLATFORMS", source)
        self.assertIn("T_GOODS_LIBRARY", source)
        self.assertIn('if body.task_type == TASK_COLLECT: create_jobs_for_task', source)

    def test_excel_compatibility_delegates_without_second_task_sql(self):
        source = (ROOT / 'server/routers/excel_match.py').read_text(encoding='utf-8')
        adapter = source[source.index('def unmatched_to_task'):]
        self.assertIn('create_canonical_task(', adapter)
        self.assertNotIn('INSERT INTO SJZQ_TASK', adapter)
        self.assertNotIn('INSERT INTO SJZQ_TASK_ITEM', adapter)
        self.assertIn('require_tenant_perms("task:create")', adapter)
        self.assertIn('require_tenant_perms("task:dispatch")', adapter)

    def test_web_embedded_flow_uses_one_payload_builder_not_excel_dispatch(self):
        task_create = (ROOT / 'web/src/views/tasks/TaskCreate.vue').read_text(encoding='utf-8')
        excel = (ROOT / 'web/src/views/excel/ExcelMatch.vue').read_text(encoding='utf-8')
        self.assertIn("buildCanonicalPayload", task_create)
        self.assertIn("@draft-rows=\"setExcelRows\"", task_create)
        self.assertIn("v-if=\"!embedded\" type=\"warning\"", excel)
        self.assertIn("emit('draft-rows'", excel)
        self.assertNotIn("unmatched-to-task", task_create)

    def test_web_draft_refuses_unresolved_rows_and_freezes_ack_retry_payload(self):
        draft = (ROOT / 'web/src/utils/taskDraft.js').read_text(encoding='utf-8')
        task_create = (ROOT / 'web/src/views/tasks/TaskCreate.vue').read_text(encoding='utf-8')
        self.assertIn("if (row.error_codes.includes('DUPLICATE_DRAFT_INPUT')) return row", draft)
        self.assertIn("selection_status: multiple ? 'choice_required' : 'selected'", draft)
        self.assertIn("export function canSubmitDraft", draft)
        self.assertIn("const frozenPayload = ref(null)", task_create)
        self.assertIn("const payload = frozenPayload.value || nextPayload()", task_create)
        self.assertIn(':platform-code="form.platform_code"', task_create)

    def test_quota_scope_and_regular_reserve_share_usage_then_quota_order(self):
        quota = (ROOT / 'server/quota.py').read_text(encoding='utf-8')
        scope = quota[quota.index('def lock_metric_scope'):quota.index('def _ledger')]
        reserve = quota[quota.index('def reserve('):quota.index('def commit(')]
        self.assertLess(scope.index('_usage_row'), scope.index('_limit'))
        self.assertLess(reserve.index('_usage_row'), reserve.index('_limit'))


if __name__ == '__main__':
    unittest.main()
