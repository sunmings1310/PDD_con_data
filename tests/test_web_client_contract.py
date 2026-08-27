from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class WebClientContractTests(unittest.TestCase):
    def source(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_http_has_single_context_and_no_direct_storage_reads(self):
        http = self.source("web/src/api/http.js")
        context = self.source("web/src/api/clientContext.js")
        self.assertNotIn("localStorage", http)
        self.assertIn("clientContext.beginRequest()", http)
        self.assertIn("headersForContext(requestContext.snapshot)", http)
        self.assertIn("undefined, { synchronous: true })", http)
        for header in ("Authorization", "X-Enterprise-Id", "X-Workspace-Id"):
            self.assertIn(header, context)

    def test_excel_uses_shared_json_multipart_and_blob_client(self):
        excel = self.source("web/src/views/excel/ExcelMatch.vue")
        self.assertNotRegex(excel, r"(?:from\s+['\"]axios['\"]|\baxios\.)")
        self.assertNotIn("tokenHeaders", excel)
        self.assertIn("http.getBlob('/api/excel/template')", excel)
        self.assertIn("const response = await http.post(", excel)
        self.assertIn("const blob = await http.postBlob(", excel)
        self.assertNotIn("response.data.data", excel)

    def test_excel_action_permissions_match_server_dependencies(self):
        excel = self.source("web/src/views/excel/ExcelMatch.vue")
        server = self.source("server/routers/excel_match.py")
        for permission in ("excel:import", "excel:match", "excel:export"):
            self.assertIn(f"store.hasPerm('{permission}')", excel)
            self.assertIn(f'require_tenant_perms("{permission}")', server)
        self.assertRegex(server, r'unmatched_to_task[\s\S]+require_perms\("task:dispatch"\)')
        self.assertRegex(server, r'unmatched_to_task[\s\S]+require_tenant_perms\("task:create"\)')

    def test_route_guard_uses_one_and_permission_helper(self):
        router = self.source("web/src/router/index.js")
        helper = self.source("web/src/router/permissions.js")
        self.assertIn("hasRoutePermissions(to.meta", router)
        self.assertIn("return '/profile'", router)
        self.assertIn(".every((permission)", helper)
        self.assertIn("Array.isArray(meta.perms)", helper)

    def test_401_binds_complete_store_reset_and_login_redirect(self):
        main = self.source("web/src/main.js")
        store = self.source("web/src/stores/user.js")
        errors = self.source("web/src/api/clientErrors.js")
        self.assertIn("bindSessionReset(() => userStore.resetSessionState())", main)
        self.assertIn("bindUnauthorizedRedirect(() => router.replace('/login'))", main)
        for state in ("profile", "tenantContexts", "enterpriseId", "workspaceId", "summary"):
            self.assertRegex(store, rf"this\.{state}\s*=")
        self.assertIn("UNAUTHORIZED", errors)

    def test_tenant_switch_aborts_and_remounts_without_reload(self):
        layout = self.source("web/src/layout/AdminLayout.vue")
        context = self.source("web/src/api/clientContext.js")
        self.assertIn("store.contextGeneration", layout)
        self.assertNotRegex(layout, r"router\.go\s*\(")
        self.assertIn("controller.abort('client-context-changed')", context)
        self.assertIn("context.generation === snapshot.generation", context)

    def test_not_found_mapping_remains_non_enumerable(self):
        errors = self.source("web/src/api/clientErrors.js")
        self.assertIn("资源不存在或不属于当前租户", errors)
        self.assertRegex(errors, r"status === 404 \|\| code === CLIENT_ERROR_CODES\.NOT_FOUND")

    def test_no_unapproved_direct_http_bypass(self):
        violations: list[str] = []
        excluded_websockets = {
            "src/views/devices/DeviceCast.vue",
            "src/views/devices/DeviceLive.vue",
        }
        for path in (WEB / "src").rglob("*"):
            if path.suffix not in {".js", ".vue"}:
                continue
            relative = path.relative_to(WEB).as_posix()
            source = path.read_text(encoding="utf-8")
            if relative != "src/api/http.js" and re.search(
                r"(?:from\s+['\"]axios['\"]|\baxios\.(?:get|post|put|delete|request)\s*\()",
                source,
            ):
                violations.append(relative)
            if relative not in excluded_websockets and re.search(r"\b(?:fetch|XMLHttpRequest)\s*\(", source):
                violations.append(relative)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
