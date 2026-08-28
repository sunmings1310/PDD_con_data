# WEB-STATE-UX-001：核心 Web 状态与反馈收口

- **Task ID**：WEB-STATE-UX-001
- **Title**：核心 Web 页面 loading/error/empty/retry、状态文案与反馈一致性
- **Status**：DEV_COMPLETE_AWAITING_INDEPENDENT_REVIEW

## Goal

在不改变服务端业务语义的前提下，让统一手动输入/Excel 下发后的主要列表与详情对初次加载、后台刷新、空数据、错误、重试、stale 响应和提交反馈采用一致、可恢复、可解释的行为。

## Context

固定起点：`origin/main@807cfb4eff9c3830f9a7f3ad4f62f1f07d183b41`。`WEB-TASK-IMPORT-001` 已 MERGED/ACCEPTED；本 Task 只收口直接关联核心任务流的 Web 状态，不重新定义 Task、数据质量、租户或权限语义。

### Baseline 状态矩阵

| 页面/模块 | 已有行为 | 已确认差异 | 本 Task 决定 |
|---|---|---|---|
| Task List | loading/error/empty/retry | 初次加载与后台 refresh 共用阻塞 loading；无 route/tenant stale fence；状态文案由 API `ui_status` 与局部 tag 混用 | 纳入 |
| Task Detail | Task/results 分区 loading/error/retry，已有 request generation | refresh 仍表现为初次阻塞；Task/item 未知状态直接裸值且映射分散 | 纳入，保持服务端状态权威 |
| Task Create + embedded Excel | canonical payload、ACK replay、route fence 已 Accepted | 创建失败仅依赖全局 toast，页面缺少可解释的保留上下文/重试反馈；成功必须只去 canonical Task Detail | 纳入反馈收口；不改变 durable idempotency |
| Product Library | loading/error/empty/retry | 无 context generation，租户/工作区切换时旧响应可覆盖新上下文；refresh 阻塞 | 纳入 |
| Quality Dashboard | loading/error/empty/retry | 无 context generation；refresh 与初次 loading 未区分 | 纳入 |
| Quarantine List/Detail | list error/retry、detail error | list/detail 均无 generation，旧响应可覆盖新筛选/上下文；detail error 无明确 retry | 纳入 |
| Task Result Evidence / Task Trace | 已有 request generation、分区 error/retry | 可作为 accepted 参考，未发现必须重写的核心缺口 | 默认不改；仅共享 helper 接口兼容所需的极小调整 |
| standalone Excel / 其他管理页 | 非本次核心任务闭环 | 范围漂移风险 | 排除 |

## Scope

### Allowed

- `web/src/views/tasks/TaskList.vue`
- `web/src/views/tasks/TaskDetail.vue`
- `web/src/views/tasks/TaskCreate.vue`
- `web/src/views/excel/ExcelMatch.vue`（仅 embedded/core-flow 行为）
- `web/src/views/data/ProductList.vue`
- `web/src/views/management/QualityDashboard.vue`
- `web/src/views/management/QuarantineList.vue`
- `web/src/utils/requestGeneration.js` 兼容扩展，或新增一个小型 async-view/status helper
- 最多一个共享轻量状态组件；不引入全局状态库
- `web/scripts/` 下真实 mounted component/contract tests
- 本 Task 文档、权威状态文档和专属验证制品

### Frozen behavior

1. 初次 loading 可阻塞；已有数据的 background refresh 不清空内容，并提供可见刷新状态。
2. empty 仅在“请求成功且数据为空”时显示；error 不得伪装为空或成功。
3. retry 使用当前权威 tenant/workspace/route/filter；重复 refresh/retry 的旧响应不得覆盖新上下文。
4. Task 状态文案由明确映射产生；未知状态安全显示“未知状态（原值）”，不得映射为完成/成功。
5. TaskCreate/embedded Excel 成功 ACK 只进入 `/tasks/{canonical_task_id}`；失败保留 frozen canonical payload 与用户输入，明确可重试且不得生成新 submission identity。
6. 403/404/NOT_FOUND 沿用统一 HTTP client、RBAC 与服务端权威资源边界。

### Forbidden

- Server API/SQL/transaction、Oracle Schema/migration
- Android、真实账号/真机/线上采集
- Generic SKU、P1 Schema、Phase 6B
- Excel 导出归属变更或删除独立 Excel 菜单
- release、后续任务、全站 UI 重构、全局大状态库、依赖大升级

## Non-goals

- 不改变 Task Complete、Product/Quality、tenant/workspace、RBAC 或 NOT_FOUND 语义。
- 不把 HTTP 200、页面完成或本地状态当作业务成功。
- 不将所有历史页面统一重写。

## Dependencies

- `WEB-TASK-IMPORT-001` 与 state sync 已 MERGED/ACCEPTED。
- `main@807cfb4eff9c3830f9a7f3ad4f62f1f07d183b41`。

## Affected Modules

- Web Vue views、现有 tenant-aware HTTP client、request generation helper、Node mounted tests。
- Oracle/Server/Android：不适用，除回归门禁外不得修改。

## ADR

None。采用现有 request-generation/HTTP client 边界的增量收口，不新增长期架构模型。

## Acceptance Criteria

- [x] 初次 loading、background refresh、empty、error、retry 可被 mounted test 区分。
- [x] Task List、Product Library、Quality、Quarantine 的旧 context/filter/route 响应不能覆盖新状态。
- [x] 重复 refresh/retry 最终只保留当前 generation 的结果与反馈。
- [x] Task 状态映射覆盖 Accepted 状态；未知状态不显示为成功/完成。
- [x] TaskCreate/embedded Excel ACK 成功只跳 canonical Task Detail；失败保留上下文并以同 submission/payload 重试。
- [x] error 与 empty 互斥；未确认数据不显示为存在。
- [x] 无 Server/Schema/Android/业务语义变更。
- [x] targeted mounted tests、Web production build 通过；Python/Android 环境回归按实际 SKIPPED/FAIL 记录。
- [x] 四制品和另一副本 rollback 通过；`MODIFIED_FILE` 保持 changed。
- [ ] Independent Review `ACCEPT`、E2E `PASS`、Hosted CI 终态完成。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Baseline mounted | `npx -y node@22.18.0 scripts/test-task-import-components.mjs` | Node 22.18.0 | existing mounted flow passes | two PASS lines | 0 | PASS |
| Baseline helper | `npx -y node@22.18.0 scripts/test-request-generation.mjs` | Node 22.18.0 | existing race tests pass | three PASS lines | 0 | PASS |
| Baseline Web | `npx -y node@22.18.0 node_modules/vite/bin/vite.js build` | dependencies installed by Node 22.18.0 npm | production build | 1682 modules; built in 6.05s | 0 | PASS |
| Targeted modified | `npx -y node@22.18.0 scripts/test-task-import-components.mjs` | mounted delayed adapter | six literal PASS lines | PASS | 0 | PASS |
| Web strict | `npx -y node@22.18.0 node_modules/vite/bin/vite.js build` | Node 22.18.0 | build | 1683 modules; built in 0.554s | 0 | PASS |
| Python applicable | `python scripts/run_python_unit_tests.py` | host Python 3.10 / pydantic mismatch | unit collection | `ImportError: cannot import name field_validator` | 1 | SKIPPED_ENVIRONMENT |
| Android applicable | `android_collector\gradlew.bat testDebugUnitTest` | host JDK absent | unit test | `JAVA_HOME is not set` | 1 | SKIPPED_ENVIRONMENT |

Baseline install note：首次使用系统 Node 20 执行 `npm ci` 后 Vite build 因 Rolldown optional native binding 缺失而 FAIL；随后使用 Node 22.18.0 调用 npm CLI 重新 `npm ci`，build PASS。失败保留为环境诊断，不冒充 PASS。

## Oracle Gate

- Required：No
- Reason：冻结范围禁止 Server SQL/transaction/Schema；若实际 diff 触及相关文件立即停止并重新分类。
- Local isolated environment identifier：N/A
- Tested code / fixed review candidate：`96f5232e46bf757e238d7ce6040bd666d1796390`。本次 documentation evidence closure Head 不在 tracked 文档中自引用；提交后以 `git rev-parse HEAD` 与 stable external manifest 为权威。
- Canonical command / test count / literal result hash / exit：SKIPPED / not applicable
- Evidence generated at / expiry：N/A
- Four artifacts / rollback / persistent business changes：PASS / persistent business changes=false
- Hosted evidence validator：预计 SKIPPED
- Independent Reviewer provenance check：`CHANGES REQUIRED`（第三轮仅证据收口，等待下一次 Re-review）。

## Real-device Gate

- Required：No
- Device/scenario：纯 Web 状态与离线 adapter 测试；不得登录真实账号或采集。
- Command or steps / result：SKIPPED / not applicable

## Rollback

- Code rollback：revert 本 Task commits。
- Configuration rollback：None。
- Data recovery：None。
- Irreversible items：None。

## Human Decision Points

- merge、release、启动后续任务必须由 Product Owner 明确批准。
- 若需改变 Task/Product/Quality/tenant 业务语义，或触及 Server SQL/transaction/Schema，立即停止。

## Stop Condition

- Review `ACCEPT` + E2E `PASS` + Hosted CI 完成后停在 Draft PR merge 前；
- 或出现业务语义、Schema/Oracle、真实账号/设备、范围扩大决策时停止；
- 禁止自动 merge、release 或启动后续任务。

## Evidence

- Original evidence：上述 baseline 状态矩阵及 baseline commands。
- Derived artifacts：`docs/tasks/WEB-STATE-UX-001-verification/`。
- Review findings：`CHANGES REQUIRED`，仅剩证据收口；本次 documentation evidence closure 提交后等待 Re-review。
- Commit / PR：no PR created.

## Review Fix History

- 2026-08-28 Independent Review：`CHANGES REQUIRED`。发现 Task Detail 的 task/results refresh 共用未推进 token、缺 tenant/workspace 监听；Quarantine detail retry 依赖 route query；初版 DIFF_FILE 不是可逆补丁；rollback 命令记录与 Node 实现不一致。
- 2026-08-28 Dev Review Fix：Task Detail 使用 task/results 独立 generation，并由 tenant/workspace/route id 统一 invalidate/reload；Quarantine 保存 selected detail id 并从该 id retry；TaskCreate tenant/workspace 切换使迟到 ACK 失效并重置 submission context；mounted suite 新增 TaskDetail duplicate/context/route、Quarantine filter/detail retry、Product filter、TaskCreate tenant stale 实测。DIFF_FILE 将以 `git apply --check --reverse` 验证；rollback 用 Node CommonJS loader 的精确命令在 changed probe 上重跑。

## Review-Fix Status

- Status：`CHANGES_REQUIRED_EVIDENCE_CLOSURE`。
- Code baseline for initial Dev commit：`45058aaa71c40aaacd4403795dc1563fd0852f5c`；本 Review Fix code candidate：`66972bb4ec08647dd77c4c56e4c0fd9c5fc1e1f4`；后续证据包装提交不在内容中预写自身 SHA。
- Oracle / real device：`SKIPPED_NOT_APPLICABLE`（仅 Web 状态层，未触及 Server SQL/transaction/schema 或 Android）。

## Second Re-review Fix

- Final `--unified=0` DIFF is a prior-wrapper-to-final business/governance target range and excludes self-referential artifacts; it is reverse-checked with `--unidiff-zero`.
- TaskCreate context abort/loading fence, safe status fallback/item raw handling, and changed-byte rollback precondition are covered by mounted tests and rollback probe.
- Evidence wrapper SHA is determined after commit; no document prewrites its own SHA.

## Hosted CI Compatibility Fix

- Hosted CI PR #13 run #33151379495：Python offline failed 1/249 at `test_web_result_visibility.py:37` because accepted source-contract expected the literal `taskResults.value = []`; source-only spacing compatibility restored without changing reset behavior. Governance/Web/Android/Oracle applicability jobs succeeded; Oracle evidence remained skipped.
- Local Python 3.10 isolated venv install was attempted; dependency acquisition was blocked by proxy/SSL, so local targeted/full remain `SKIPPED_ENVIRONMENT`; hosted rerun is required after this Head.
