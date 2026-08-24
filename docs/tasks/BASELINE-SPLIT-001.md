# BASELINE-SPLIT-001：Accepted Business Baseline Split Manifest

- Status：READY FOR FINAL REVIEW / PR REMAINS DRAFT
- Date：2026-08-24
- Base：`origin/main@a3d499594b2bd2bf52a43e31ca6440f63b9a8cd6`
- Source evidence：`90b53658af5bf1e1f0488aaeb520e59887c8c91b`、`13b4301445eda9768069a807a13d9f43cedb8e8f`
- Integration branch：`codex/accepted-business-baseline`

## 1. Split decision

`90b5365` 以完整 commit cherry-pick，生成 integration commit `8bf63e3`。`13b4301` 没有整体 cherry-pick；本清单按 file/hunk 提取 Accepted Raw、Product P0 和最小支撑，并保留原 source branch 作为未改写证据。

分类：`ACCEPTED_RAW`、`ACCEPTED_PRODUCT_P0`、`REQUIRED_SUPPORT`、`EXPERIMENTAL_SKU`、`INVESTIGATION_ONLY`。

## 2. Android production hunks

| File / Hunk | Classification | Included | Reason | Acceptance Evidence |
|---|---|---:|---|---|
| `collector/CollectorContract.kt`：`RawResult.sources`、`RawSource` | ACCEPTED_RAW | Yes | Raw evidence 的平台边界数据结构；不触发交互 | Raw targeted、Raw replay JVM |
| `collector/PddCollector.kt`：SEARCH/DETAIL/SHOP/PROMOTION/MEDIA/EMBEDDED/OTHER source 构造 | ACCEPTED_RAW | Yes | 正常详情已有观察形成受控 Raw sources | Raw replay JVM、server raw tests |
| `collector/PddCollector.kt`：`openAndReadSkuPrices()`、`SKU_PANEL` 自动 source | EXPERIMENTAL_SKU | No | 会进入购买选择面板；专项仍未 Accepted | negative JVM gate |
| `collector/PddCollector.kt`：默认步骤固定为 `params/shop_sales/human` | REQUIRED_SUPPORT | Yes | 明确切断正常详情到 SKU runtime 的调用边 | negative JVM gate |
| `data/Entities.kt`：parser version `pdd-android-2` | ACCEPTED_PRODUCT_P0 | Yes | 标题/参数边界修正可追溯版本 | DetailReader tests |
| `data/OutboxPayload.kt`：唯一 product mapper、Raw sanitization/manifest payload | ACCEPTED_RAW + ACCEPTED_PRODUCT_P0 | Yes | Raw 上传与 Canonical 字段共用 durable mapper | Outbox raw tests |
| `engine/TaskEngine.kt`：capture id、`raw.sources` 进入 durable outbox | ACCEPTED_RAW | Yes | Raw 必须随已确认 product event 可靠投递 | Raw replay/outbox tests |
| `engine/TaskEngine.kt`：普通首个 canonical item binding | REQUIRED_SUPPORT | Yes | 保持 product receipt 与 TaskItem 的既有完成语义 | Phase 2/full regression |
| `export/CsvExporter.kt`：canonical title/name/spec 输出 | ACCEPTED_PRODUCT_P0 | Yes | 导出与统一字段语义一致 | Product P0 tests |
| `net/ApiClient.kt`：legacy 上传委托 `OutboxPayload.product()` | ACCEPTED_PRODUCT_P0 | Yes | 消除第二套字段 mapper | Product P0/Android full |
| `parser/DetailReader.kt`：完整标题、参数 label 边界、manufacturer/spec 修正 | ACCEPTED_PRODUCT_P0 | Yes | Golden Sample 与 Canonical 语义必需 | DetailReader/P0 tests |
| `parser/DetailReader.kt`：历史 SKU text 兼容读取、空 sku id 不伪造 | ACCEPTED_PRODUCT_P0 | Yes | 读取历史 SKU 不启用采集交互 | DetailReader tests |
| `parser/ProductQualityGate.kt`：空 SKU array 为 missing warning | REQUIRED_SUPPORT | Yes | 空集合不伪装为已观察 SKU | Raw/Product quality tests |
| `engine/PddActions.kt`：virtual-list pagination / unseen card selection | REQUIRED_SUPPORT | Yes | 1.0.75 已验收非 SKU 生命周期能力；恢复确定性前向翻页和去重 | Backlog 1.0.75、`PddPaginationTest` |
| `engine/PddActions.kt`：SKU_PANEL、dynamic dimension、combination hunks | EXPERIMENTAL_SKU | No | 不引入 13b Generic SKU runtime | behavior JVM gate + auxiliary source scan |
| `data/Dao.kt`：legacy finish requeue、cross-attempt product query | REQUIRED_SUPPORT | Yes | 1.0.73～1.0.75 已验收恢复/跨 Attempt receipt 行为 | `LegacyFinishRecoveryTest`、`JobRecoveryPolicyTest` |
| `net/AgentCoordinator.kt`：engine retry、legacy finish、checkpoint direct finish、cross-attempt receipt、retry_wait reacquire | REQUIRED_SUPPORT | Yes | 已有真机 E2E/Backlog 证据，Split 误排除 | recovery/pagination/legacy finish JVM tests |
| `app/build.gradle.kts`：1.0.82 version bump | INVESTIGATION_ONLY | No | 对应真机 Generic SKU 调查制品版本 | 原 13b branch 保留证据 |

## 3. Server/Web production hunks

| File / Hunk | Classification | Included | Reason | Acceptance Evidence |
|---|---|---:|---|---|
| `server/raw_capture.py` | ACCEPTED_RAW | Yes | validate、sanitize、SHA-256、manifest、persistence、replay reference | `tests.test_raw_capture` |
| `server/routers/products.py`：Raw persistence + Canonical detail/edit/update | ACCEPTED_RAW + ACCEPTED_PRODUCT_P0 | Yes | Product upload transaction 与只读/编辑 DTO 的权威入口 | Raw/P0 tests、Oracle gate |
| `server/schemas.py`：`raw_capture`、Detail/Edit/Capture/Snapshot DTO | ACCEPTED_RAW + ACCEPTED_PRODUCT_P0 | Yes | API contract | Product P0 tests |
| `server/product_contract.py` | ACCEPTED_PRODUCT_P0 | Yes | 五种价格与 stable editable fields 唯一语义 | Product P0 tests |
| `server/product_read_model.py` | ACCEPTED_PRODUCT_P0 | Yes | Legacy/strict Canonical Read Model | Product P0 + Golden Sample |
| `server/routers/reports.py`：Effective Price | ACCEPTED_PRODUCT_P0 | Yes | Report 不建立第二套价格优先级 | Product P0 tests |
| `server/data_quality.py`：空 SKU collection 为未观察 | REQUIRED_SUPPORT | Yes | Quality 与 Android 空值语义一致 | Raw/data-quality tests |
| `server/job_service.py`：普通 item/canonical receipt 与 `NEXT_RUN_AT` hunks | REQUIRED_SUPPORT | Yes | 普通 TaskItem canonical binding 与 Oracle NOT NULL 兼容已验收 | Phase 2、Backlog、job service tests |
| `server/job_reconciliation.py`：Oracle alias/NEXT_RUN_AT/tenant event hunks | REQUIRED_SUPPORT | Yes | 修复真实 Oracle duplicate column alias、NOT NULL compatibility 与 reconciliation event tenant identity | static compatibility ×4、real Oracle integration ×5、Oracle gate |
| `server/routers/tasks.py`：tenant pull 与 late cancel ACK hunks | REQUIRED_SUPPORT | Yes | Phase 5.5 租户边界及取消后 durable outbox 释放已验收 | tenant pull、late cancel tests |
| `web/ProductList.vue`：Canonical fields + Edit DTO | ACCEPTED_PRODUCT_P0 | Yes | Library 编辑不复制列表动态事实 | Web build、P0 contract |
| `web/TaskDetail.vue`：Capture Edit DTO | ACCEPTED_PRODUCT_P0 | Yes | Capture 编辑与 Library 使用同一 stable policy | Web build、P0 contract |

## 4. Tests, tools and docs

| File / Hunk | Classification | Included | Reason | Acceptance Evidence |
|---|---|---:|---|---|
| `.gitignore`：`pdd_system.db` | REQUIRED_SUPPORT | Yes | 本地数据库不得进入基线 | safety scan |
| `OutboxPayloadRawCaptureTest.kt`、`RawCaptureReplayTest.kt` | ACCEPTED_RAW | Yes | Raw sanitization/manifest/offline replay | JVM targeted |
| `DetailReaderTest.kt`、`CollectorRegistryTest.kt` updates | ACCEPTED_PRODUCT_P0 | Yes | parser v2 与 Canonical parser compatibility | JVM targeted/full |
| `AcceptedBaselineNoSkuRuntimeTest.kt` | REQUIRED_SUPPORT | Yes | 新负向 gate：默认路径不调用 SKU runtime，Generic runtime 不存在 | JVM targeted/full |
| `tests/test_raw_capture.py` | ACCEPTED_RAW | Yes | server Raw persistence/hash/replay | Python targeted/full |
| `tests/test_product_consistency_p0.py` | ACCEPTED_PRODUCT_P0 | Yes | DTO、价格、immutable policy | Python targeted/full |
| `scripts/raw_capture_replay.py` | ACCEPTED_RAW | Yes | offline replay only | Raw targeted |
| `scripts/product_consistency_p0.py` | ACCEPTED_PRODUCT_P0 | Yes | 实际 Oracle Golden Sample read-only gate | Golden Sample |
| `docs/decisions/2026-08-20-product-field-semantics-p0.md` | ACCEPTED_PRODUCT_P0 | Yes | 正式 Accepted ADR | ADR status Accepted |
| `docs/architecture.md` Raw/Canonical sections | ACCEPTED_RAW + ACCEPTED_PRODUCT_P0 | Yes | 描述实际 split 架构与 SKU runtime exclusion | Sol review |
| `docs/backlog.md` split record | REQUIRED_SUPPORT | Yes | 当前任务边界和排除项 | 本 manifest |
| Field Observation / Generic SKU ADR | EXPERIMENTAL_SKU | No | Proposed/验证冻结，不是 Accepted | source ADR status |
| `schema_discovery.py`、`sku_panel_discovery.py`、`generic_sku_validation.py` | INVESTIGATION_ONLY | No | 专项调查工具，不进入 accepted baseline | 原 13b branch 保留 |
| schema/generic/SKU discovery tests | INVESTIGATION_ONLY | No | 验证未验收调查工具 | 原 13b branch 保留 |
| `PddActionsSkuContractTest.kt` | EXPERIMENTAL_SKU | No | 依赖未纳入的 13b Generic SKU runtime | behavior gate replaces Generic SKU runtime assertion |
| `PddPaginationTest.kt` | REQUIRED_SUPPORT | Yes | virtual list 前向翻页与 unseen card 选择 | 2 JVM tests |
| `LegacyFinishRecoveryTest.kt` | REQUIRED_SUPPORT | Yes | late cancel requeue 与 JSON null target compatibility | 2 JVM tests |
| `JobRecoveryPolicyTest.kt` 新增 recovery tests | REQUIRED_SUPPORT | Yes | cross-attempt receipt、engine retry、checkpoint direct completion | 3 JVM tests |
| Oracle compatibility / canonical receipt / tenant pull / late cancel tests | REQUIRED_SUPPORT | Yes | 对应恢复的 Accepted lifecycle 生产语义 | Python 非 SKU 7 tests |
| `2026-08-24-raw-capture-identity-immutability.md` | ACCEPTED_RAW | Yes | 冻结 Raw tenant identity、strict idempotency 与 Derived 不可变合同 | Raw behavior tests |

## 5. Explicit exclusions

- Generic SKU runtime contract；
- 默认 SKU_PANEL interaction、购买/拼成入口点击、combination traversal；
- Schema Discovery 生产依赖和 investigation scripts；
- 正式 ProductAttribute/SKU/SkuSnapshot Schema 与 migration；
- P1、Phase 6B。

保留 `RawSource(type="SKU_PANEL")` 的通用表达能力和历史 SKU JSON 读取，不等于启用采集交互。

## 6. Independent Review Corrections

| Reviewer Finding | Status | Corrected Classification | Restored / Fixed Files and Hunks | Acceptance Evidence | Tests |
|---|---|---|---|---|---|
| 1：Accepted 非 SKU 生命周期能力被误排除 | RESOLVED | `REQUIRED_SUPPORT / No` → `REQUIRED_SUPPORT / Yes` | `AgentCoordinator.kt`、`Dao.kt`、`PddActions.kt` pagination；`job_service.py`、`job_reconciliation.py`、`routers/tasks.py` | Backlog 1.0.73～1.0.75、Phase 2/5.5/6A 既有验收与 source `13b4301` | lifecycle/recovery targeted、full、isolated Oracle |
| 1A：Accepted 非 SKU 测试数量下降 | RESOLVED | 非 SKU coverage 恢复；Generic SKU tests 继续排除 | Python reconciliation ×4、canonical receipt ×1、tenant pull ×1、late cancel ×1；Android pagination ×2、legacy finish ×2、recovery ×3 | 每个测试均对应上一行恢复的生产语义 | Python/Android targeted + full |
| 2：Raw resanitize 原地覆盖 | RESOLVED | `ACCEPTED_RAW` 不变量强化 | `server/raw_capture.py` Derived/Resanitized version；replay 显式 original/derived | Accepted Raw evidence 需要可审计、可重放、不可变 | original bytes/hash/manifest 不变 + derived replay |
| 3：capture_id 未租户绑定且弱幂等 | RESOLVED | `ACCEPTED_RAW` 身份合同冻结 | Tenant/Workspace 路径、identity/content hashes、`RAW_CAPTURE_CONFLICT`、Accepted ADR | Enterprise/Workspace 隔离及 Raw provenance 不变量 | retry/conflict/cross-tenant/cross-workspace/product/attempt/device/content |
| 4：no-SKU 核心门禁仅做源码扫描 | RESOLVED | `REQUIRED_SUPPORT` 行为门禁 | `PddDetailPorts.kt` Spy/Fake seam；TaskEngine → Registry → PDD detail 实际调用路径 | Generic SKU 始终 `NOT ACCEPTED` | purchase/panel/combination=0，SKU_PANEL=0，DETAIL/parse/legacy read 正常；源码扫描仅辅助 |
| 5：绝对路径泄露 | RESOLVED | `ACCEPTED_RAW` API 边界修复 | `routers/products.py` opaque evidence/manifest refs；旧 receipt 输出清洗；verification 使用 repo-relative 路径 | 物理存储路径不是业务 identity | API/receipt/media ping + changed-scope absolute-path scan |
| 6：通用 RawSource 带 PDD schema 默认值 | RESOLVED | 平台中立 Contract + PDD 显式 Adapter provenance | `CollectorContract.kt` nullable default；`PddCollector.kt` 显式 `pdd-a11y-v1` | 防止未来 Adapter 继承错误 provenance | generic default null + PDD detail sources explicit |
| 7：41 项 strict Oracle 未执行恢复后的 reconciliation compatibility | RESOLVED | 静态检查继续作为 `STATIC COMPAT CHECK`；另增 `REAL ORACLE INTEGRATION` | `tests/test_job_reconciliation_oracle_integration.py`、`scripts/test-baseline.ps1`、`server/job_reconciliation.py` tenant event 最小修复 | 第二次独立 Review 指出的唯一 merge-blocking P1；旧 41/41 不再被描述为该路径的真实 Oracle 证据 | 5 项真实 Oracle 数据/连接/生产方法测试进入 strict gate；旧 41 + 新 5 = 46 |
| 8：Review verification artifact 含机器绝对路径 | RESOLVED | 历史删除证据保留语义并脱敏 | `BASELINE-REVIEW-FIX-001-verification/DIFF_FILE.patch` 使用 `<REPO_ROOT>` / `<GIT_BIN>`；verification 修正分类 | 该 finding 为 artifact 历史证据，不是 runtime/API 泄漏 | machine-specific path=0；negative test/ADR sentinel >0；runtime exposure=0 |
| 9：`mark_confirmed_result_success` 的真实 Oracle fixture 缺少真实 Attempt、Checkpoint→Attempt、canonical Product binding 与 Task aggregate | RESOLVED | `REQUIRED_SUPPORT` 生命周期恢复证据补全；完整 fixture 暴露并关闭最小生产缺口 | `tests/test_job_reconciliation_oracle_integration.py` 使用真实 acquire/start Attempt #1 和生产 `checkpoint()`；`server/job_reconciliation.py` 从 Checkpoint 恢复历史 Attempt、校验 receipt/product/tenant、绑定 TaskItem 并调用权威聚合 | 第三次 Review 指出的最后一个 merge-blocking P1；Attempt 保持既有 `success` 不可变终态，不创建新 Attempt | 初始 test-only 运行 `FAIL`（`AssertionError: 477 != None`）；最小修复后 targeted 1/1、模块 5/5、strict Oracle 46/46 PASS；二次真实 Oracle 调用无重复对象/计数 |

Generic SKU 相关 `GenericSkuContract`、购买/拼成入口自动交互、SKU Panel 自动打开和 combination traversal 未随 lifecycle 修复恢复；`PddActionsSkuContractTest.kt` 仍排除。Legacy SKU JSON/text 兼容读取及 `SKU_PANEL` 类型表达能力仅用于已存在数据，不会激活默认运行时。

## 7. Verification record

| Gate | Exact command / input | Literal result | Exit | Status |
|---|---|---|---:|---|
| Lifecycle/reconciliation Python targeted | `python -m unittest -v tests.test_job_reconciliation_oracle_compat`；`tests.test_job_service`；`tests.test_phase55_enterprise_hardening`；`tests.test_task_state_r1` | `Ran 4 tests ... OK`；`Ran 10 tests ... OK (skipped=2)`；`Ran 6 tests ... OK`；`Ran 15 tests ... OK` | 0 | PASS |
| Phase 6A Python targeted | `python -m unittest -v tests.test_phase6a_collectors` | `Ran 4 tests ... OK` | 0 | PASS |
| Raw immutability/identity targeted | `python -m unittest -v tests.test_raw_capture` | `Ran 8 tests in 0.250s ... OK` | 0 | PASS |
| Product P0 Python targeted | `python -m unittest -v tests.test_product_consistency_p0` | `Ran 5 tests ... OK` | 0 | PASS |
| Android behavior/lifecycle targeted | `gradlew testDebugUnitTest --no-daemon` + 5 class filters | `BUILD SUCCESSFUL in 8s`; 18 tests, 0 failures, 0 skipped | 0 | PASS |
| Confirmed-result lifecycle targeted | `python -m unittest -v tests.test_job_reconciliation_oracle_integration.OracleReconciliationIntegrationTest.test_mark_confirmed_result_success_completes_real_lifecycle_and_is_idempotent`；输入：隔离可写 Oracle test schema、全部 opt-in flags=1 | `Ran 1 test in 4.583s ... OK`；Real Oracle=YES、Production Method=YES、Attempt=REAL、Checkpoint binding/canonical Product binding/Task aggregate/idempotency/tenant isolation=PASS | 0 | PASS |
| Reconciliation real Oracle module | `python -m unittest -v tests.test_job_reconciliation_oracle_integration`；输入：同上 | `Ran 5 tests in 20.846s ... OK`；skipped=0 | 0 | PASS |
| Reconciliation static/module targeted | `python -m unittest -v tests.test_job_reconciliation tests.test_job_reconciliation_oracle_compat` | `Ran 12 tests in 0.008s ... OK` | 0 | PASS |
| Python full | `python scripts/run_python_unit_tests.py` | `Ran 195 tests in 0.352s ... OK (skipped=23)` | 0 | PASS |
| Python strict | `scripts/test-baseline.ps1 -Suite python -Strict` | `Ran 195 tests in 0.351s ... OK (skipped=23)`；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Python compile | `python -m compileall -q server scripts tests` | no output | 0 | PASS |
| Android JVM strict | `scripts/test-baseline.ps1 -Suite android -Strict` | `BUILD SUCCESSFUL in 8s`; XML：70 tests, 0 failures, 0 errors, 1 skipped；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Web production strict | `scripts/test-baseline.ps1 -Suite web -Strict` | `1673 modules transformed`; `built in 563ms`；`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Oracle reconciliation static | `python -m unittest -v tests.test_job_reconciliation_oracle_compat` | `Ran 4 tests in 0.005s ... OK`；仅为 `STATIC COMPAT CHECK`，不计真实 Oracle integration | 0 | PASS |
| Oracle reconciliation real integration | strict gate 内执行 `tests/test_job_reconciliation_oracle_integration.py`；输入：既有隔离、可写、事务回滚 Oracle test schema | 5/5 PASS：`expired_leases`、`promote_due_retry`、`mark_confirmed_result_success`、`mark_job_dead`、`nonretryable fail / NEXT_RUN_AT`；skipped=0 | 0 | PASS |
| Oracle Phase 1～6A | `scripts/test-baseline.ps1 -Suite oracle -Strict`；输入：既有隔离 Oracle test schema、全部 opt-in flags=1 | 旧 count 41 + 真实 Oracle reconciliation cases 5 = `Ran 46 tests in 171.804s ... OK`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True`；Oracle suite skipped=0 | 0 | PASS |
| Golden Sample | `python scripts/product_consistency_p0.py` | product `985843042423`; `result=PASS`; 10 legacy SKU combinations; 8 media | 0 | PASS |
| Generic SKU negative | `AcceptedBaselineNoSkuRuntimeTest` + auxiliary production source scan | behavior tests 3/3 PASS；purchase/panel/combination=0；SKU_PANEL=0；DETAIL/parse/legacy SKU read PASS；Generic runtime names 0 | 0 | PASS |
| Security | changed-scope secret/raw/DB/artifact/large-file/absolute-path scan | no secret、Raw payload、DB、build artifact or changed file >1 MiB；current artifact/file machine-specific path=0；git diff 中 machine-specific path=5，全部是移除旧路径的 historical deleted lines；其他 absolute-path matches 仅为 negative test/ADR sentinel；runtime/API exposure=0 | 0 | PASS |
| Diff | `git diff --check 246f181..HEAD`（提交前等价检查工作树） | no whitespace errors | 0 | PASS |

测试数量解释：Python `13b4301` 191 - 实验 Schema/Generic SKU 6 = Accepted 185；原 Split 误排除 7 后为 178；第一次 Review 修复恢复 7 并新增 Raw review tests 5 得 190；本次再增 5 个 opt-in 真实 Oracle reconciliation cases，full discovery 为 195，strict Oracle 实际执行它们时不 skip。Android `13b4301` 70 - Generic SKU tests 3 = Accepted 67；加 Split 专用 no-SKU gate 2，误排除 7 后为 62；恢复 7 且行为 gate 从 2 扩为 3，最终 70。没有为了数量恢复 Generic SKU 测试。

Python full 的 23 个 skip（含 5 个 opt-in reconciliation integration）和 Android 的 1 个 skip 均未计为 Oracle/真机 PASS；隔离 Oracle strict gate 已另行实际执行 46 项并通过，无 skip。

本次第三次 Review 修复可复现修改/回滚制品：[`MODIFIED_FILE.py`](BASELINE-REVIEW-FIX-003-verification/MODIFIED_FILE.py)、[`DIFF_FILE.patch`](BASELINE-REVIEW-FIX-003-verification/DIFF_FILE.patch)、[`VERIFICATION.txt`](BASELINE-REVIEW-FIX-003-verification/VERIFICATION.txt)、[`ROLLBACK.sh`](BASELINE-REVIEW-FIX-003-verification/ROLLBACK.sh)。此前 Review 与原 Split 制品继续保留，并已移除验证记录中的用户机器绝对路径。

## 8. Sol Review

1. Phase 6A commit 完整保留；targeted 与 Oracle compatibility 通过。
2. RawSource、sanitization、manifest、server persistence、offline replay 和 durable upload 链完整。
3. Product P0 的 Canonical fields、五价、Read/Edit DTO、immutable policy、Web 编辑边界与 Golden Sample 完整。
4. 默认 `PddDetailCollector` 不引用 `openAndReadSkuPrices()`，不生成主动 `SKU_PANEL` source；13b Generic runtime 名称和 combination traversal 未进入分支。
5. Collector Contract 仅增加 Raw sources，不改变 Registry/Capability/Quality 完成语义。
6. 恢复 7 项 Python 与 7 项 Android Accepted 非 SKU coverage；no-SKU 核心证明升级为行为测试，源码扫描仅作辅助。
7. Original Raw、identity/content hash 和 Manifest 在 resanitize 前后逐字节不变；Derived 版本可独立验证和 replay。
8. 逐项复核 13b production hunks；恢复仅覆盖既有 Accepted lifecycle，不包含 Generic SKU、P1 或 Phase 6B。
9. 第二次 Review 指出的 reconciliation Oracle evidence 缺口由 5 项真实 integration cases 关闭；旧 41 项结果只代表当时集合，当前 strict gate 为 46/46。
10. 第三次 Review 证明其中 `mark_confirmed_result_success` fixture 仍不完整；本次用真实 Attempt #1、绑定该 Attempt 的生产 Checkpoint、confirmed Receipt/Product、TaskItem canonical binding、Task aggregate、Tenant A/B 和二次调用，完成最后一个定向门禁；完整 fixture 首先失败并暴露生产恢复遗漏，最小修复后全部通过。

## 9. Rollback

- 分支整体回滚：删除未 merge 的 `codex/accepted-business-baseline` 分支，不影响 source branches；
- commit 回滚：按本分支新增 commit 逆序 `git revert`；
- Oracle tests 使用专用测试 schema 并自行清理标记数据；本 Task 无正式 SKU migration、无生产数据修改。
