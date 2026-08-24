from __future__ import annotations

import inspect
import unittest

from server.job_reconciliation import OracleReconciliationStore
from server.job_service import fail


class OracleReconciliationCompatibilityTest(unittest.TestCase):
    def test_expired_scan_aliases_duplicate_status_columns(self):
        source = inspect.getsource(OracleReconciliationStore.expired_leases)
        self.assertIn("j.STATUS AS JOB_STATUS", source)
        self.assertIn("a.STATUS AS ATTEMPT_STATUS", source)

    def test_retry_promotion_preserves_not_null_next_run_at(self):
        source = inspect.getsource(OracleReconciliationStore.promote_due_retry)
        self.assertIn("NEXT_RUN_AT=SYSTIMESTAMP", source)
        self.assertNotIn("NEXT_RUN_AT=NULL", source)

    def test_terminal_reconciliation_preserves_not_null_next_run_at(self):
        for method in (
            OracleReconciliationStore.mark_confirmed_result_success,
            OracleReconciliationStore.mark_job_dead,
        ):
            source = inspect.getsource(method)
            self.assertIn("NEXT_RUN_AT=SYSTIMESTAMP", source)
            self.assertNotIn("NEXT_RUN_AT=NULL", source)

    def test_non_retryable_failure_preserves_not_null_next_run_at(self):
        source = inspect.getsource(fail)
        self.assertIn("ELSE SYSTIMESTAMP END", source)
        self.assertNotIn("ELSE NULL END", source)


if __name__ == "__main__":
    unittest.main()
