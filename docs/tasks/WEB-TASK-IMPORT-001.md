# WEB-TASK-IMPORT-001：统一手动输入与 Excel 导入任务流程

- **Task ID**：WEB-TASK-IMPORT-001
- **Title**：统一手动输入与 Excel 导入的 canonical Task 创建/下发契约
- **Status**：IN_PROGRESS
- **Base**：`origin/main@2200ef021ed69f29fd3796b2c7a50252fa60575b`
- **Branch**：`codex/web-task-import-001`
- **Worktree**：`D:\work\PDD_con_data_web_task_import`

## Goal

让手动输入和 Excel 导入共用同一套可审核、可恢复、可幂等的 Task 创建/下发契约与分步流程：

`来源 → 解析/校验/去重 → 已有商品匹配/候选选择 → 选定采集目标 → 平台/设备/账号/优先级/采集节奏/异常策略 → 审核摘要 → 统一提交 → Task Detail`。

服务端 `/api/tasks` 及其紧邻 canonical service 是唯一创建 Task/TaskItem/CollectionJob 的权威写入口；Excel 只负责提供带 provenance 的候选输入，不维持第二套下发语义。

## Context

### 已确认现状

| Surface | 当前行为 | 差异/风险 | 本 Task 最小目标 |
|---|---|---|---|
| `TaskCreate.vue` 手动输入 | 按行 trim 后直接 POST `/api/tasks`；包含完整平台、设备、账号、优先级、节奏和异常配置 | 只有空值检查；没有统一行状态、稳定去重键、审核摘要或提交幂等 | 抽取 canonical draft/payload builder，手动输入进入统一分步状态 |
| `TaskCreate.vue` Excel source | 仅嵌入 `ExcelMatch` | Excel 内部仍自行加载设备并下发，外层任务配置没有复用 | Excel 输出标准化行与选择结果，回填同一个 Task draft |
| `ExcelMatch.vue` | `/api/excel/match` 后把未匹配行直接 POST `/api/excel/unmatched-to-task` | 固定 priority=5，只携带 device/max_detail；绕过账号、完整节奏、异常策略、审核与 canonical submit | 停止 UI 旁路；匹配/选择只产出 targets，最终统一 POST tasks |
| `tasks.py::create_task` | 写 Task、简单 keyword TaskItem、CollectionJob | 不能表达 Excel provenance、target fields、行选择和提交 request identity | 最小扩充 canonical input，并把 Task/Item/Job/receipt 状态放在同一事务 |
| `excel_match.py::unmatched_to_task` | 独立复制 Task/TaskItem SQL 和权限/设备检查 | 与 tasks 创建逻辑漂移，重复下发保护不足 | 新 UI 不再调用；兼容入口仅委托同一 canonical service，或保持受测兼容但禁止继续复制写逻辑 |

### 权威边界

- 服务端 Oracle 仍是 tenant/workspace、Task、TaskItem、Job、提交幂等和最终结果的 Source of Truth。
- Web 的 route/button/loading 不能替代 `task:create` / `task:dispatch`、设备 ownership、平台一致性和 NOT_FOUND 校验。
- 本 Task 不改变 Task Complete、draft→人工保存→资料库、Product/Snapshot 或采集成功语义。

## Canonical Contract

### 1. Draft 与流程

客户端维护一个 Task draft，而非两套页面 payload：

1. `source`：`manual` 或 `excel`，只用于 provenance 与恢复；
2. `rows`：解析后的稳定输入行；
3. `validation`：空值、类型、长度、平台支持和必填 target 字段；
4. `deduplication`：在当前 draft 内计算稳定 dedup key；
5. `matching`：`matched / multiple / unmatched`；
6. `selection`：明确 include/exclude 和候选选择；
7. `task_config`：平台、设备、账号、优先级、节奏、重试/繁忙/风险/异常策略；
8. `review`：提交前展示有效、错误、去重、排除、选择与最终目标计数；
9. `submission`：单一 canonical payload、稳定 submission id、一次服务端事务；
10. 成功 ACK 后跳转 `/tasks/{task_id}`；失败保留 draft 并允许使用同一 submission id 重试。

### 2. 输入行状态

每行至少具有：

- `row_id`：上传/编辑周期内稳定的本地标识；
- `source` / `source_row_index`；
- 原始输入引用与规范化值；
- `validation_status = valid | invalid`；
- `match_status = matched | multiple | unmatched | not_applicable`；
- `selection_status = selected | excluded | choice_required`；
- `dispatch_status = ready | blocked`；
- 可解释 `error_codes[]`。

错误行不得进入 canonical targets；UI 必须显示原因、保留行号并允许修正或明确排除，不能静默丢弃。

### 3. 稳定去重键

- 商品链接或平台 ID 可识别时：`platform + platform_product_id`。
- 药品目标字段完整时：`platform + normalized approval + name + spec + manufacturer`。
- 其他手动关键词：`platform + normalized keyword`。
- 只在同一 draft/tenant/workspace 范围内折叠重复输入；保留原始行来源列表。
- 不用标题猜测平台商品 ID，不把多个不同候选错误合并。

### 4. 匹配与选择语义

- `matched`：唯一候选可默认选定，但审核页允许排除；采集目标必须使用明确平台身份或批准的 target fields。
- `multiple`：默认 `choice_required`；用户必须选择一个候选、改为按原始字段采集，或排除。禁止静默取第一项。
- `unmatched`：可按完整原始 target fields 进入采集；缺失必填字段时 `blocked`。
- 已有商品匹配只影响候选与目标选择，不把历史 Product 当成本次采集成功，也不自动写入资料库。

### 5. Canonical submit 与幂等

- 手动与 Excel 必须由同一 builder 生成相同字段顺序/语义的 canonical payload，并只调用服务端权威 tasks 入口。
- payload 至少包含 `submission_id`、`source`、task metadata/config 和规范化 `targets[]`；服务端重新校验，不信任客户端 row status。
- 同 tenant/workspace、同 `submission_id`、同 payload hash：返回原 `task_id` 和 `idempotent=true`。
- 同 key、不同 payload：拒绝 `IDEMPOTENCY_CONFLICT`。
- Task、TaskItem、CollectionJob 与提交 ACK/receipt 必须在同一事务可确定；响应丢失后同 key 重试不能新建第二个 Task。
- 浏览器重复点击、请求超时和页面重试复用同一 submission id；更改 payload 后必须生成新 id。
- 若现有 Schema 无法在不迁移的情况下可靠实现持久幂等，Dev 必须停止并提交证据；本 Task 不授权新增 Schema/migration。

### 6. Tenant / RBAC / NOT_FOUND

- 所有解析、匹配、候选、设备、账号与 submit 请求使用统一 tenant-aware HTTP client。
- 服务端按 enterprise/workspace 重新查询候选、设备、账号与目标身份；跨租户资源按现有不可枚举 NOT_FOUND 语义处理。
- 最终提交要求 `task:create`；立即下发相关动作保持既有 `task:dispatch` 语义。兼容入口不能放宽权限。
- tenant/workspace 切换使旧 draft response stale/abort；旧上下文不能提交到新上下文。

## Scope

### Allowed

- 在 `TaskCreate.vue` 内形成分步创建/审核流程，并复用或拆分最小的 Task draft、row normalization、payload builder helper。
- 让 `ExcelMatch.vue` 在 embedded 模式输出解析/匹配/选择结果，不直接下发；独立 Excel 菜单仍保留。
- 最小扩充 `TaskCreateIn`、`tasks.py` 与紧邻 service，使 manual/Excel 共用 canonical Task/Item/Job 创建事务。
- 将 `unmatched-to-task` 变为共享 service 的受测兼容入口，或保留旧调用兼容但禁止生产 UI 继续旁路；不得维持第二份 SQL 写逻辑。
- 增加可执行 Node/组件契约、Python API/tenant/RBAC/幂等测试；仅在真实边界变化时更新 architecture/API 文档。

### Forbidden

- Schema、migration、历史数据回填/清理或生产配置。
- 导出业务迁移；导出仍归 Task Detail、Product Library、Quality/Quarantine。
- 直接删除独立 Excel 菜单。
- 改变 draft→人工保存→资料库、Task Complete、Product/Snapshot 或质量语义。
- Generic SKU、P1 SKU/ProductAttribute Schema、Phase 6B、WebSocket、Android、真实账号/真机、生产或 release。
- 全站 UI/状态管理重构、依赖大版本升级或无关格式化。

## Non-goals

- 不实现新的 Excel 导出中心、导入历史管理台或完整批处理平台。
- 不用客户端缓存承担全局幂等、租户隔离或服务端授权。
- 不为未来平台预建复杂插件体系；仅保留 `platform_code` 与 canonical target 边界。

## Dependencies

- `WEB-RESULT-VISIBILITY-001`：MERGED / ACCEPTED。
- `WEB-CLIENT-CONTRACT-001`：MERGED / ACCEPTED，PR #9；统一 tenant-aware HTTP client 已进入 main。
- Fixed Base：`origin/main@2200ef021ed69f29fd3796b2c7a50252fa60575b`。

## Affected Modules

### Expected

- `web/src/views/tasks/TaskCreate.vue`
- `web/src/views/excel/ExcelMatch.vue`
- 新增最小 `web/src/api/`、`web/src/utils/` 或 `web/src/components/` Task draft/payload helper
- `server/schemas.py`
- `server/routers/tasks.py`
- `server/routers/excel_match.py`
- 紧邻 canonical task creation service（如确有必要）
- `web/scripts/` 与 `tests/` targeted contracts
- `docs/architecture.md`、本 Task 与验证制品

### Conditional

- `web/src/router/index.js` / `AdminLayout.vue`：仅处理现有入口交接，不删除菜单。
- Oracle 测试：仅当实现触及 server SQL/transaction/tenant 权威逻辑。

## ADR

当前不新增 ADR；沿用 Accepted Task/tenant/workspace/RBAC/idempotency 不变量。若可靠 submission idempotency 必须新增 Schema，或 matched/multiple/unmatched 的产品行为需要改变，停止交回 Product Owner/ADR。

## Acceptance Criteria

- [ ] manual 与 Excel 走同一分步 draft 和 canonical payload builder；相同目标/config 生成相同业务 payload。
- [ ] 生产 UI 不再直接调用 `/api/excel/unmatched-to-task` 创建第二套 Task。
- [ ] Excel valid/invalid、matched/multiple/unmatched、selected/excluded/choice_required 均有明确、可解释状态。
- [ ] multiple 未选择、错误行、空目标不得提交；重复行按稳定 key 折叠并保留来源。
- [ ] matched 商品不会被当成本次采集成功；选定目标才进入 TaskItem。
- [ ] 平台、设备、账号、优先级、节奏和异常策略在 manual/Excel 间完全复用。
- [ ] 服务端重新验证 targets、tenant/workspace、RBAC、设备/账号 ownership 与平台一致性。
- [ ] 同 submission id/同 payload 重试返回同 task；不同 payload 冲突；重复点击/ACK 丢失不重复下发。
- [ ] tenant/workspace 切换使旧解析/匹配/submit stale，跨租户资源保持 NOT_FOUND。
- [ ] 创建 Task、TaskItem、CollectionJob 和提交 receipt/ACK 的事务边界可测试。
- [ ] 成功 ACK 后只跳转 canonical Task Detail；失败保留可恢复 draft。
- [ ] 独立 Excel 菜单保留；导出、资料库、Generic SKU/P1/Phase6B/Android 均未改变。
- [ ] targeted→module→Python/Web/Android full→适用 Oracle/E2E 门禁通过；git diff --check 通过。

## Test Plan

| Layer | Command / Scenario | Expected | Baseline | Status |
|---|---|---|---|---|
| Python existing client contract | `python -m unittest -v tests.test_web_client_contract` | accepted tenant-aware client stays green | `Ran 10 tests in 0.015s`; `OK`; exit 0 | PASS |
| Python compile | `python -m compileall -q server tests` | syntax clean | no output; exit 0 | PASS |
| Node baseline | `node --version` / dependency check | record runtime before Dev setup | `v20.11.1`; web/node_modules absent; version exit 0 | BLOCKED for project Node gate; not called PASS |
| New Node/flow contract | real builder + TaskCreate/Excel embedded flow | canonical equivalence, states, duplicate click, stale switch, error recovery | pending | NOT RUN |
| Python API | canonical create + compatibility adapter | empty/invalid/duplicate/multiple, replay/conflict, RBAC/NOT_FOUND | pending | NOT RUN |
| Web full | `.\scripts\test-baseline.ps1 -Suite web -Strict` | Node 22 production build | pending | NOT RUN |
| Python full | `.\scripts\test-baseline.ps1 -Suite python -Strict` | no regression | pending | NOT RUN |
| Android JVM | `.\scripts\test-baseline.ps1 -Suite android -Strict` | no regression | pending | NOT RUN |
| Compile/diff | `python -m compileall -q server tests`; `git diff --check` | clean | compile/diff exit 0 | PASS |
| E2E | manual and Excel targets through review→single submit→Task Detail | one Task, correct items/config/tenant and retry behavior | pending | NOT RUN |

首次 Node 观察只证明系统 Node 为 20.11.1 且新 worktree 未含 ignored `web/node_modules`；它不是项目固定 Node 22 Web Gate 的 PASS。Dev 必须使用仓库 canonical strict 入口或批准的 ignored runtime junction 后运行真实门禁。

## Oracle Gate

- Required：**Conditional, expected Yes if Dev changes server SQL/transaction/tenant behavior**
- Reason：本任务预期收口 `tasks.py` 与 `excel_match.py` 的 Oracle Task/TaskItem/Job 创建事务及持久幂等；一旦修改即必须在固定 Head 运行隔离 Oracle strict。
- Local isolated environment identifier：pending final fixed Head
- Fixed Head SHA：pending
- Canonical command：`powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict`
- Evidence / validator / Reviewer provenance：pending
- 若最终仅改 Web 且 server SQL 未变，必须由差异分类和 Independent Review 明确证明不适用，不能自行称 PASS。

## Real-device Gate

- Required：No
- Device/scenario：不修改 Android 或真实采集行为。
- Result：`SKIPPED (not applicable)`，不得称 PASS。

## Rollback

- Code rollback：普通 `git revert` 本 Task commits；恢复旧 UI 后仍保持服务端兼容入口。
- Configuration rollback：移除 worktree-only ignored runtime junction；无生产配置。
- Data recovery：测试 Task/fixture 必须在隔离事务 rollback/cleanup；无 Schema/migration。
- Irreversible items：无。

## Human Decision Points

- matched/multiple/unmatched 的默认选择需要改变本 Task 已冻结语义；
- 持久提交幂等无法在无 Schema migration 下可靠实现；
- 需要删除独立 Excel 菜单、改变资料库/Task成功语义、生产操作或扩大范围；
- PR merge 与 release。

## Stop Condition

- Dev 在固定 branch/worktree 完成最小实现、targeted→module→full、必要 Oracle、自检、四制品更新、提交并 push 后停止，交 Control 进入 Independent Review/E2E；Dev 不建 PR、不 merge。
- 需要 Schema/migration、产品语义选择、真实账号/真机/生产、Generic SKU/P1/Phase6B 或全站重构时立即停止。
- 本 Task 完成后不得自动启动 `WEB-STATE-UX-001` 或 release。

## Evidence

- Original evidence：`TaskCreate.vue` 手动 POST `/api/tasks`；`ExcelMatch.vue::dispatchAndroidMatch` POST `/api/excel/unmatched-to-task`；`tasks.py::create_task` 与 `excel_match.py::unmatched_to_task` 两套 Task SQL。
- Derived artifacts：`docs/tasks/WEB-TASK-IMPORT-001-verification/`。
- Review findings：pending。
- Commit / PR：Task setup pending commit；Dev 不创建 PR。
