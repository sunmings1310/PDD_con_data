# BASELINE-SPLIT-001：Accepted Business Baseline Split Manifest

- Status：ACCEPTED / READY FOR DRAFT PR
- Date：2026-08-23
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
| `engine/PddActions.kt`：13b pagination、SKU_PANEL、dynamic dimension、combination hunks | EXPERIMENTAL_SKU | No | 保留 Phase 6A 的 90b 实现；不引入 13b Generic SKU runtime | source scan、negative JVM gate |
| `data/Dao.kt`：legacy finish requeue、cross-attempt product query | REQUIRED_SUPPORT | No | 属于另一个生命周期恢复变更，不是本次 Raw/P0 最小依赖 | 原 13b branch 保留证据 |
| `net/AgentCoordinator.kt`：engine retry、legacy finish、checkpoint direct finish、cross-attempt receipt | REQUIRED_SUPPORT | No | 与本次四项能力无直接依赖，避免夹带生命周期行为变化 | 原 13b branch 保留证据 |
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
| `server/job_service.py`：普通 item/canonical receipt 与 `NEXT_RUN_AT` hunks | REQUIRED_SUPPORT | No | 不属于本次最小 Product/Raw split；90b 的已验收完成语义保持不变 | Phase 2/full regression |
| `server/job_reconciliation.py`：Oracle alias/NEXT_RUN_AT hunks | REQUIRED_SUPPORT | No | Oracle 兼容修复不由本 Task扩 scope | Phase 6A 90b Oracle baseline |
| `server/routers/tasks.py`：tenant pull 与 late cancel ACK hunks | REQUIRED_SUPPORT | No | 不夹带 Task 生命周期/租户路由行为变化 | 原 13b branch 保留证据 |
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
| `PddActionsSkuContractTest.kt`、`PddPaginationTest.kt` | EXPERIMENTAL_SKU / INVESTIGATION_ONLY | No | 依赖未纳入的 13b runtime/pagination hunks | negative gate replaces SKU runtime assertion |
| Job recovery、legacy finish、Oracle compatibility test hunks | REQUIRED_SUPPORT | No | 对应未纳入的生命周期/Oracle兼容 hunk，不降低既有断言 | 90b/full regression retained |

## 5. Explicit exclusions

- Generic SKU runtime contract；
- 默认 SKU_PANEL interaction、购买/拼成入口点击、combination traversal；
- Schema Discovery 生产依赖和 investigation scripts；
- 正式 ProductAttribute/SKU/SkuSnapshot Schema 与 migration；
- P1、Phase 6B。

保留 `RawSource(type="SKU_PANEL")` 的通用表达能力和历史 SKU JSON 读取，不等于启用采集交互。

## 6. Verification record

| Gate | Exact command / input | Literal result | Exit | Status |
|---|---|---|---:|---|
| Phase 6A Python targeted | `python -m unittest -v tests.test_phase6a_collectors` | `Ran 4 tests ... OK` | 0 | PASS |
| Raw + Product P0 Python targeted | `python -m unittest -v tests.test_raw_capture tests.test_product_consistency_p0` | `Ran 8 tests ... OK` | 0 | PASS |
| Android targeted | Collector/Raw/Detail/negative gate filters | `BUILD SUCCESSFUL in 35s` | 0 | PASS |
| Python full | `scripts/test-baseline.ps1 -Suite python -Strict` | `Ran 178 tests ... OK (skipped=18)` | 0 | PASS |
| Python compile | `python -m compileall -q server scripts tests` | no output | 0 | PASS |
| Android JVM full | `testDebugUnitTest --no-daemon` | `BUILD SUCCESSFUL in 13s`; 62 tests, 0 failures, 1 skipped | 0 | PASS |
| Web production | `npm ci && npm run build` | `1673 modules transformed`; built in 4.64s | 0 | PASS |
| Oracle Phase 1～6A | strict isolated Oracle gate | `Ran 40 tests in 116.520s ... OK`; `PASS=1 FAIL=0 BLOCKED=0` | 0 | PASS |
| Golden Sample | `python scripts/product_consistency_p0.py` | product `985843042423`; `result=PASS`; 10 legacy SKU combinations; 8 media | 0 | PASS |
| Generic SKU negative | `AcceptedBaselineNoSkuRuntimeTest` + production source scan | default detail has no SKU call/source; Generic runtime names absent; only unused 90b capability definition remains | 0 | PASS |
| Security | tracked-path/secret/DSN/absolute-path/large-file scan | 0 findings; no changed file >1 MiB | 0 | PASS |
| Diff | `git diff --check origin/main` | no whitespace errors | 0 | PASS |

Python 的 18 个 skip 和 Android 的 1 个 skip 均未计为 Oracle/真机 PASS；隔离 Oracle 已单独实际执行并通过。

可复现修改/回滚制品：[`MODIFIED_FILE.kt`](BASELINE-SPLIT-001-verification/MODIFIED_FILE.kt)、[`DIFF_FILE.patch`](BASELINE-SPLIT-001-verification/DIFF_FILE.patch)、[`VERIFICATION.txt`](BASELINE-SPLIT-001-verification/VERIFICATION.txt)、[`ROLLBACK.sh`](BASELINE-SPLIT-001-verification/ROLLBACK.sh)。

## 7. Sol Review

1. Phase 6A commit 完整保留；targeted 与 Oracle compatibility 通过。
2. RawSource、sanitization、manifest、server persistence、offline replay 和 durable upload 链完整。
3. Product P0 的 Canonical fields、五价、Read/Edit DTO、immutable policy、Web 编辑边界与 Golden Sample 完整。
4. 默认 `PddDetailCollector` 不引用 `openAndReadSkuPrices()`，不生成主动 `SKU_PANEL` source；13b Generic runtime 名称和 combination traversal 未进入分支。
5. Collector Contract 仅增加 Raw sources，不改变 Registry/Capability/Quality 完成语义。
6. 未删除或放宽既有测试断言；新增负向 gate。未纳入的实验测试随实验实现一起保留在 source branch。
7. 逐项复核 13b production hunks；没有发现 Accepted Raw/Product P0 的遗漏依赖。

## 8. Rollback

- 分支整体回滚：删除未 merge 的 `codex/accepted-business-baseline` 分支，不影响 source branches；
- commit 回滚：按本分支新增 commit 逆序 `git revert`；
- Oracle tests 使用专用测试 schema 并自行清理标记数据；本 Task 无正式 SKU migration、无生产数据修改。
