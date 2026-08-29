# PDD-TARGET-MATCH-TERMINAL-001：目标精确匹配与未匹配业务终态

- **Task ID**：PDD-TARGET-MATCH-TERMINAL-001
- **Title**：目标精确匹配与未匹配业务终态
- **Status**：REVIEW（Dev gates complete；等待 Independent Review，不是 ACCEPTED）

## Goal

修复 `SKU-PANEL-EVIDENCE-001` 在 Task 3534 暴露的同一条 P0/P1 链路：无关搜索结果不得被当作已批准目标继续执行；目标自然结束且未匹配时必须以可观察、不可重试的 `not_matched` 业务终态结束，而不是映射为 `transient / LOCAL_TASK_FINISHED` 并重复执行。

## Context

- 固定起点：`main@80b3435558e67850c9cba4215ca81456721ef0db`。
- Accepted 失败证据：`codex/sku-panel-evidence-001@902f471e9e5d781e3a5d708705a7faa713732a69`，Independent Review `ACCEPT`。
- Task 3534 实际进入错误商品详情；五次 Attempt 均为 `failed/transient/LOCAL_TASK_FINISHED`；Task/Item/Job 最终失败，Raw/Snapshot/Receipt 为 0。该运行证据只用于复现和验收，不作为生产 fixture 提交。
- 已确认调用点：`TaskEngine` 使用 `ProductTargetMatcher`；`AgentCoordinator` 当前将非 complete 的 `job_fail` 固定提交为 transient；服务端按 transient retry policy 重试。

## Scope

### Allowed

1. Android 搜索结果/详情导航的目标身份门禁：批准文号、品名、规格、厂家可获得时均参与匹配。
2. 搜索卡片只做可见字段预筛；必要时可进入只读详情补齐字段，但在购买/SKU 入口、结果持久化和成功上报前必须完成完整 `ProductTargetMatcher` 判定。
3. 候选不匹配时安全返回结果列表继续候选；候选耗尽时形成稳定、可解释的 `not_matched`。
4. Android→Server 终态协议：本地无匹配自然结束时 Item=`not_matched`，Job/Attempt 使用不可重试业务终态；不得把该路径无条件映射为 transient。
5. Task 聚合/API/Web 使用既有权威状态展示未匹配/失败明细，本次业务结果、Raw、Snapshot 保持 0，且任务不是 cancelled。
6. 先补失败复现测试，再做最小实现；只修改直接相关 Android/Server/Web 状态展示代码和测试。

### Forbidden

- Generic SKU runtime、SKU_PANEL 自动交互、P1 SKU/ProductAttribute Schema、migration、历史回填、Phase 6B。
- 改变 Product/Snapshot 身份与成功语义、伪造 Raw/Snapshot/Receipt、直接写测试 Oracle 业务结果。
- 真实订单、购物车、支付、生产操作、release、merge。
- 在 `codex/sku-panel-evidence-001` 上写业务代码。

## Non-goals

- 不提升搜索召回或设计通用搜索排序系统。
- 不实现 SKU 维度/组合采集。
- 不重构整个 Task/Job 状态机或全部 Web 页面。
- 不删除历史失败证据。

## Dependencies

- `SKU-PANEL-EVIDENCE-001@902f471...` 的失败证据与 Proposal 已通过独立 Review。
- Accepted Task/Job/Attempt/Lease、ProductTargetMatcher、tenant/workspace 与 Task Detail 语义保持不变。

## Affected Modules

- Android：`TaskEngine`、`ProductTargetMatcher`、`AgentCoordinator`、`TaskStatusMapping` 及相关 JVM 测试。
- Server：Job fail/retry 与 Task/Item 聚合的 service/domain、API 测试及 Oracle 集成测试。
- Web：仅在既有 API 已提供原因但当前详情未显示时做最小展示修复与测试。

## ADR

不新增长期产品语义。复用 Accepted Task/Job/Attempt 状态模型与 Product 身份不变量；如实现要求新增状态或改变聚合行为，停止并提交 ADR/Product Owner 决策。

## Acceptance Criteria

- [x] 失败复现测试保留：`not_matched` 旧映射抛出异常，`TARGET_NOT_MATCHED` 旧服务端写入 `failed`；两项均已在实现前失败。
- [x] `ProductTargetMatcher` 四字段门禁覆盖批准文号、品名、规格、厂家；不匹配在 `TaskEngine.collectOne` 的质量/持久化之前返回，未触及 SKU/Purchase 路径。
- [x] 多候选以 `CandidateResult.NOT_MATCHED` 安全回列表继续；仅全部自然不匹配时本地任务终态为 `not_matched`。
- [x] `business_rejection/TARGET_NOT_MATCHED` 将 Item 写为 `not_matched`，Job/Attempt 为非重试终态并释放 Lease；真实 Oracle 覆盖已通过。
- [x] `TaskStatusMapping.jobFailureFor` 仅将 `not_matched` 映射为 `business_rejection/TARGET_NOT_MATCHED`；其他旧 `job_fail` 路径保留 `transient/LOCAL_TASK_FINISHED`。
- [x] 服务端聚合为既有 `failed` Task 终态（非 cancelled），Item 明细保留 `TARGET_NOT_MATCHED`；Task Detail 已展示未匹配/原因，结果为空时无 Raw/Snapshot；真实 Oracle 断言已通过。
- [x] 既有 outbox ACK 与 lease fence 保持；新增 Oracle 用例断言未匹配仅一条 Attempt 且 Product/Raw/Snapshot/Receipt 均为 0，并已通过。
- [x] Android targeted、Server targeted、Python/Android/Web baseline 与 Oracle-required gate 均已通过，无新增 P0。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Android targeted baseline | `gradlew.bat testDebugUnitTest --tests com.collector.pdd.engine.ProductTargetMatcherTest --tests com.collector.pdd.net.TaskStatusMappingTest --no-daemon` | JDK `D:\work\PDD_con_data\.tools\jdk-17.0.20+8`; SDK `D:\work\pda-picking\tools\android-sdk`; accepted main | existing matcher/mapping tests pass | `BUILD SUCCESSFUL in 2m 10s`; 30 actionable tasks | 0 | PASS |
| Python baseline | `$env:PDD_PYTHON='D:\work\PDD_con_data\.venv-t001\Scripts\python.exe'; powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite python -Strict` | Python 3.10.6; accepted main; Oracle flags absent | offline baseline passes; Oracle-only cases remain explicit skips | `Ran 249 tests in 1.120s`; `OK (skipped=31)`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Python regression | `$env:PDD_PYTHON='D:\work\PDD_con_data\.venv-t001\Scripts\python.exe'; powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite python -Strict` | tested code Head `20a6ae0` | offline regression passes | `Ran 251 tests in 0.981s`; `OK (skipped=32)`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Android regression | `powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite android -Strict` | JDK 17.0.20+8; SDK Android 34; tested code Head `20a6ae0` | Android JVM passes | `BUILD SUCCESSFUL in 31s`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Web | `powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite web -Strict` | accepted Node `v22.18.0` / npm `10.9.3`; `web/node_modules`; gate Head `1522497` | production build passes | `✓ built in 8.40s`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Oracle | `$env:PDD_PYTHON='D:\work\PDD_con_data\.venv-t001\Scripts\python.exe'; powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict` | approved isolated writable Oracle; tested code Head `20a6ae0`; gate Head `1522497` | retry/terminal/aggregate transaction tests pass, cleanup=0 | `Ran 55 tests in 341.773s`; `OK`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |

## Oracle Gate

- Required：Yes
- Reason：修改 Job/Attempt retry 分类、Item 终态与 Task 聚合事务语义。
- Local isolated environment identifier：沿用项目专用可写可清理 Oracle 测试环境；不得回显连接秘密。
- Tested code Head SHA：`20a6ae005ad60549a51578cb0559904cf7017138`。
- Control gate Head SHA：`1522497f77774bb8250ee8e92c98c3c7ec10c7ff`。
- Canonical command / test count / literal result / exit：`test-baseline.ps1 -Suite oracle -Strict`；55 tests；`Ran 55 tests in 341.773s; OK; [PASS] oracle-integration: exit=0; SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True`；exit 0。
- Evidence generated：2026-08-29；isolated cleanup=0、persistent business changes=false。
- Four artifacts / rollback：四制品及 PowerShell 等价 rollback 已复核，`MODIFIED_FILE` 保持 changed。
- Hosted evidence validator：交 Independent Review 后按流程核验。
- Independent Reviewer provenance check：尚未开始；本 Task 当前仅为 REVIEW-ready，非 ACCEPTED。

## Real-device Gate

- Required：Yes，最终业务路径需要真机确认；但实现 Review `ACCEPT` 前不执行。
- Device/scenario：同一受控商品任务，验证错品不进入 SKU_PANEL、未匹配只终结一次并在 Web 显示。
- Command or steps / result：等待 Independent Review `ACCEPT` 后向 Product Owner 单独申请复验批准。

## Rollback

- Code rollback：普通 Git revert 本 Task commits；不得回退 Accepted main 历史。
- Configuration rollback：无持久配置变更。
- Data recovery：测试 fixture 必须逐表清理；本 Task 不迁移/回填数据。
- Irreversible items：无。

## Human Decision Points

- 新增状态、改变 Product/Task 成功语义、Schema/migration、真实账号/真机复验、PR、merge、release 均需按工作流单独批准。

## Stop Condition

- Dev 完成测试/实现/回归并提交固定 Head 后，停止并交 Independent Review。
- Review `CHANGES_REQUIRED` 时仅在本 Task 内修复；`ACCEPT` 后停止，请求 Product Owner 是否执行一次真机复验。
- 若现有协议无法在无 Schema 变更下表达不可重试 `not_matched`，立即 `BLOCKED / DECISION REQUIRED`，不得自行 migration。
- 不创建 PR、不 merge、不 release、不启动 Generic SKU/P1/Phase6B。

## Evidence

- Original evidence：`SKU-PANEL-EVIDENCE-001@902f471e9e5d781e3a5d708705a7faa713732a69`。
- Derived artifacts：`docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification/`。
- Review findings：尚未开始 Independent Review。
- Commits：失败复现 `7294014`；固定实现 `20a6ae0`；Control gate Head `1522497`。PR 仍禁止。

## Dev Execution Evidence（2026-08-29）

- 固定实现 Head：`20a6ae005ad60549a51578cb0559904cf7017138`（前置失败复现提交：`729401476f34073d338222351161d3c903f1de97`）。
- Android：候选结果区分 `COLLECTED / NOT_MATCHED / FAILED`；仅所有已检查候选均自然不匹配时形成 `not_matched`，匹配门禁仍在质量和 Product/outbox 持久化之前。
- 协议：`not_matched → business_rejection/TARGET_NOT_MATCHED`；服务端以既有 Job/Attempt `failed` 非重试终态关闭并把对应 Item 置为 `not_matched`，不新增 Schema/状态。
- 可见性：既有 `TaskDetail` 已按 `not_matched` 显示“未匹配”及 Item `message`；本次不改 Web DTO/Schema。
- 实测：失败复现两项均为 exit 1；Python strict `251 / skipped=32` PASS；Android JVM strict PASS；Control 在 gate Head `1522497` 使用已验收 Node `v22.18.0` / npm `10.9.3` 与 `web/node_modules` 执行 Web canonical command PASS（`✓ built in 8.40s`）；同一批准隔离 Oracle canonical command PASS（55 tests，341.773s），包含 real `TARGET_NOT_MATCHED` 用例。
- Historical：首次 Oracle 尝试只设置 `T003_*`，而 `server.db` 仍读取默认本地 `ORACLE_*` 配置导致失败；随后在同一已批准隔离环境补齐进程变量后以 canonical command PASS。未记录或回显秘密。
- Independent Review 历史：固定 wrapper `660aca2` 收到 `CHANGES_REQUIRED` 的唯一 P1——`DIFF_FILE.patch` 被 PowerShell 写成单行，`git apply --check` 不能执行。已从 Base→`20a6ae0` 的 8 个直接 Android/Server/test 路径以保留换行方式重新生成 zero-context 完整补丁；base probe 的 `git apply --check --unidiff-zero --whitespace=nowarn` exit 0。
- 四制品、准确命令、字面结果、hash 与 PowerShell rollback 等价核验见 [`PDD-TARGET-MATCH-TERMINAL-001-verification/VERIFICATION.txt`](PDD-TARGET-MATCH-TERMINAL-001-verification/VERIFICATION.txt)。

## Dev Stop

已修复 Review 的单一 P1 制品问题，状态保持 `REVIEW`，等待重新 Independent Review；不是 ACCEPTED。不得创建 PR、merge 或 release。
