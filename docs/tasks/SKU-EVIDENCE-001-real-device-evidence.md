# SKU-EVIDENCE-001 Real-device Evidence Matrix

- **Evidence date**：2026-08-25
- **Approved baseline**：`main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- **Device**：M2007J3SC / Android 10 / collector `1.0.81`
- **Tasks**：`1567`（受控提前停止，3 个结果）、`1568`（4/4 job success）
- **Result**：`SCHEMA REVIEW CANDIDATE — MODEL ASSUMPTIONS REQUIRE CHANGES`

本文件只提交脱敏摘要、identity/hash 和可复现结论。Original Raw 保存在隔离证据目录，不提交真实页面内容或账号信息；derived replay 和矩阵与 Original Raw 分离。

## 1. Execution boundary and terminal state

- Task `1568` 聚合终态为 `succeeded`，`SUCCESS_COUNT=4`、`FAIL_COUNT=0`，四个 Job 均为 `success`、`ACTIVE_ATTEMPT_ID=NULL`、lease 已释放。
- 设备 `6` 在结束后为 `online / idle`，`CURRENT_TASK_ID`、`ACTIVE_JOB_ID`、`ACTIVE_ATTEMPT_ID` 均为空。
- Task `1568` 没有 anomaly/error event；没有继续创建采样任务。
- 7/7 capture 的 guard 均为 `order_confirmation_clicked=false`、`order_submitted=false`、`payment_started=false`。

## 2. Raw identity and immutable hashes

| Raw | Capture | Product identity | Identity SHA-256 | Content SHA-256 | SKU_PANEL SHA-256 |
|---:|---|---:|---|---|---|
| 515 | `cap-1567-4c1b30d2-a71b-489e-961c-ee1735c4ecec` | `920205213506` | `668c312359884b23e632d46d15bce24cd63c2c01871d601586c96d56f3b9817e` | `6cc3448122ae0e7a68d6ec164502ef7a65c22dd75db42b252e8fbd6d489fa65f` | `233a65ef8b3e094c01f910a21353343ae46afd6c2bc7c0f9e345de7b5cd1eb51` |
| 516 | `cap-1567-3437eb1e-5471-45e6-894c-85726505891f` | `806103671575` | `93d0e01b8bc20a2ce66d3dce05e65b55c8f0f5b4d7a6ef6f638fc20bffc0d578` | `6c7951b9904857ab4d86b2ddceb76af48a58403edd4895e66159a3272ec4721c` | `680aff1e3a9971009de9b8ba2f15ef5377b1acafe1c5738ab55b8cd7e7364d15` |
| 517 | `cap-1567-c2d9d9e8-aa91-4d6c-a953-0adb04d7991b` | `826879938468` | `3f8c15680996966ab746bb3b4eed04c09042363e9082ea01501cd48decaab400` | `e7a9da8b49e1090ee733988cdf0ee531e2e5eff85d8ea025dbc74d8866a732fa` | `419ceb4c2ae0a9ff1fcedb45ee1befbef8b5d8a1ff236df4848b746041d0d178` |
| 518 | `cap-1568-85318453-6c3e-4ce5-850b-cc736f345e84` | `762257475043` | `6aeb1f2f6a9bf7a74da52b002e5b8a779581e6b7f21bf7458245226c02b6184c` | `74b63cc352094261e04637ef0274291e9b0de3b278023d8342cb58fe612ca369` | `1b6dea077ec8db9a2c229eb0297ddfd613f2b9fa7b164886a5b73526f4510980` |
| 519 | `cap-1568-d9a9b816-5885-4fb8-8f40-3778dc82f244` | `932558905084` | `df6506675bc2f84bdc59b0812827a32b427b1c97a3d061baaafe8e9ce5ac5227` | `5045d9dc3c26a3f71d2ee69325d8e9efe5db4011bddeb629f38030abe7ea8754` | `80ecd92b2b876f0c3b95446ebadeee06ebe6665afe244926dc11fe06523070a8` |
| 520 | `cap-1568-7c6eee66-bfcf-4776-bd7c-4b39b08c7e3b` | `940415734455` | `bae90064f9533827da809aa080000ac579ec78cd4e03f699640667db82d0de42` | `3240c3d850dbf3291ce66d4b92b12a54923f1daa2ae0ac2400634d3191021cb1` | `06748724985b0e804757d5f32595b89b4b71c1dfaed81be7fafdbdc864f83e74` |
| 521 | `cap-1568-2483d11d-fcd7-4224-9253-8d26bde8038d` | `959729371509` | `eff2219dbe4570c67eb17b294261588ac6a83df9af17c26ff642358f1ef6ddfc` | `da066423861bd6bee6c8191b03695ce2d62d26bd2d58904a7f8b69b4d40b3852` | `0ecac449fd4e29af0e8adbafa55f880c058c6bc973f1df154883acbd341482b6` |

`verify_capture` 对 7/7 manifest、source size/hash、product upload JSON 和敏感标记检查均通过。

## 3. Observation matrix

| Capture suffix | Dimensions observed | Options | Combination observations | Disabled | SKU media | Direct platform SKU ID | Decision status |
|---|---:|---:|---:|---|---|---|---|
| `3437eb1e` | 2 | 8 | 12 available with price | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | usable two-dimensional price evidence |
| `4c1b30d2` | 2 | 10 | 21 reported false, all price missing | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `OBSERVATION_NOT_CONFIRMED` |
| `c2d9d9e8` | 2 | 9 | 20 reported false, all price missing | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `OBSERVATION_NOT_CONFIRMED` |
| `2483d11d` | 1 inventoried, another default selection visible | 8 | prices observed under an unmodeled/default selection | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | dimension inventory incomplete; combination attribution `NOT_CONFIRMED` |
| `7c6eee66` | 1 | 7 | one false while page still requests shoe size | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | incomplete selection, not invalid combination |
| `85318453` | 2 | 7 | 6 available with price | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | usable two-dimensional price evidence |
| `d9a9b816` | 1 | 7 sampled | page still requires size | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | partial dimension observation |

### Required factual classifications

- **Three or more dimensions**：`NOT_OBSERVED`。7 个样本最多只形成两个已确认维度，不能从标题或文本拼接出第三维。
- **Disabled option**：`NOT_OBSERVED`。带文本的 `enabled=false` panel node 为 0。
- **Unavailable / invalid combination**：`NOT_CONFIRMED`。`available=false` 样本同时存在选择未生效、必要维度未选或价格读取失败，不能升级为平台明确拒绝。
- **SKU image / option association**：`NOT_OBSERVED`。所有 combination 的 `media_ref` 均为空。
- **Direct platform SKU ID**：`NOT_OBSERVED`。所有 combination 的 `platform_sku_id` 均为空；不得推导或伪造。
- **Raw 521 / `2483d11d`**：首次 observation 没有 confirmed `selected_text`，后续页面状态包含未进入 `dimension_inventory` 的默认选择；价格只能证明页面曾显示该价格，不能归因于已建模的单维组合。

## 4. Raw → Replay → DTO

- Server replay：7/7 `mode=dry-run-analysis`、`network_access=false`、hash/JSON verification PASS；Product identity 与 manifest 一致；QualityGate 均接受正常商品事实。
- Android replay：显式设置 7 个 `PDD_CAPTURE_DIRS`，`RawCaptureReplayTest` 实际执行 `1` test、`0` failure、`0` error、`0` skipped；输出 7 个 DTO，`item_id` 与 manifest identity 全部一致，`parser_version=pdd-android-2`。
- Android Accepted 默认路径仍不把调查性 `SKU_PANEL` 自动交互作为 runtime 能力；Android DTO 因缺少默认路径认可的完整字段表现为 `parse_status=partial / quality_status=warning`。这是真实结果，不冒充正式 Generic SKU runtime PASS。

## 5. Model finding and Schema ADR Review recommendation

真实证据推翻了“Raw 中 `available=false` 可以直接等价为 invalid combination”的假设。Schema Proposal Review 必须至少：

1. 将交互请求、选择确认和业务 availability 分开建模；只有页面已选状态匹配、必要维度完整且存在明确拒绝证据时，才允许 `OBSERVED_UNAVAILABLE`；
2. 使用 `OBSERVED_AVAILABLE / OBSERVED_UNAVAILABLE / OBSERVATION_NOT_CONFIRMED / NOT_OBSERVED`，不得把采集失败写成库存或无效组合；
3. `platform_sku_id`、`media_ref` 和 disabled state 均必须 nullable/observation-aware；
4. SKU identity 不得由标题、商品参数、主商品价格或本次选项文本单独推导；
5. 在更多证据与单独 Product Owner 决策前，不实施正式 Schema/migration，不启用 Generic SKU runtime。

因此本 Task 已达到“证据推翻当前模型假设”的 Stop Condition，可以提交独立 Schema ADR Review；它不等于 P1 或 Schema 实施已获准。

## 6. Regression summary

| Gate | Literal result | Status |
|---|---|---|
| Python compile | exit `0` | PASS |
| Python unit | `Ran 195 tests ... OK (skipped=23)`；23 个为未启用 Oracle 的离线 skip | PASS |
| Android full JVM | `BUILD SUCCESSFUL`; 70 tests, 0 failure/error, 1 expected no-env replay skip | PASS |
| Android explicit real-Raw replay | 7 DTO; 1 test, 0 failure/error/skip | PASS |
| Web production build | Node `22.18.0`; `✓ built in 6.49s` | PASS |
| Oracle strict Phase 1～6A | `Ran 46 tests in 197.142s` / `OK` | PASS |
| Product Golden Sample / Legacy read | `result: PASS`; legacy provenance remains explicitly unavailable | PASS |
