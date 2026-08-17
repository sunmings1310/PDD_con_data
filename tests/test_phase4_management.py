from __future__ import annotations

import unittest
import os

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server import management_queries as q


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.description = []
        self.rows = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), dict(params or {})))
        if not self.responses:
            raise AssertionError(f"unexpected SQL: {sql}")
        columns, rows = self.responses.pop(0)
        self.description = [(name,) for name in columns]
        self.rows = list(rows)

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class Phase4ManagementTests(unittest.TestCase):
    def test_quarantine_filters_are_database_paged_and_exact(self):
        cols = ["QUARANTINE_ID", "STATUS", "FAILURE_REASON", "ERROR_CODES_JSON", "COLLECTED_AT"]
        cur = Cursor([(["COUNT"], [(3,)]), (cols, [(8, "open", "bad", '["SKU_INVALID_PRICE"]', "t")])])
        result = q.list_quarantines(cur, page=2, limit=1, filters={
            "error_code": "SKU_INVALID_PRICE", "platform": "pinduoduo", "task_id": 9,
            "start_at": "a", "end_at": "b",
        })
        self.assertEqual((result["total"], result["page"], result["limit"]), (3, 2, 1))
        self.assertEqual(result["items"][0]["error_codes"], ["SKU_INVALID_PRICE"])
        count_sql, count_params = cur.calls[0]
        page_sql, page_params = cur.calls[1]
        self.assertIn("DBMS_LOB.INSTR", count_sql)
        self.assertEqual(count_params["error_code"], '"SKU_INVALID_PRICE"')
        self.assertIn("JSON_VALUE(q.EVIDENCE_JSON", count_sql)
        self.assertIn("q.MASTER_PRODUCT_ID IS NULL", count_sql)
        self.assertIn("COALESCE(q.MASTER_PRODUCT_ID,m.MASTER_PRODUCT_ID) MASTER_PRODUCT_ID", page_sql)
        self.assertIn("ORDER BY q.COLLECTED_AT DESC,q.QUARANTINE_ID DESC", page_sql)
        self.assertIn("OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY", page_sql)
        self.assertEqual((page_params["offset"], page_params["limit"]), (1, 1))

    def test_quarantine_detail_uses_raw_field_sources_and_quality_result(self):
        cols = ["QUARANTINE_ID", "QUALITY_RESULT_ID", "RAW_JSON", "EVIDENCE_JSON", "ERROR_CODES_JSON",
                "ACCEPTED", "QUALITY_RESULT_STATUS", "PAGE_STATUS", "PARSE_STATUS", "QUALITY_STATUS",
                "MISSING_FIELDS_JSON", "QUALITY_ERROR_CODES_JSON", "WARNINGS_JSON",
                "QUALITY_PARSER_VERSION", "QUALITY_RULES_VERSION_ACTUAL", "PLATFORM_CODE", "PLATFORM_PRODUCT_ID",
                "LINKED_MASTER_PRODUCT_ID"]
        row = (1, 2, '{"field_sources":{"price":"network"}}',
               '{"platform_code":"pinduoduo","platform_product_id":"42"}', '["MISSING_PRICE"]',
               0, "quarantined", "product", "failed", "quarantined", '["price"]', '["MISSING_PRICE"]',
               "[]", "parser-x", "rules-x", None, None, 99)
        detail = q.quarantine_detail(Cursor([(cols, [row])]), 1)
        self.assertEqual(detail["field_sources"], {"price": "network"})
        self.assertEqual(detail["platform_product_id"], "42")
        self.assertEqual(detail["master_product_id"], 99)
        self.assertFalse(detail["quality_gate"]["accepted"])
        self.assertEqual(detail["quality_gate"]["missing_fields"], ["price"])

    def test_snapshot_page_batches_provenance_and_includes_diff(self):
        snap_cols = ["SNAPSHOT_ID", "MASTER_PRODUCT_ID", "SKU_JSON", "DIFF_ID", "CHANGED_FIELDS_JSON",
                     "PRICE_CHANGED", "SALES_CHANGED", "SKU_CHANGED", "AVAILABILITY_CHANGED",
                     "TITLE_CHANGED", "SHOP_CHANGED"]
        snaps = [(12, 7, '[{"name":"red"}]', 20, '{"price":{"before":1,"after":2}}', 1, 0, 0, 0, 0, 0),
                 (11, 7, None, 19, '{}', 0, 0, 0, 0, 0, 0)]
        prov_cols = ["SNAPSHOT_ID", "FIELD_NAME", "SOURCE_TYPE", "SOURCE_REF", "TRANSFORMATION"]
        product_cols = ["MASTER_PRODUCT_ID", "PLATFORM_CODE", "PLATFORM_PRODUCT_ID", "STATUS", "FIRST_SEEN_AT", "LAST_SEEN_AT"]
        cur = Cursor([(product_cols, [(7, "pinduoduo", "42", "active", "a", "b")]),
                      (["COUNT"], [(2,)]), (snap_cols, snaps), (prov_cols, [(12, "price", "network", "raw:1", None)])])
        result = q.list_snapshots(cur, 7, page=1, limit=20)
        self.assertEqual(len(cur.calls), 4)
        self.assertEqual(result["product"]["platform_product_id"], "42")
        self.assertIn("SNAPSHOT_ID IN (:sid0,:sid1)", cur.calls[3][0])
        self.assertTrue(result["items"][0]["difference"]["price_changed"])
        self.assertEqual(result["items"][0]["provenance"][0]["field_name"], "price")
        self.assertEqual(result["items"][1]["provenance"], [])

    def test_metrics_use_real_aggregates_and_emit_anomalies(self):
        overall_cols = ["TOTAL_COUNT", "ACCEPTED_COUNT", "QUARANTINE_COUNT", "PARSER_FAILURE_COUNT",
                        "PARSE_STATUS_FAILED_COUNT", "IDENTITY_MISSING_COUNT", "TITLE_MISSING_COUNT",
                        "PRICE_MISSING_COUNT", "SKU_ABNORMAL_COUNT"]
        group_cols = ["VERSION", "TOTAL_COUNT", "ACCEPTED_COUNT", "QUARANTINE_COUNT", "PARSER_FAILURE_COUNT"]
        rule_cols = ["VERSION", "TOTAL_COUNT", "ACCEPTED_COUNT", "QUARANTINE_COUNT"]
        error_cols = ["ERROR_CODE", "ERROR_COUNT"]
        cur = Cursor([(overall_cols, [(10, 6, 4, 2, 4, 1, 2, 3, 1)]),
                      (group_cols, [("bad-parser", 5, 1, 4, 2), ("good-parser", 5, 5, 0, 0)]),
                      (rule_cols, [("phase3-1", 10, 6, 4)]), (error_cols, [("PARSE_FAILED", 4)])])
        result = q.quality_metrics(cur)
        self.assertEqual(result["total_collections"], 10)
        self.assertEqual(result["pass_count"], 6)
        self.assertEqual(result["overall"]["quality_pass_rate"], .6)
        self.assertEqual(result["overall"]["parser_failure_rate"], .2)
        kinds = {x["type"] for x in result["anomalies"]}
        self.assertIn("quarantine_rate_high", kinds)
        self.assertIn("parser_version_degraded", kinds)
        self.assertIn("error_code_concentrated", kinds)
        self.assertEqual(result["key_field_missing_rates"][1]["rate"], .2)
        self.assertEqual(result["top_error_codes"][0]["error_code"], "PARSE_FAILED")
        self.assertEqual(result["by_parser_version"][0]["pass_count"], 1)
        self.assertIn('"PARSE_FAILED"', cur.calls[0][0])
        self.assertIn('"platform_code"', cur.calls[0][0])
        self.assertIn('"platform_product_id"', cur.calls[0][0])

    def test_trace_pages_never_select_lease_token_hash(self):
        business_cols = ["JOB_ID", "ATTEMPT_ID", "RESULT_KIND", "SNAPSHOT_ID", "MASTER_PRODUCT_ID",
                         "QUARANTINE_ID", "QUALITY_STATUS", "COLLECTED_AT"]
        cur = Cursor([(["COUNT"], [(1,)]), (["ATTEMPT_ID", "TRACE_ID"], [(4, "trace-4")]),
                      (business_cols, [(3, 4, "snapshot", 12, 7, None, "passed", "t"),
                                       (3, 4, "quarantine", None, 7, 19, "quarantined", "u")])])
        result = q.job_attempts(cur, 3, 1, 50)
        self.assertEqual(result["items"][0]["trace_id"], "trace-4")
        self.assertEqual([x["result_kind"] for x in result["items"][0]["business_results"]],
                         ["snapshot", "quarantine"])
        self.assertNotIn("LEASE_TOKEN_HASH", cur.calls[1][0])
        self.assertIn("ATTEMPT_NO DESC,ATTEMPT_ID DESC", cur.calls[1][0])
        self.assertIn("UNION ALL", cur.calls[2][0])

    def test_task_jobs_batch_business_results_without_changing_page_total(self):
        job_cols = ["JOB_ID", "STATUS"]
        business_cols = ["JOB_ID", "ATTEMPT_ID", "RESULT_KIND", "SNAPSHOT_ID", "MASTER_PRODUCT_ID",
                         "QUARANTINE_ID", "QUALITY_STATUS", "COLLECTED_AT"]
        cur = Cursor([(["COUNT"], [(2,)]), (job_cols, [(8, "success"), (7, "quarantined")]),
                      (business_cols, [(8, 81, "snapshot", 100, 10, None, "passed", "t"),
                                       (7, 71, "quarantine", None, 11, 101, "quarantined", "t")])])
        result = q.task_jobs(cur, 5, 1, 20)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["business_results"][0]["snapshot_id"], 100)
        self.assertEqual(result["items"][1]["business_results"][0]["quarantine_id"], 101)
        self.assertEqual(cur.calls[2][1], {"bid0": 8, "bid1": 7})

    def test_task_events_are_complete_and_stably_ordered(self):
        cur = Cursor([(["COUNT"], [(1,)]), (["EVENT_ID", "DETAIL_JSON"], [(1, '{"paused_jobs":2}')])])
        result = q.task_events(cur, 9, 1, 50)
        self.assertEqual(result["items"][0]["detail"], {"paused_jobs": 2})
        self.assertIn("CREATE_TIME ASC,EVENT_ID ASC", cur.calls[1][0])
        self.assertNotIn("LEASE_TOKEN_HASH", cur.calls[1][0])


if __name__ == "__main__":
    unittest.main()
