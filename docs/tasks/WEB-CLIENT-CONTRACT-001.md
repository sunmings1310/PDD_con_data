# WEB-CLIENT-CONTRACT-001：统一租户感知 Web Client 契约

- **Task ID**：WEB-CLIENT-CONTRACT-001
- **Title**：统一 tenant-aware Web HTTP client、Excel 请求头与权限路由
- **Status**：IN_PROGRESS
- **Base**：`origin/main@85ba3a56bb3f70b5613d565f8b1a6873198b7ddb`
- **Branch**：`codex/web-client-contract-001`
- **Worktree**：`D:\work\PDD_con_data_web_client_contract`

## Goal

建立一个可测试的 Web client 契约，使普通 JSON、multipart 与 blob/Excel 请求都从同一权威客户端上下文发送 token、enterprise 与 workspace；权限路由、401/403/404/API envelope 和租户切换 stale-state 使用一致语义，同时保持服务端 Oracle tenant/workspace、RBAC 与 NOT_FOUND 为最终权威。

## Context

依赖 `WEB-RESULT-VISIBILITY-001` 已通过 PR #7 merge，并经 accepted-state PR #8 同步到 `main@85ba3a5`。当前 `web/src/api/http.js` 已为普通 Axios 请求注入三类 header，但 Excel template/match/export 在 `ExcelMatch.vue` 直接使用全局 Axios，并只拼 Authorization，导致 enterprise/workspace 丢失。Store、localStorage、route guard、页面错误分支与 WebSocket 又分别读取或解释身份上下文，切换 tenant/workspace 依赖整页 reload 才隔离旧状态。

## Baseline Contract Matrix

| Surface | 当前入口与上下文来源 | 当前差异/风险 | 本 Task 最小目标 |
|---|---|---|---|
| JSON API | `web/src/api/http.js` Axios instance；每次从 localStorage 读取 token/enterprise/workspace | 上下文来源与 Pinia store 分离；401 只清 storage，错误对象存在 Axios/plain `ApiOk` 两种形态 | 单一 context provider；一致 envelope/error 契约；401 清理 store 与 storage |
| Excel template | `ExcelMatch.vue` 直接 `axios.get` + `tokenHeaders()` | 只带 token，缺 tenant headers；blob 错误解析与普通 client 不一致 | 使用统一 client 的 blob/download 能力，三类 header 一致 |
| Excel match | `ExcelMatch.vue` 直接 `axios.post(FormData)` | 只带 token；tenant server dependency 会 400/404；页面自行解析 `ok` | 统一 multipart client 与 error mapping |
| Excel export | `ExcelMatch.vue` 直接 `axios.post(..., responseType:'blob')` | 只带 token；JSON error blob 自行解析 | 统一 blob 成功/错误解析，保持下载行为 |
| Excel dispatch | `http.post('/api/excel/unmatched-to-task')` | 已走 client，但属于后续导入业务边界 | 仅保证 client 契约，不改变 dispatch 产品行为/UI |
| Direct HTTP scan | Web 源码除 `http.js` 外只有 `ExcelMatch.vue` 直接 Axios；未观察到直接 `fetch/XMLHttpRequest` | 后续新增旁路风险 | 回归测试禁止批准范围内重新出现旁路 |
| WebSocket | `DeviceCast.vue` query 参数；`DeviceLive.vue` auth message；均直接读 localStorage | 非 HTTP，且 BL-110 已有独立认证边界 | 本 Task 不重构协议；只记录为相邻边界，不扩大范围 |
| Tenant selector | `user.js` 同时维护 Pinia + localStorage；`AdminLayout.vue` 选择后 `router.go(0)` | 切换瞬间旧请求可能回写；summary/profile/route permission 有 stale 窗口 | context generation/abort 或等价可测试 fence；切换后旧响应不得进入新上下文 |
| Route permission | `router/index.js` 的 `meta.perm/perms` + `profile.perms` | UI permission 是提示性快照；selected tenant 服务端权限仍由 `require_tenant_perms` 决定 | 统一 guard helper；多权限 AND；403 不重解释为 404，服务端拒绝保持权威 |
| 401 | `http.js` 删除 token 并跳 login | Pinia profile/tenant state 可能保留；多次请求重复提示/跳转 | 幂等 session invalidation，完整清理客户端 auth state |
| 403 | 页面各自读取 `err.response.status` | 文案和错误形态漂移 | 稳定 client error code/status，route/action 不泄露数据 |
| 404/NOT_FOUND | HTTP 404 与 `ApiOk(ok=false,data.error_code=NOT_FOUND)` 并存 | plain data/Axios error 分支重复 | 规范化但不改变服务端“跨租户与不存在不可区分”语义 |

## Scope

### Allowed

- 抽取/完善 `web/src/api/http.js` 及紧邻的 auth/tenant context、error normalization、request generation/abort helper。
- 让现有 Excel template/match/export 使用统一 client，覆盖 JSON、multipart、blob 与 blob 中 JSON error。
- 统一 `router/index.js` 的 `perm/perms` guard helper，并确保 route guard 只做客户端提示；服务端 `require_tenant_perms` 仍是权威。
- 修复 401 logout 清理、403/404/NOT_FOUND 映射及 tenant/workspace 切换时旧请求/旧页面状态回写。
- 如 selected-context 权限无法由现有 `/api/auth/me` 契约表达，可最小扩充 auth context DTO/query；不得绕过服务端 RBAC 或新增缓存权威。
- 增加可执行 offline Web client/route/Excel contract tests，以及必要的 Python tenant/auth contract tests。
- 仅在实际契约边界变化时更新 `docs/architecture.md` 或既有 API 文档。

### Forbidden

- 实现 `WEB-TASK-IMPORT-001` 的模板设计、Excel 解析、导入向导、去重、商品匹配、未匹配转目标或任务下发 UI。
- 删除/重定位 Excel 菜单，重做 Excel 页面业务流程，改变 Excel 匹配/导出产品语义。
- Schema、migration、历史数据回填/清理或生产配置。
- Generic SKU、P1 SKU/ProductAttribute Schema、Phase 6B 或第二平台。
- Android、真实账号/真机采集、生产操作、merge 或 release。
- 顺手迁移全部 Web 页面、重做全站状态管理、UI 或测试框架。
- 改变服务端 tenant/workspace ownership、RBAC、跨租户 NOT_FOUND 或 Task/Product 成功语义。

## Non-goals

- 不统一 WebSocket/Cast 协议；仅保证本 Task 的 HTTP 请求上下文。
- 不把客户端 route guard 变成授权真相；客户端不能旁路或替代服务端校验。
- 不消除所有历史页面文案差异，只处理统一 client 返回形态所必需的调用点。

## Dependencies

- `WEB-RESULT-VISIBILITY-001`：MERGED / ACCEPTED。
- Accepted Phase 5/5.5 tenant/workspace 与 BL-110 WS tenant boundary。
- `WEB-TASK-IMPORT-001` 必须等待本 Task merge 后从新 main 单独启动。

## Affected Modules

### Expected minimum modification boundary

- `web/src/api/http.js`
- 新增或最小复用 `web/src/api/` / `web/src/utils/` 中的 context/error helper
- `web/src/stores/user.js`
- `web/src/router/index.js`
- `web/src/layout/AdminLayout.vue`
- `web/src/views/excel/ExcelMatch.vue`
- `web/package.json` 与 `web/scripts/` 下 targeted executable tests
- `tests/test_phase5_tenancy.py` 及新增 client contract test

### Conditional only

- `server/routers/auth.py`、`server/tenant.py`：仅当 selected tenant 权限契约确实缺失且可在现有表/DTO内最小表达。
- `docs/architecture.md`：仅记录真实边界变化。

### Explicitly excluded neighboring files

- `server/routers/excel_match.py` 的匹配/解析/导出/下发业务逻辑，除非只需不改变行为的契约测试。
- `DeviceCast.vue`、`DeviceLive.vue` WebSocket 协议。
- 其他 Web 页面批量迁移。

## ADR

不预设新增 ADR。沿用 Accepted enterprise/workspace、RBAC、NOT_FOUND 与 Web result visibility 决策。若需要改变 selected-context 权限产品行为、服务端错误语义或引入新的身份权威，停止并提交 ADR/Product Owner。

## Acceptance Criteria

- [ ] JSON、multipart、Excel template/match/export blob 均由同一 client context 注入有效 Authorization、`X-Enterprise-Id`、`X-Workspace-Id`；无批准的直接 Axios/fetch 旁路。
- [ ] 请求使用发起时不可变的 context snapshot；tenant/workspace 切换后旧请求会被取消或标记 stale，旧响应不能覆盖新上下文状态。
- [ ] 401 会幂等清除 Pinia 与 storage 的 token/profile/tenant context，并只触发确定的登录跳转；不会保留可误用的旧权限。
- [ ] 403 保持 forbidden，404 与服务端 `NOT_FOUND` 保持“资源不存在或不属于当前租户”的不可枚举语义；client normalization 不泄露资源存在性。
- [ ] Route `perm` 与 `perms` 使用同一 helper，多权限保持 AND；UI guard 不能替代服务端 RBAC。
- [ ] Excel template/match/export 在 tenant-aware client 下保持原业务输入、输出、文件名与下载行为；blob 内 JSON error 可解释且不下载伪文件。
- [ ] Excel 页面按钮/route 对 `excel:import`、`excel:match`、`excel:export` 的客户端可见性与服务端要求一致；服务端拒绝仍为最终结果。
- [ ] tenant 切换会清理或刷新 summary、页面请求与 permission context，不依赖旧请求自然结束。
- [ ] 不实现模板/解析/导入/下发新功能，不修改 Schema/migration/Excel业务/Android/采集链。
- [ ] targeted client/route/Excel tests、Python tenant contracts、Web production build、Python full、Android JVM、compile/diff 适用回归通过。
- [ ] 若 server Oracle-backed permission/context query 发生变化，固定 Head 隔离 Oracle strict 与 evidence validator 通过；Independent Review 与 E2E 完成，无新增 P0。

## Test Plan

| Layer | Command / scenario | Expected | Baseline | Status |
|---|---|---|---|---|
| Python targeted | `python -m unittest -v tests.test_phase5_tenancy tests.test_web_result_visibility`，offline import config | existing tenant/result contract | `Ran 11 tests in 0.010s`; `OK`; exit 0 | PASS |
| Web race | `node web/scripts/test-request-generation.mjs` | result visibility A/B stale fences stay green | 三项 `PASS`; exit 0 | PASS |
| Web build | `.\scripts\test-baseline.ps1 -Suite web -Strict` | production build | `1676 modules transformed`; `built in 5.78s`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True`; exit 0 | PASS |
| New client unit | executable Node tests for header snapshots, envelope/blob errors, 401/403/404, tenant generation | all contract cases deterministic offline | pending | BLOCKED |
| Router/Excel contract | source/runtime tests for `perm/perms`, Excel no direct Axios, action permissions | no drift/bypass | pending | BLOCKED |
| Full regression | canonical Python/Web/Android/compile/diff | no Phase 1～6A or result visibility regression | pending | BLOCKED |
| E2E | two authorized tenant contexts + limited permission context; switch during deferred request; Excel template/match/export errors | exact headers, no stale write, correct 401/403/404/download behavior | pending | BLOCKED |

首次基线尝试如实记录：缺少 worktree-local ignored runtime 与 offline import config 时，Python import `BLOCKED/FAIL`（缺 `ORACLE_*`/`JWT_SECRET`），Web strict `BLOCKED`（bundled Node absent）；随后仅建立指向既有 `.tools`、`web/node_modules` 的 ignored junction，并使用不连接数据库的 dummy import config，以上基线转为实际 PASS。未把首次 BLOCKED 冒充 PASS。

## Oracle Gate

- Required：Conditional；若只修改 Web client/route/Excel调用且 server query/tenant permission DTO 不变，则明确 `No / SKIPPED (not applicable)`。若修改 `server/tenant.py`、`server/routers/auth.py` 的 Oracle-backed selected-context permission/query 或任何 tenant SQL，则为 **Yes**。
- Reason：客户端 header 与 route tests 可离线验证；服务端 tenant/RBAC query 变更必须由真实 Oracle证明。
- Local isolated environment identifier：conditional，固定 Head 后记录。
- Fixed Head SHA：pending
- Canonical command / test count / literal result hash / exit：pending
- Evidence generated at / expiry：pending
- Four artifacts / rollback / persistent business changes：`docs/tasks/WEB-CLIENT-CONTRACT-001-verification/`；实现阶段更新；禁止持久业务变更。
- Hosted evidence validator：pending / not applicable after final diff classification
- Independent Reviewer provenance check：pending

## Real-device Gate

- Required：No
- Device/scenario：不修改 Android/真实页面/生命周期；`SKIPPED (not applicable)`，不得称为 PASS。
- Command or steps / result：不执行真实账号或真机采集。

## Rollback

- Code rollback：普通 `git revert` 本 Task commits，恢复旧 client/Excel调用；不强推、不改写历史。
- Configuration rollback：删除本 worktree ignored runtime junction；无生产配置。
- Data recovery：无 Schema/migration/业务数据写入；E2E fixture 必须隔离并清理。
- Irreversible items：无。

## Human Decision Points

- selected tenant permission 的产品行为、403/404 对外语义、session 失效体验存在明显不同方案。
- 需要新增身份权威、Schema/migration、生产操作、真实账号/真机或越过本 Task Non-goals。
- PR 可在 Review ACCEPT 后按 Workflow 创建 Draft；merge/release 必须 Product Owner 明确批准。

## Stop Condition

- Dev 在固定 branch/worktree 完成最小实现、targeted→module→full 自检、提交并 push 后，停止交给独立 E2E/Review；Dev 不创建 PR、不 merge。
- 若需要实现 Excel 导入/下发新功能、批量重构全部 Web、改变服务端权威 tenant/RBAC/NOT_FOUND 产品语义或执行 Schema/migration，立即停止交回 Control/Product Owner。
- 本 Task 完成后不得自动启动 `WEB-TASK-IMPORT-001`、Generic SKU/P1 Schema、Phase 6B 或 release。

## Evidence

- Original evidence：`main@85ba3a5` 的 `http.js`、`user.js`、router、AdminLayout、ExcelMatch、tenant/auth/excel endpoints 与现有 tests。
- Derived artifacts：`docs/tasks/WEB-CLIENT-CONTRACT-001-verification/`。
- Review findings：pending
- Commit / PR：Task setup pending；PR 未创建。
