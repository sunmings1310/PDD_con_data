# SKU-EVIDENCE-001：补齐 Generic SKU Schema 决策证据

- **Task ID**：SKU-EVIDENCE-001
- **Title**：补齐 Generic SKU Schema 决策证据
- **Status**：REVIEW（Real-device Gate：PASS；Schema implementation：NOT APPROVED）
- **Approved base**：`main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- **Branch / worktree**：`codex/sku-evidence-001` / `D:\work\PDD_con_data_sku_evidence`
- **Product Owner approval**：2026-08-25，本 Task 仅批准真实证据补齐与 Schema Proposal Review 建议，不批准 Schema 实施、Generic SKU runtime、P1、P2 或 Phase 6B。

## Goal

补齐 Generic SKU Schema 决策所需的真实、可追溯、可重放证据，并给出可交给独立 Schema ADR Review 的结论；证据不足或推翻现有假设时明确记录，不以实现代替证据。

## Context

Accepted Business Baseline 已具备 Raw Capture、不可变 identity/hash/manifest、离线 Replay、Canonical Product Contract 和 `SKU_PANEL` Raw source 表达能力，但默认 PDD 路径不打开购买入口、不遍历组合。既有调查覆盖无 SKU、单维、双维及部分组合观察，仍缺三维以上、disabled/unavailable、SKU 图片稳定关联、平台直接 SKU ID 和当前批准测试版本真机回归。

## Scope

### Allowed

1. 补充三维及以上购买维度真实样本；
2. 补充 disabled/unavailable option 与无效 combination；
3. 验证 SKU 图片与选项/组合关联稳定性；
4. 查找平台直接 SKU ID；未观察到时记录 `NOT_OBSERVED`；
5. 使用既有 Raw Capture 保存打开前后证据、SHA-256、manifest 和 identity；
6. 执行当前批准测试版本真机回归；
7. 验证 Raw → Replay → DTO 一致性；
8. 执行 Phase 1～6A、Product Golden Sample、Legacy read 回归；
9. 输出证据矩阵和独立 Schema ADR Review 建议。

### Forbidden

- 创建正式 SKU/ProductAttribute Oracle 表或执行 migration；
- 启用默认 Generic SKU runtime，或修改普通 PDD 默认采集路径；
- 进入 P1、P2、Phase 6B 或第二平台；
- 用标题、商品参数或主商品价格推导 SKU；
- 伪造平台 SKU ID、库存、图片、选项或组合；
- 确认订单、提交订单、支付或越过购买安全边界；
- 删除、回填或清洗现有数据。

## Non-goals

- 不冻结正式 Oracle Schema；
- 不实现生产 Generic SKU Collector；
- 不改变 Product/Snapshot/SKU 产品语义；
- 不发布、不 merge、不清理历史证据分支。

## Dependencies

- Accepted Raw Capture 与 Product P0；
- 可用真机、合法测试账号、满足缺口的目标商品页面和人工监督；
- 隔离 Oracle 环境用于既有严格回归，不用于 Schema 变更；
- 原始证据与派生矩阵必须分离保存。

## Affected Modules

- `docs/tasks/SKU-EVIDENCE-001.md`
- `docs/backlog.md`
- 既有 Raw Capture / Replay 工具与脱敏证据目录（仅按批准步骤产生测试证据）
- 必要的离线证据矩阵、验证记录和 Schema Proposal 建议

## ADR

- 复用 `docs/decisions/2026-08-24-raw-capture-identity-immutability.md`；
- 本 Task 不接受正式 SKU Schema ADR。证据充分后只提交独立 ADR Review 建议，仍需 Product Owner 另行批准。

## Acceptance Criteria

- [x] 三维及以上购买维度有真实 Raw/manifest/identity 证据，或明确记录未取得原因（7 个样本均为 1～2 维，结论 `NOT_OBSERVED`）；
- [x] disabled/unavailable option 和无效 combination 有可重放证据（disabled `NOT_OBSERVED`；`available=false` 被证伪为不足以认定 invalid combination）；
- [x] SKU 图片关联有稳定性判断（7/7 `media_ref` 为空，结论 `NOT_OBSERVED`）；
- [x] 平台 SKU ID 明确为 `NOT_OBSERVED`；
- [x] 未触发确认订单、提交订单或支付；
- [x] Original Raw、hash、manifest 与 derived replay/矩阵分离且可核验；
- [x] Raw → Replay → DTO 身份一致性通过，并如实记录 Android DTO 的 partial/warning；
- [x] 当前批准测试版本真机 Gate 有实际结果；
- [x] Phase 1～6A、Product Golden Sample、Legacy read 回归有实际结果；
- [x] 输出证据充分性结论和独立 Schema ADR Review 建议；
- [ ] Independent Review 给出 `ACCEPT`、`CHANGES_REQUIRED` 或 `BLOCKED`。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `python -m unittest -v tests.test_collection_fixtures tests.test_raw_capture tests.test_product_consistency_p0` | Python 3.10 venv；dummy non-network Oracle config | fixture、Raw 与 Product P0 离线契约通过 | `Ran 19 tests ... OK` | 0 | PASS |
| Module | Gradle `testDebugUnitTest` filters：`AcceptedBaselineNoSkuRuntimeTest`、`RawCaptureReplayTest`、`DetailReaderTest` | JDK 17 / SDK 34；未设置 `PDD_CAPTURE_DIRS` | non-runtime/parser 通过；真实 Raw replay 不得伪 PASS | `BUILD SUCCESSFUL`; 14 passed, `RawCaptureReplayTest` 1 skipped | 0 | PASS + SKIPPED |
| Full regression | Python offline、Android JVM、Web build、Oracle strict 分层入口 | Python 3.10、JDK 17、Node 22.18、隔离 Oracle | Phase 1～6A 回归实际通过 | Python 195 OK；Android 70/0/0；Web build PASS；Oracle 46/46 OK | 0 | PASS |
| Golden / Legacy | `python scripts/product_consistency_p0.py` | 隔离 Oracle/批准的只读样本 | Canonical/Legacy 读取保持一致 | `result: PASS`；legacy provenance 仍明确 unavailable | 0 | PASS |

## Oracle Gate

- Required：Yes（仅执行既有 Phase 1～6A strict、Golden Sample、Legacy read 回归；本 Task 不变更 Schema）
- Reason：Schema Proposal 的兼容结论必须证明现有 Product/Raw/Legacy 行为不回归。
- Environment：隔离、可写、可清理 Oracle；Golden Sample 按既有批准只读入口。
- Command / result / exit：Phase 1～6A strict `Ran 46 tests in 197.142s`、`OK`、exit `0`；Product Golden Sample `result: PASS`、exit `0`。

## Real-device Gate

- Required：Yes
- Device/scenario：当前批准测试版本；三维以上、disabled/unavailable、图片关联、平台 SKU ID 观察；全程不得确认订单/提交订单/支付。
- Command or steps / result：Product Owner 已于 2026-08-25 明确批准；collector `1.0.81` 在受控真机完成 7 个 Raw，Task `1568` 为 4/4 success，设备已回到 online/idle。7/7 guard 确认未点击确认订单、未提交订单、未开始支付。结果与 hash 见证据矩阵。

## Rollback

- Code rollback：本 Task 当前只建立文档和派生证据；未 merge 分支可删除，已提交变更可按提交逆序 `git revert`。
- Configuration rollback：不修改生产配置；真机临时测试设置恢复到测试前状态。
- Data recovery：不执行 Schema、migration、回填或清洗；隔离 Oracle 测试数据按既有清理入口删除。
- Irreversible items：无；一旦步骤需要不可逆订单/支付动作立即停止。

## Human Decision Points

- 真机、真实账号、目标页面或人工验证开始前必须获得明确批准；
- 需要改变 Product/Snapshot/SKU 语义、扩大采样范围或启用 runtime 时停止；
- Schema/ migration、merge、release 必须另行批准。

## Stop Condition

满足任一条件即停止：

1. 证据足以提交独立 Schema ADR Review；
2. 证据推翻当前模型假设，记录反例；
3. 缺少真机、账号、目标页面或人工验证而 `BLOCKED`；
4. 需要越过确认订单、提交订单或支付边界；
5. 需要改变 Product/Snapshot/SKU 产品语义并转交 Product Owner；
6. 证据报告和回归完成；不得自动实施 Schema。

## Evidence

- Original evidence：Accepted baseline 没有 committed 真实 SKU_PANEL Raw；历史调查保留在 `13b4301`，不能当作 Accepted runtime。
- Derived artifacts：[`SKU-EVIDENCE-001-evidence-inventory.md`](SKU-EVIDENCE-001-evidence-inventory.md)、[`SKU-EVIDENCE-001-real-device-evidence.md`](SKU-EVIDENCE-001-real-device-evidence.md)、[`SKU-EVIDENCE-001-verification/VERIFICATION.txt`](SKU-EVIDENCE-001-verification/VERIFICATION.txt)。
- Review findings：真实证据推翻 `available=false == invalid combination` 的模型假设；三维、disabled、SKU media 和平台 SKU ID 均须按 `NOT_OBSERVED` 处理。等待最终 Independent Review。
- Commit / PR：Task 建立提交 `9f41036c7b9fb13b986baaae49a7583568ef46b7`；最终 fixed Head 待验证提交后记录。PR 未创建且未获准；Schema/migration/runtime/P1/P2/Phase 6B 均未开始。
