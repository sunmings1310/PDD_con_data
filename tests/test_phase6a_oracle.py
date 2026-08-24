"""Phase 6A PDD Collector compatibility against the disposable Oracle schema.

The fixture deliberately reuses the Phase 3 Product/Snapshot helper.  Phase 6A
is a structural migration, so these assertions prove that requests which now
pass through the server Collector Registry/PddCollector retain the established
Oracle persistence semantics.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from tests.test_phase3_oracle import Phase3OracleTest as _Phase3OracleFixture
from server.collectors import PlatformIdentity, collector_registry
from server.routers import products


CONFIGURED = (
    os.getenv("T003_ORACLE_TEST_ENABLED") == "1"
    and os.getenv("PHASE6A_ORACLE_TEST_ENABLED") == "1"
    and all(
        os.getenv(name)
        for name in ("T003_ORACLE_DSN", "T003_ORACLE_USER", "T003_ORACLE_PASSWORD")
    )
)


@unittest.skipUnless(
    CONFIGURED,
    "BLOCKED_BY_ENVIRONMENT: Phase 6A isolated Oracle test schema not configured",
)
class Phase6AOracleCollectorCompatibilityTest(_Phase3OracleFixture):
    # The inherited class supplies only the proven Oracle setup/body/cleanup
    # helpers.  Phase 3's own cases remain owned by test_phase3_oracle.py.
    test_identity_snapshots_provenance_diff_and_replay = None
    test_quality_rejection_is_idempotently_quarantined_without_snapshot = None

    def test_pdd_registry_adapter_preserves_accepted_observation_semantics(self):
        collector = collector_registry.require("pinduoduo")
        identity = PlatformIdentity("pinduoduo", self.platform_item)
        self.assertTrue(collector.validate_identity(identity))

        first_key = "p6a-first-" + self.tag
        second_key = "p6a-second-" + self.tag
        first_body = self._body(first_key)
        second_body = self._body(
            second_key,
            price=10.5,
            parser="pdd-android-2",
            task_item=False,
        )

        original_identity = collector.validate_identity
        with (
            patch.object(collector, "validate_identity", wraps=original_identity) as identity_check,
            patch.object(products, "get_conn", self._connection),
        ):
            first = products.upload_product(first_body)
            replay = products.upload_product(first_body)
            second = products.upload_product(second_body)

        self.assertGreaterEqual(identity_check.call_count, 3)
        self.assertTrue(first.ok and replay.ok and second.ok)
        self.assertTrue(replay.data["idempotent"])
        self.assertEqual(first.data["snapshot_id"], replay.data["snapshot_id"])
        self.assertEqual(first.data["master_product_id"], second.data["master_product_id"])
        self.assertNotEqual(first.data["snapshot_id"], second.data["snapshot_id"])
        self.assertEqual(["price"], second.data["changed_fields"])

        self.cur.execute(
            """SELECT PLATFORM_CODE,PLATFORM_PRODUCT_ID
                 FROM SJZQ_PRODUCT_MASTER WHERE MASTER_PRODUCT_ID=:id""",
            {"id": first.data["master_product_id"]},
        )
        self.assertEqual(("pinduoduo", self.platform_item), tuple(self.cur.fetchone()))

        self.cur.execute(
            """SELECT SNAPSHOT_ID,DISPLAY_PRICE,PARSER_VERSION,QUALITY_STATUS
                 FROM SJZQ_PRODUCT_SNAPSHOT
                WHERE MASTER_PRODUCT_ID=:id ORDER BY SNAPSHOT_ID""",
            {"id": first.data["master_product_id"]},
        )
        snapshots = self.cur.fetchall()
        self.assertEqual(2, len(snapshots))
        self.assertEqual([12.3, 10.5], [float(row[1]) for row in snapshots])
        self.assertEqual(["pdd-android-1", "pdd-android-2"], [row[2] for row in snapshots])
        self.assertEqual(["passed", "passed"], [row[3] for row in snapshots])

        self.cur.execute(
            """SELECT ACCEPTED,STATUS,QUALITY_STATUS
                 FROM SJZQ_QUALITY_RESULT WHERE SNAPSHOT_ID=:snapshot""",
            {"snapshot": first.data["snapshot_id"]},
        )
        self.assertEqual((1, "passed", "passed"), tuple(self.cur.fetchone()))
        self.cur.execute(
            """SELECT PRICE_CHANGED,SALES_CHANGED
                 FROM SJZQ_SNAPSHOT_DIFF WHERE SNAPSHOT_ID=:snapshot""",
            {"snapshot": second.data["snapshot_id"]},
        )
        self.assertEqual((1, 0), tuple(int(value) for value in self.cur.fetchone()))

    def test_pdd_registry_adapter_preserves_rejected_quarantine_semantics(self):
        collector = collector_registry.require("pinduoduo")
        key = "p6a-quarantine-" + self.tag
        body = self._body(
            key,
            price=None,
            sources={"item_id": "embedded_json", "name": "detail_text"},
        )

        original_identity = collector.validate_identity
        with (
            patch.object(collector, "validate_identity", wraps=original_identity) as identity_check,
            patch.object(products, "get_conn", self._connection),
        ):
            rejected = products.upload_product(body)
            replay = products.upload_product(body)

        self.assertGreaterEqual(identity_check.call_count, 1)
        self.assertFalse(rejected.ok or replay.ok)
        self.assertTrue(rejected.data["quarantined"] and rejected.data["persisted"])
        self.assertEqual(rejected.data["quarantine_id"], replay.data["quarantine_id"])
        self.assertTrue(replay.data["idempotent"])

        self.cur.execute(
            "SELECT COUNT(*) FROM SJZQ_PRODUCT_SNAPSHOT WHERE TASK_ID=:task",
            {"task": self.task_id},
        )
        self.assertEqual(0, int(self.cur.fetchone()[0]))
        self.cur.execute(
            """SELECT q.ACCEPTED,q.STATUS,q.QUALITY_STATUS,q.ERROR_CODES_JSON,
                      d.QUARANTINE_ID,d.STATUS
                 FROM SJZQ_QUALITY_RESULT q
                 JOIN SJZQ_DATA_QUARANTINE d ON d.QUALITY_RESULT_ID=q.QUALITY_RESULT_ID
                WHERE d.QUARANTINE_ID=:id""",
            {"id": rejected.data["quarantine_id"]},
        )
        accepted, quality_status, source_quality, errors, quarantine_id, quarantine_status = self.cur.fetchone()
        error_text = errors.read() if hasattr(errors, "read") else errors
        self.assertEqual(0, int(accepted))
        self.assertEqual("quarantined", quality_status)
        self.assertEqual("quarantined", source_quality)
        self.assertIn("FIELD_SOURCE_MISSING:price", json.loads(error_text))
        self.assertEqual(rejected.data["quarantine_id"], int(quarantine_id))
        self.assertEqual("open", quarantine_status)


del _Phase3OracleFixture


if __name__ == "__main__":
    unittest.main()
