# WEB-RESULT-VISIBILITY-001：采集结果可见性与证据下钻

- **Task ID**：WEB-RESULT-VISIBILITY-001
- **Title**：采集结果可见性与证据下钻
- **Status**：REVIEW_FIX_2_DEV_SELF_CHECK_COMPLETE（E2E PASS；等待新 fixed-Head Independent Review）
- **Base**：`origin/main@09e717cdc3f67eaaf620d6a5e796445ec0334674`
- **Branch**：`codex/web-result-visibility-001`
- **Worktree**：`D:\work\PDD_con_data_web_result_visibility`

## Goal

让有权限的管理端用户稳定查看当前 Task 的采集结果，并能以服务端权威资源 ID 从 Task 下钻到 Raw、Quality、Snapshot 或 Quarantine；同时明确区分“本次采集结果”和“已保存商品资料库”，不改变采集、保存或任务成功语义。

## Context

`BL-110-WS-TENANT-BOUNDARY` 已通过 PR #5 普通 merge，当前唯一业务基线为 `main@09e717c`。现有 Task Detail 主要读取 `/api/products?task_id=...`，会遗漏尚未保存到资料库或进入 Quarantine 的任务结果；执行轨迹虽附带 Snapshot/Quarantine，但 Snapshot 导航仍以 Master Product 路由承载，Raw 与 Quality 缺少任务级直达链路。页面也未统一区分 loading、empty、error 与权限拒绝。

## Scope

### Allowed

- 在服务端现有 tenant/workspace 权威查询边界内，补充或修正 Task 结果读取 DTO/API，使 Snapshot、Quarantine、Raw、Quality 使用各自真实资源 ID。
- 修复 draft/待保存结果在 Task 上的可见性；不得要求先保存到商品资料库才可查看本次采集事实。
- 在 Web Task Detail/Trace 及必要的管理详情视图中实现 Task→Raw→Quality 下钻。
- 明确展示“本次采集结果”与“已保存商品资料库”两种状态和动作边界；保留既有人工保存语义。
- 补齐相关页面的 loading、empty、error、retry 和权限拒绝行为，避免失败后残留上一次数据。
- 增加服务端查询/权限/资源 ID 回归测试和适用的 Web 静态契约验证；保持现有构建与 Phase 1～6A 回归。
- 仅在实现确有必要时更新实际架构或既有 API 文档；不新增第二套状态账本。

### Forbidden

- `WEB-CLIENT-CONTRACT-001`、Excel 导入/导出重构或独立 Excel 菜单去留。
- Generic SKU、SKU Schema、ProductAttribute、正式 migration、历史数据回填或清理。
- Phase 6B、第二平台、Android/真机采集逻辑或真机 Gate。
- 改变 Product/Snapshot/Quality、draft→人工保存→资料库、Task Complete 或采集成功语义。
- release、merge、生产操作或生产配置变更。

## Non-goals

- 不统一全站 HTTP client 或权限路由；该工作属于后续 `WEB-CLIENT-CONTRACT-001`。
- 不建设完整质量管理平台，不重做商品资料库 UI，不新增 Schema。
- 不将页面操作、Parser 对象或 HTTP 2xx 重新定义为业务成功。

## Dependencies

- `BL-110-WS-TENANT-BOUNDARY`：已通过 PR #5 merge 到固定 base。
- Accepted Phase 1～6A、Product Consistency P0、Raw Capture、Quality/Quarantine 与 Canonical Product Contract。
- 后续 `WEB-CLIENT-CONTRACT-001` 必须等待本 Task merge 后从新 main 启动。

## Affected Modules

- Web：`web/src/views/tasks/TaskDetail.vue`、`web/src/views/management/TaskTrace.vue`、`ProductTimeline.vue`、`QuarantineList.vue`、必要路由与局部 API 调用。
- Server：`server/routers/management.py`、`server/management_queries.py` 及仅为 Task 结果读取所需的现有 read model。
- Tests：`tests/test_phase4_management.py` 及针对 tenant-bound resource ID/权限的现有测试模块；Web build/静态契约检查。
- Docs：本 Task、`docs/backlog.md`、`docs/CURRENT_STATE.md`、必要的 architecture/verification 证据。

## ADR

不新增 ADR。沿用 Accepted Product/Snapshot、Phase 3 Quality/Quarantine、Phase 4 管理查询和 Phase 5 tenant/workspace 决策。若实现要求改变产品语义、资源身份或新增持久化模型，立即停止并提交 Product Owner/ADR 决策。

## Acceptance Criteria

- [x] 同时有 `task:view + data:view` 的当前租户用户可看到 Task 范围内的可信 Snapshot、draft/待保存结果与 Quarantine；未保存到资料库不再导致本次采集结果消失。
- [x] 页面明确区分“本次采集结果”和“已保存商品资料库”；保存动作不改变已确认采集事实。
- [x] Snapshot 链接和请求使用服务端返回的真实 `snapshot_id`；Master Product、Enterprise Product、legacy `product_id` 不得冒充 Snapshot ID。
- [x] Task 结果可用服务端权威 ID 下钻到对应 Raw 与 Quality；缺失证据时展示明确 unavailable 原因，不猜测或拼接 ID。
- [x] Quarantine 结果展示失败原因与可用 Raw/Quality 证据，且不会伪装成正常商品/Snapshot。
- [x] loading、empty、error、retry、403/无权限均有确定行为；请求失败会清空或隔离陈旧数据，不显示跨 Task/租户残留。
- [x] 所有读取继续执行 enterprise/workspace 所有权校验；跨租户、无权限及不存在资源不泄露数据。
- [x] 不改变写入、Task 完成、人工保存、Schema/migration、默认 PDD 采集路径或 Android 行为。
- [x] targeted、Python module/full、Web production build、Python compile、Android JVM 与 `git diff --check` 按适用门禁通过。
- [ ] 新 fixed Head Oracle strict、E2E 与 Independent Review 完成；无新增 P0。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `$python='D:/work/PDD_con_data/.venv-t001/Scripts/python.exe'; & $python -m unittest -v tests.test_phase4_management tests.test_phase4_pagination_contract tests.test_phase5_tenancy tests.test_web_result_visibility` | offline fake cursor + tenant/permission fixtures | 稳定分页、exact ID、403 与 ownership 断言通过 | `Ran 28 tests in 0.010s`；`OK` | 0 | PASS |
| Stale race | `& '.tools/node-v22.18.0-win-x64/node.exe' web/scripts/test-request-generation.mjs` | TaskDetail/TaskTrace A/B deferred response 与 deferred confirm | reset 完整；旧 A 不覆盖/清空 B；stale confirm 不发 POST | `STALE_RACE=PASS ...`；`REQUEUE_CONFIRM_RACE=PASS ... stale_request_sent=false`；`TASK_TRACE_RACE=PASS ... preserved=true` | 0 | PASS |
| Web | `.\scripts\test-baseline.ps1 -Suite web -Strict` | bundled Node 22/npm 10；`web/` production build | production build PASS | `1676 modules transformed`；`built in 584ms`；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Python module/full | `$env:PDD_PYTHON='D:/work/PDD_con_data/.venv-t001/Scripts/python.exe'; .\scripts\test-baseline.ps1 -Suite python -Strict` | offline；opt-in Oracle 由独立 Gate 执行 | 无 Phase 1～6A 回归 | `Ran 223 tests in 0.441s`；`OK (skipped=24)`；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Android JVM | 设置固定 JDK/SDK 后 `.\scripts\test-baseline.ps1 -Suite android -Strict` | 不修改 Android；JDK 17/SDK 34 | 既有测试通过 | `BUILD SUCCESSFUL in 7s`；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Real Oracle targeted | `$python='D:/work/PDD_con_data/.venv-t001/Scripts/python.exe'; & $python -m unittest -v tests.test_phase55_oracle.Phase55OracleFinalGate.test_02_two_enterprises_are_isolated_on_all_read_surfaces` | 隔离 writable Oracle；Task A/B、Snapshot/Raw/Quality/Quarantine fixture | 实际 SQL/tenant/resource binding 通过并清理 fixture | `Ran 1 test in 6.185s`；`OK` | 0 | PASS |
| Static | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe -m compileall -q server tests`；`git diff --check` | 当前实现树 | exit 0 | no output / no whitespace errors | 0 | PASS |

开发过程中按 targeted→module 执行；固定实现 Head 后再运行 full/Oracle/Independent Review，不以 `SKIPPED` 或 `BLOCKED` 冒充 `PASS`。

## Oracle Gate

- Required：**Yes**。
- Reason：修改了 Oracle-backed Task/Raw/Quality/Snapshot/Quarantine 管理查询和 tenant-bound 资源 ID 绑定；Hosted CI 不连接数据库。
- Local isolated environment identifier：本地隔离 writable T003 test schema；凭据来自 ignored environment，未写入仓库；targeted fixture 已清理。
- Fixed Head SHA：Review Fix 2 最终 commit SHA 由外部 manifest 与 Control handoff 绑定，避免提交 manifest 后再次移动 Head。
- Canonical command / test count / literal result hash / exit：最终 Head 独占执行 canonical `scripts/test-baseline.ps1 -Suite oracle -Strict`；外部 manifest 记录完整 literal output/hash、46/46、skipped=0、exit 0。
- Evidence generated at / expiry：最终 commit 后生成；validator 时效为 72 小时，精确 UTC 时间见外部 manifest。
- Four artifacts / rollback / persistent business changes：`docs/tasks/WEB-RESULT-VISIBILITY-001-verification/` 四制品；副本 rollback 恢复 SHA-256 `efc9ed1197e3e2e8e212842b71b643de4b321a8d5421b88f87062598110ec6b0`，`MODIFIED_FILE.py` 保持 changed；无持久业务变更。
- Hosted evidence validator：外部 manifest 在最终 Head 使用 `.github/scripts/validate_oracle_local_evidence.py` 独立验证；结果随 handoff 提交。
- Independent Reviewer provenance check：E2E 已 PASS；Reviewer 继续核对最终 Head 本地隔离 Oracle 来源、cleanup、rollback 与四制品 hash。

## Real-device Gate

- Required：No
- Device/scenario：本 Task 不修改 Android 或真实采集路径；记录为 `SKIPPED (not applicable)`，不得称为 PASS。
- Command or steps / result：不执行真机采集。

## Rollback

- Code rollback：对本 Task 独立 commits 执行 `git revert`，恢复原 Task/管理读取与 Web 路由；禁止 history rewrite。
- Configuration rollback：无配置变更。
- Data recovery：禁止 Schema/migration 与持久业务写入；隔离测试数据按测试脚本清理并记录字面结果。
- Irreversible items：无。

## Human Decision Points

- 产品语义、Product/Snapshot/Quality/draft 保存边界、跨租户可见性策略发生变化。
- 需要 Schema/migration、数据回填/清理、生产操作、真实账号/真机、扩大到被禁止任务。
- 创建 PR 可按当前 Workflow/Task 授权推进；merge 与 release 必须等待 Product Owner 明确批准。

## Stop Condition

- scope/acceptance/test/Oracle/rollback 已冻结，Dev 完成实现与自检，E2E/固定 Head 门禁和 Independent Review 形成可复验证据后停止在 merge 前。
- 若证据推翻现有资源身份/产品语义、要求 Schema/migration、跨入排除范围，或 Oracle/权限环境导致必要验收 `BLOCKED`，立即停止并交由 Control/Product Owner。
- 不自动启动 `WEB-CLIENT-CONTRACT-001`、Excel 导入、Generic SKU/SKU Schema、Phase 6B、真机采集或 release。

## Evidence

- Original evidence：`main@09e717c` 的 `TaskDetail.vue`、`TaskTrace.vue`、`management.py`、`management_queries.py`、`test_phase4_management.py`。
- Derived artifacts：`docs/tasks/WEB-RESULT-VISIBILITY-001-verification/`：`MODIFIED_FILE.py`、`DIFF_FILE.patch`、`VERIFICATION.txt`、executable `ROLLBACK.sh`；baseline/modified/rollback 命令、字面结果、exit 和 restored status 见 `VERIFICATION.txt`。
- Implementation evidence：新增 tenant-bound `GET /api/management/tasks/{task_id}/results` 与 `GET /api/management/tasks/{task_id}/results/{resource_kind}/{resource_id}`；DTO 明确 exact ID/unavailable/library state；Task Detail/Trace 不再以列表行或 Master Product 冒充结果资源；新证据页为只读。
- Tests：offline targeted 28/28、Python 223/223（24 个环境 opt-in skip 单独处理）、Web build、Android 70 XML cases、真实 Oracle targeted 1/1、compile/diff 均 PASS；fixed-Head strict Oracle 在最终 commit 后生成外部 manifest。
- Review findings（2026-08-27 Review Fix）：
  1. **RESOLVED**：Task results `ORDER BY` 增加 `RESULT_KIND` 与 Snapshot/Quarantine/Product/Raw/Quality authoritative ID 全序；同 timestamp、跨 result kind 相同 ID、跨页无重复漏项回归通过。
  2. **RESOLVED**：新增可执行 `requestGeneration` helper 与 A/B 乱序 Node 回归；Task Detail/Trace/Evidence 路由切换同步 reset，旧 generation 不得写回。
  3. **RESOLVED**：Task result/evidence API 恢复 Accepted Phase 4 `data:view`，与 `task:view` 及 Task/tenant ownership 取交集；task-only 用户返回 403。
  4. **RESOLVED BY FINAL-HEAD EXTERNAL EVIDENCE**：旧 Head Oracle 46/46 只作发现证据；每轮 Review Fix 最终 commit 后独占重跑 canonical strict，并以新 Head 外部 manifest 为唯一有效证据。
  6. **RESOLVED**：deferred confirm 期间 A→B 切换会在 POST 前返回 stale，固定 `taskId` 不读取实时 route；测试确认 `stale_request_sent=false`。
  7. **RESOLVED**：TaskTrace fetch outcome 区分 `ok/failed/stale`；只有当前 generation 的真实 `failed` 才清空 selection/attempts/events，旧 A stale 不影响 B。
  5. **RESOLVED**：`VERIFICATION.txt` 可复制命令改用 forward-slash path/PowerShell 变量，移除反斜杠转义歧义；副本 rollback 重测。
- Commit / PR：最终 Dev commit 与 push 完成后在 handoff 记录固定 SHA；PR 未创建。
