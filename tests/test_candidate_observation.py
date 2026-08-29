from __future__ import annotations

import json
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.candidate_observation import (
    CandidateObservationError, canonical_payload, cleanup_expired, persist,
)
from server.management_queries import _shape_task_result


def body(**overrides):
    values = dict(
        device_key="device-key", idempotency_key="candidate-job1-attempt1-1",
        task_id=10, task_item_id=11, job_id=12, attempt_id=13,
        worker_id="worker", lease_token="x" * 32, trace_id="trace",
        platform_code="pinduoduo", candidate_present=True, matched=False,
        reason_code="candidate_rejected", candidate_ordinal=1,
        expected_fields={"title": "expected", "password": "never"},
        observed_fields={"title": "observed", "shop": "shop", "cookie": "never"},
        field_differences={"title": "mismatch", "cookie": "never"},
        source_summary=[{"type": "detail_response", "source_identifier": "detail"}],
        collected_at_epoch_ms=1_700_000_000_000, collector_version="collector-1",
        parser_version="parser-1", screenshot_ref=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class Cursor:
    def __init__(self, fetches): self.fetches=list(fetches); self.sql=[]; self.rowcount=1
    def execute(self, sql, params=None): self.sql.append((" ".join(sql.split()), params or {}))
    def fetchone(self): return self.fetches.pop(0)
    def fetchall(self): return self.fetches.pop(0)


class CandidateObservationTest(unittest.TestCase):
    def test_contract_is_bounded_sanitized_and_30_days(self):
        encoded, digest, size = canonical_payload(body())
        payload=json.loads(encoded)
        self.assertEqual(False, payload["matched"])
        self.assertEqual(30, payload["retention_days"])
        self.assertEqual({"title": "expected"}, payload["expected_fields"])
        self.assertNotIn("cookie", payload["observed_fields"])
        self.assertEqual(64, len(digest)); self.assertLess(size, 65536)
        with self.assertRaises(CandidateObservationError):
            canonical_payload(body(reason_code="no_candidate", candidate_present=True))
        with self.assertRaises(CandidateObservationError):
            canonical_payload(body(screenshot_ref="../secret.png"))
        expected_ref = "candidate-observations/" + hashlib.sha256(body().idempotency_key.encode()).hexdigest() + ".jpg"
        self.assertEqual(expected_ref, json.loads(canonical_payload(body(screenshot_ref=expected_ref))[0])["screenshot_ref"])

    def test_persist_is_lease_fenced_raw_only_and_idempotent(self):
        cur=Cursor([None, (0,)])
        job={"task_id":10,"item_id":11}
        reservation=SimpleNamespace(status="pending", reservation_id=91)
        device={"device_id":4,"enterprise_id":2,"workspace_id":3}
        with patch("server.candidate_observation.require_active_lease", return_value=(job,{})), \
             patch("server.candidate_observation.reserve", return_value=reservation), \
             patch("server.candidate_observation.commit") as commit_mock, \
             patch("server.candidate_observation.next_id", return_value=77):
            result=persist(cur, body=body(), device=device)
        self.assertEqual(77, result["raw_id"]); self.assertTrue(result["acknowledged"])
        sql="\n".join(x[0] for x in cur.sql)
        self.assertIn("INSERT INTO SJZQ_RAW_COLLECTION", sql)
        self.assertIn("UPDATE SJZQ_TASK_ITEM", sql)
        self.assertNotIn("PRODUCT_SNAPSHOT", sql); self.assertNotIn("QUALITY_RESULT", sql)
        commit_mock.assert_called_once_with(cur, 91)

        payload, sha, _=canonical_payload(body())
        replay=Cursor([(77, sha, 4, 2, 3)])
        result=persist(replay, body=body(), device=device)
        self.assertTrue(result["idempotent"]); self.assertEqual(1, len(replay.sql))

    def test_cleanup_only_candidate_raw_and_preserves_item_summary(self):
        cur=Cursor([[(77,2,3,"key",512,"candidate-observations/a.png")]])
        with patch("server.candidate_observation.adjust_used") as adjust:
            refs=cleanup_expired(cur, limit=10)
        self.assertEqual(["candidate-observations/a.png"], refs)
        sql="\n".join(x[0] for x in cur.sql)
        self.assertIn("SOURCE_TYPE=:source_type", sql)
        self.assertIn("ROWNUM<=:limit", sql)
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertIn("COLLECTED_AT < SYSTIMESTAMP", sql)
        self.assertIn("DELETE FROM SJZQ_RAW_COLLECTION", sql)
        self.assertNotIn("DELETE FROM SJZQ_TASK_ITEM", sql)
        adjust.assert_called_once()

    def test_task_result_marks_candidate_raw_unavailable_for_library(self):
        row = _shape_task_result({"result_kind":"candidate_observation", "task_id":10,
            "raw_id":77, "library_status":"unavailable", "failure_reason":"no_candidate"})
        self.assertEqual(77, row["result_id"])
        self.assertFalse(row["library"]["can_save"])
        self.assertEqual("candidate_observation_never_enters_library", row["library"]["reason"])
        self.assertEqual("available", row["resources"]["raw"]["availability"])

if __name__ == "__main__": unittest.main()
