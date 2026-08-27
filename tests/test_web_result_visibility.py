from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

for _key, _value in {
    "APP_ENV": "test", "ORACLE_HOST": "127.0.0.1", "ORACLE_PORT": "1521",
    "ORACLE_SERVICE": "TEST", "ORACLE_USER": "TEST", "ORACLE_PASSWORD": "test-password",
    "JWT_SECRET": "Test-only-JWT-secret-32-characters!",
}.items():
    os.environ.setdefault(_key, _value)

from server.routers import management
from server.schemas import ApiOk
from server.tenant import TenantContext


ROOT = Path(__file__).resolve().parents[1]
TENANT = TenantContext(11, 101, 1, 1, "viewer", frozenset({"task:view"}))


class WebResultVisibilityContractTest(unittest.TestCase):
    def test_task_detail_uses_authoritative_task_results_not_library_list(self):
        source = (ROOT / "web/src/views/tasks/TaskDetail.vue").read_text(encoding="utf-8")
        self.assertIn("/api/management/tasks/${expectedTaskId}/results", source)
        self.assertNotIn("/api/products?task_id=", source)
        self.assertIn("本次采集结果", source)
        self.assertIn("已保存商品资料库", source)
        self.assertIn("draft/待保存和 Quarantine", source)
        self.assertIn("taskResults.value = []", source)
        self.assertIn("resultsError.value = requestError", source)
        self.assertIn("createRequestGeneration", source)
        self.assertIn("watch(()=>String(route.params.id),switchTask,{immediate:true})", source)
        self.assertIn("resetTaskState", source)
        for field in ("snapshot_id", "raw_id", "quality_result_id", "quarantine_id"):
            self.assertIn(field, source)

    def test_snapshot_raw_quality_and_quarantine_links_use_their_own_ids(self):
        trace = (ROOT / "web/src/views/management/TaskTrace.vue").read_text(encoding="utf-8")
        detail = (ROOT / "web/src/views/management/TaskResultEvidence.vue").read_text(encoding="utf-8")
        routes = (ROOT / "web/src/router/index.js").read_text(encoding="utf-8")
        self.assertNotIn("/products/${r.master_product_id}/timeline", trace)
        for fragment in (
            "/snapshot/${r.snapshot_id}",
            "/raw/${r.raw_id}",
            "/quality/${r.quality_result_id}",
            "/quarantine/${r.quarantine_id}",
        ):
            self.assertIn(fragment, trace)
        self.assertIn("watch(()=>String(route.params.id),loadTaskTrace,{immediate:true})", trace)
        self.assertIn("requestGeneration.isCurrent", trace)
        self.assertIn("createRequestGeneration", detail)
        self.assertIn("clearPage(attempts);clearPage(events)", trace)
        self.assertIn("results/${route.params.resourceKind}/${route.params.resourceId}", detail)
        self.assertIn("detail.value = null", detail)
        self.assertIn("无权限查看该 Task 证据（403）", detail)
        self.assertIn("tasks/:taskId/results/:resourceKind/:resourceId", routes)
        self.assertIn("perms: ['task:view', 'data:view']", routes)

    def test_management_routes_require_task_view_permission(self):
        paths = {
            "/api/management/tasks/{task_id}/results",
            "/api/management/tasks/{task_id}/results/{resource_kind}/{resource_id}",
        }
        matched = [route for route in management.router.routes if route.path in paths]
        self.assertEqual(paths, {route.path for route in matched})
        for route in matched:
            dependency = route.dependant.dependencies[0].call
            self.assertEqual(("task:view", "data:view"), inspect.getclosurevars(dependency).nonlocals["needed"])
            request = Request({"type": "http", "method": "GET", "path": route.path, "headers": []})
            denied = TenantContext(11, 101, 1, 1, "viewer", frozenset())
            with patch("server.tenant.load_context", return_value=denied):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(dependency(request, user={"user_id": 1}))
            self.assertEqual(403, caught.exception.status_code)
            task_only = TenantContext(11, 101, 1, 1, "viewer", frozenset({"task:view"}))
            with patch("server.tenant.load_context", return_value=task_only):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(dependency(request, user={"user_id": 1}))
            self.assertEqual(403, caught.exception.status_code)

    def test_missing_task_resource_returns_same_not_found_contract(self):
        with patch.object(management, "_run", return_value=ApiOk(data=None)):
            result = management.task_result_resource(
                5, "snapshot", 100, tenant=TENANT,
            )
        self.assertFalse(result.ok)
        self.assertEqual("NOT_FOUND", result.data["error_code"])
        self.assertNotIn("tenant", result.message.lower())


if __name__ == "__main__":
    unittest.main()
