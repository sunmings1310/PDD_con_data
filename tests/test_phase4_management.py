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
from server.tenant import TenantContext


TENANT_A = TenantContext(11, 101, 1, 1, "viewer", frozenset({"task:view"}))


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
                         "ENTERPRISE_PRODUCT_ID", "PRODUCT_ID", "QUARANTINE_ID", "RAW_ID",
                         "QUALITY_RESULT_ID", "LIBRARY_STATUS", "QUALITY_STATUS", "COLLECTED_AT"]
        cur = Cursor([(["COUNT"], [(1,)]), (["ATTEMPT_ID", "TRACE_ID"], [(4, "trace-4")]),
                      (business_cols, [(3, 4, "snapshot", 12, 7, 70, 17, None, 21, 31, "draft", "passed", "t"),
                                       (3, 4, "quarantine", None, 7, 70, None, 19, 22, 32, "unavailable", "quarantined", "u")])])
        result = q.job_attempts(cur, 3, 1, 50)
        self.assertEqual(result["items"][0]["trace_id"], "trace-4")
        self.assertEqual([x["result_kind"] for x in result["items"][0]["business_results"]],
                         ["snapshot", "quarantine"])
        self.assertEqual(21, result["items"][0]["business_results"][0]["raw_id"])
        self.assertEqual(31, result["items"][0]["business_results"][0]["quality_result_id"])
        self.assertNotIn("LEASE_TOKEN_HASH", cur.calls[1][0])
        self.assertIn("ATTEMPT_NO DESC,ATTEMPT_ID DESC", cur.calls[1][0])
        self.assertIn("UNION ALL", cur.calls[2][0])

    def test_task_jobs_batch_business_results_without_changing_page_total(self):
        job_cols = ["JOB_ID", "STATUS"]
        business_cols = ["JOB_ID", "ATTEMPT_ID", "RESULT_KIND", "SNAPSHOT_ID", "MASTER_PRODUCT_ID",
                         "ENTERPRISE_PRODUCT_ID", "PRODUCT_ID", "QUARANTINE_ID", "RAW_ID",
                         "QUALITY_RESULT_ID", "LIBRARY_STATUS", "QUALITY_STATUS", "COLLECTED_AT"]
        cur = Cursor([(["COUNT"], [(2,)]), (job_cols, [(8, "success"), (7, "quarantined")]),
                      (business_cols, [(8, 81, "snapshot", 100, 10, 110, 1000, None, 200, 300, "saved", "passed", "t"),
                                       (7, 71, "quarantine", None, 11, 111, None, 101, 201, 301, "unavailable", "quarantined", "t")])])
        result = q.task_jobs(cur, 5, 1, 20)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["business_results"][0]["snapshot_id"], 100)
        self.assertEqual(result["items"][1]["business_results"][0]["quarantine_id"], 101)
        self.assertEqual("available", result["items"][0]["business_results"][0]["resources"]["snapshot"]["availability"])
        self.assertEqual("saved", result["items"][0]["business_results"][0]["library"]["status"])
        self.assertEqual(cur.calls[2][1], {"bid0": 8, "bid1": 7})

    def test_task_results_include_snapshot_draft_quarantine_and_explicit_unavailable_resources(self):
        columns = [
            "RESULT_KIND", "TASK_ID", "JOB_ID", "ATTEMPT_ID", "SNAPSHOT_ID",
            "MASTER_PRODUCT_ID", "ENTERPRISE_PRODUCT_ID", "PRODUCT_ID", "QUARANTINE_ID",
            "RAW_ID", "QUALITY_RESULT_ID", "LIBRARY_STATUS", "QUALITY_STATUS",
            "PLATFORM_TITLE", "CANONICAL_NAME", "PRODUCT_ATTRIBUTE_SPEC", "FAILURE_REASON",
            "COLLECTED_AT",
        ]
        rows = [
            ("snapshot", 5, 8, 81, 100, 10, 110, 1000, None, 200, 300, "draft",
             "passed", "完整标题", "规范名", "10ml", None, "t3"),
            ("quarantine", 5, 7, 71, None, 11, 111, None, 101, 201, 301, "unavailable",
             "quarantined", None, None, None, "MISSING_PRICE", "t2"),
            ("legacy_product", 5, None, None, None, None, None, 1001, None, None, None, "saved",
             "legacy", "旧标题", "旧规范名", "20ml", None, "t1"),
        ]
        cur = Cursor([
            (["OWNED"], [(1,)]),
            (["COUNT"], [(3,)]),
            (columns, rows),
        ])

        result = q.task_results(cur, 5, page=1, limit=20, tenant=TENANT_A)

        self.assertEqual((3, 1, 20), (result["total"], result["page"], result["limit"]))
        snapshot, quarantine, legacy = result["items"]
        self.assertEqual(100, snapshot["snapshot_id"])
        self.assertEqual(200, snapshot["raw_id"])
        self.assertEqual(300, snapshot["quality_result_id"])
        self.assertEqual("draft", snapshot["library"]["status"])
        self.assertTrue(snapshot["library"]["can_save"])
        self.assertEqual("available", snapshot["resources"]["snapshot"]["availability"])
        self.assertEqual("unavailable", snapshot["resources"]["quarantine"]["availability"])
        self.assertEqual("not_applicable_for_accepted_snapshot", snapshot["resources"]["quarantine"]["reason"])
        self.assertEqual("unavailable", quarantine["library"]["status"])
        self.assertEqual("available", quarantine["resources"]["raw"]["availability"])
        self.assertEqual("available", quarantine["resources"]["quality"]["availability"])
        self.assertEqual("no_normal_snapshot_for_quarantine", quarantine["resources"]["snapshot"]["reason"])
        self.assertEqual("saved", legacy["library"]["status"])
        self.assertEqual("not_captured_by_strict_protocol", legacy["resources"]["raw"]["reason"])
        self.assertIn("p.ENTERPRISE_ID=:enterprise_id", cur.calls[1][0])
        self.assertIn("NOT EXISTS", cur.calls[1][0])
        self.assertEqual(11, cur.calls[2][1]["enterprise_id"])
        self.assertEqual(101, cur.calls[2][1]["workspace_id"])

    def test_task_result_resource_is_task_and_tenant_bound_and_parses_raw(self):
        columns = [
            "RESOURCE_KIND", "RAW_ID", "TASK_ID", "JOB_ID", "ATTEMPT_ID", "DEVICE_ID",
            "REQUEST_KEY", "SOURCE_TYPE", "PAYLOAD_SHA256", "RAW_JSON", "COLLECTED_AT",
        ]
        cur = Cursor([
            (["OWNED"], [(1,)]),
            (columns, [("raw", 200, 5, 8, 81, 2, "request-1", "product", "a" * 64,
                        '{"platform_code":"pinduoduo"}', "t")]),
        ])

        result = q.task_result_resource(cur, 5, "raw", 200, tenant=TENANT_A)

        self.assertEqual("raw", result["resource_kind"])
        self.assertEqual(200, result["resource_id"])
        self.assertEqual({"platform_code": "pinduoduo"}, result["details"]["raw_data"])
        self.assertEqual("available", result["resources"]["raw"]["availability"])
        resource_sql, resource_params = cur.calls[1]
        self.assertIn("r.RAW_ID=:resource_id", resource_sql)
        self.assertIn("r.TASK_ID=:task_id", resource_sql)
        self.assertIn("r.ENTERPRISE_ID=:enterprise_id", resource_sql)
        self.assertIn("r.WORKSPACE_ID=:workspace_id", resource_sql)
        self.assertEqual({"resource_id": 200, "task_id": 5, "enterprise_id": 11, "workspace_id": 101},
                         resource_params)

    def test_task_result_resource_cross_tenant_and_missing_are_indistinguishable(self):
        cross_tenant = Cursor([(["OWNED"], [])])
        self.assertIsNone(q.task_result_resource(cross_tenant, 5, "snapshot", 100, tenant=TENANT_A))
        self.assertEqual(1, len(cross_tenant.calls))

        missing = Cursor([(["OWNED"], [(1,)]), (["SNAPSHOT_ID"], [])])
        self.assertIsNone(q.task_result_resource(missing, 5, "snapshot", 100, tenant=TENANT_A))
        self.assertIn("s.SNAPSHOT_ID=:resource_id", missing.calls[1][0])
        self.assertIn("s.TASK_ID=:task_id", missing.calls[1][0])

    def test_snapshot_resource_uses_snapshot_id_and_keeps_diff_and_provenance(self):
        columns = [
            "RESOURCE_KIND", "SNAPSHOT_ID", "MASTER_PRODUCT_ID", "ENTERPRISE_PRODUCT_ID",
            "LEGACY_PRODUCT_ID", "RAW_ID", "QUALITY_RESULT_ID", "TASK_ID", "JOB_ID",
            "ATTEMPT_ID", "NORMALIZED_JSON", "SKU_JSON", "FIELD_SOURCES", "QUALITY_STATUS",
        ]
        row = ("snapshot", 100, 10, 110, 1000, 200, 300, 5, 8, 81,
               '{"title":"完整标题"}', '[{"name":"1盒"}]', '{"title":"detail_response"}', "passed")
        diff_columns = ["DIFF_ID", "CHANGED_FIELDS_JSON", "PRICE_CHANGED"]
        provenance_columns = ["FIELD_NAME", "SOURCE_TYPE", "SOURCE_REF", "TRANSFORMATION"]
        cur = Cursor([
            (["OWNED"], [(1,)]),
            (columns, [row]),
            (diff_columns, [(400, '{"price":{"before":1,"after":2}}', 1)]),
            (provenance_columns, [("title", "detail_response", "raw:200", None)]),
        ])

        result = q.task_result_resource(cur, 5, "snapshot", 100, tenant=TENANT_A)

        self.assertEqual(("snapshot", 100), (result["resource_kind"], result["resource_id"]))
        self.assertEqual(100, result["snapshot_id"])
        self.assertEqual(200, result["raw_id"])
        self.assertEqual(300, result["quality_result_id"])
        self.assertEqual({"title": "完整标题"}, result["details"]["normalized"])
        self.assertEqual("detail_response", result["details"]["provenance"][0]["source_type"])
        self.assertEqual(2, result["details"]["difference"]["changes"]["price"]["after"])
        self.assertEqual({"resource_id": 100, "task_id": 5, "enterprise_id": 11, "workspace_id": 101},
                         cur.calls[1][1])

    def test_quality_resource_exposes_raw_snapshot_or_quarantine_ids_without_guessing(self):
        columns = [
            "RESOURCE_KIND", "QUALITY_RESULT_ID", "RAW_ID", "TASK_ID", "JOB_ID", "ATTEMPT_ID",
            "SNAPSHOT_ID", "QUARANTINE_ID", "ACCEPTED", "STATUS", "MISSING_FIELDS_JSON",
            "ERROR_CODES_JSON", "WARNINGS_JSON",
        ]
        cur = Cursor([
            (["OWNED"], [(1,)]),
            (columns, [("quality", 301, 201, 5, 7, 71, None, 101, 0, "rejected",
                        '["price"]', '["MISSING_PRICE"]', '[]')]),
        ])

        result = q.task_result_resource(cur, 5, "quality", 301, tenant=TENANT_A)

        self.assertEqual(301, result["quality_result_id"])
        self.assertEqual(201, result["raw_id"])
        self.assertEqual(101, result["quarantine_id"])
        self.assertIsNone(result["snapshot_id"])
        self.assertEqual("no_normal_snapshot_for_quarantine", result["resources"]["snapshot"]["reason"])
        self.assertEqual(["MISSING_PRICE"], result["details"]["error_codes"])

    def test_task_events_are_complete_and_stably_ordered(self):
        cur = Cursor([(["COUNT"], [(1,)]), (["EVENT_ID", "DETAIL_JSON"], [(1, '{"paused_jobs":2}')])])
        result = q.task_events(cur, 9, 1, 50)
        self.assertEqual(result["items"][0]["detail"], {"paused_jobs": 2})
        self.assertIn("CREATE_TIME ASC,EVENT_ID ASC", cur.calls[1][0])
        self.assertNotIn("LEASE_TOKEN_HASH", cur.calls[1][0])


if __name__ == "__main__":
    unittest.main()
