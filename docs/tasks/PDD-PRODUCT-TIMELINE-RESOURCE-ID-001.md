# PDD-PRODUCT-TIMELINE-RESOURCE-ID-001：修复商品时间线资源 ID 混用

- **Task ID**：PDD-PRODUCT-TIMELINE-RESOURCE-ID-001
- **Title**：修复 Product / Enterprise Product / Legacy Product ID 混用
- **Status**：REVIEW / ORACLE PASS

## Goal

租户内商品时间线统一使用 `enterprise_product_id` 作为外部资源 ID，使既有 Product 1182 对应的 Snapshot 1050 等历史快照恢复可见，同时保持跨企业与 Workspace 隔离。

## Context

- 固定基线：`main@80b3435558e67850c9cba4215ca81456721ef0db`。
- 已复现锚点：Task 4286、Legacy Product 1182、Master Product 600、Enterprise Product 588、Snapshot 1050。
- 当前 `ProductList.vue` 把 `master_product_id` 放入 `/products/:id/timeline`；租户 API 实际把该路由值按 `enterprise_product_id` 解析，导致 HTTP 200 + 空时间线。
- Accepted ADR `phase5-product-master-tenancy.md` 已规定：租户 API 不返回全局 identity 作为资源定位；资源定位使用 `enterprise_product_id`，并以 Enterprise + Workspace 约束读取 Snapshot。

## Scope

### Allowed

- 画清 Legacy Product、global master identity、Enterprise Product 的来源、转换和 Web/API 调用链。
- Product 列表/相关时间线入口返回并使用 `enterprise_product_id`。
- 将时间线 API/查询参数命名与 tenant resource 语义对齐；保留必要内部 master identity 转换。
- 修正 ProductList、Quarantine 等当前生产时间线入口及紧邻测试。
- 使用现有历史数据和隔离 Oracle fixture 验证可见性与隔离。

### Forbidden

- 删除、重建、回填或清理历史 Product/Snapshot 数据。
- Schema/migration。
- 保存幂等、媒体路径、health 脱敏、Generic SKU/P1 SKU/Phase 6B。
- merge、release；本授权不创建或推进任何 PR。

## Non-goals

- 不改变 Product/Snapshot 身份产品语义。
- 不为旧客户端开放全局 master ID 的跨租户查找 fallback。
- 不修改商品保存、采集或质量业务流程。

## Dependencies

- Accepted Phase 5 tenant-bound Product identity ADR。
- Accepted Product Read/Edit Contract 与 Web Result Visibility。
- `PDD-PRODUCT-CHANGE-BIND-HOTFIX-001` Draft PR 非依赖，不串接其分支。

## Affected Modules

- Server：`server/routers/products.py`、`server/routers/management.py`、`server/management_queries.py`。
- Web：`web/src/views/data/ProductList.vue`、`web/src/views/management/ProductTimeline.vue`、`web/src/views/management/QuarantineList.vue`。
- Tests：紧邻 Python/Web contract 与隔离 Oracle 测试。

## ADR

复用 Accepted [`../decisions/phase5-product-master-tenancy.md`](../decisions/phase5-product-master-tenancy.md)。本 Task 不新增第二套身份决策。

## Acceptance Criteria

- [x] tenant-facing 时间线资源 ID 唯一为 `enterprise_product_id`；global master ID 只在服务端内部转换。
- [x] Product 列表与 Quarantine 时间线入口不再传 `master_product_id`。
- [x] 以 1182 → 588 → 600 → 1050 契约 fixture 与真实 Oracle 路径证明历史 Snapshot 可从正确 tenant resource 读取。
- [x] 跨企业资源 ID 与不存在资源保持不可枚举的空结果语义；Workspace Snapshot 不串读。
- [x] 合法但没有 Snapshot 的 Enterprise Product 仍显示正确空时间线。
- [x] 无历史数据删除、重建或持久污染。
- [x] Targeted、Python full、Web build、Oracle strict、diff/sensitive/rollback 通过。
- [ ] Independent Review `ACCEPT`。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Baseline | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe scripts\run_python_unit_tests.py` + focused source trace | main fixed base | existing baseline remains green while wrong master ID path is reproduced | `Ran 249 tests`; `OK (skipped=31)`；ProductList→master ID、tenant query→enterprise ID 冲突已定位 | 0 | PASS / DEFECT REPRODUCED |
| Targeted | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe -m unittest tests.test_product_timeline_resource_id tests.test_phase4_management tests.test_web_result_visibility tests.test_phase5_tenancy tests.test_phase55_oracle` | 588 → 600 → 1050 contract fixture | correct Enterprise resource, tenant/workspace fences | `Ran 38 tests`; `OK (skipped=11)` | 0 | PASS；Oracle integration未计为PASS |
| Full regression | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe scripts\run_python_unit_tests.py` | offline repository suite | no regression | `Ran 252 tests`; `OK (skipped=32)` | 0 | PASS |
| Web build | `npm run build` | Node `v22.18.0` / npm `10.9.3` after `npm ci` | production build | `1683 modules transformed`; `built in 7.17s` | 0 | PASS |

## Oracle Gate

- Required：Yes。
- Reason：修改 Oracle tenant-bound Product/Snapshot 查询与真实历史读取契约。
- Local isolated environment identifier：沿用已批准专用测试 Oracle，秘密不进入日志或仓库。
- Fixed tested Head SHA：`63a62e53d0d0d83aa875f53df58648c98dd303f7`（代码 Head `643e5334880e9cc7d4f57c597e14c437613f90cd`）。
- Canonical command / test count / literal result / exit：在 T003 与应用 Oracle 环境均绑定同一获批隔离库且秘密不输出后，`powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict` → `Ran 54 tests in 337.001s`，`OK`，`[PASS] oracle-integration: exit=0`，`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True`。
- Four artifacts / rollback / persistent business changes：四制品和副本 rollback PASS；新增 fixture 清理核对 `SJZQ_PRODUCT_MASTER=0`、`SJZQ_RAW_COLLECTION=0`、`SJZQ_PRODUCT_SNAPSHOT=0`，`persistent_business_changes=false`。
- Hosted evidence validator：pending。
- Independent Reviewer provenance check：pending Re-review；首轮代码 Review 无 finding。

## Real-device Gate

- Required：No。
- Device/scenario：管理端与服务端只读资源定位修复，不改变 Android/采集路径。

## Rollback

- Code rollback：回退本 Task 单一提交范围。
- Configuration rollback：无配置变更。
- Data recovery：无业务数据迁移；Oracle fixture 必须逐表清理。
- Irreversible items：无。

## Human Decision Points

- merge/release、身份产品语义变化、Schema/migration、历史数据动作必须另行批准。

## Stop Condition

- Dev、适用门禁与 Independent Review 完成后停在 Draft PR 人工门禁前。
- 如现有 Accepted ADR 无法兼容历史数据而需新增 fallback 产品语义、Schema 或回填，立即 `BLOCKED` 并交 Product Owner。

## Evidence

- Original evidence：`PDD-MANUAL-REGRESSION-001` 的 Product 1182 / Snapshot 1050 运行证据。
- Derived artifacts：`docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001-verification/`。
- Review findings：首轮代码无 finding；历史失败由应用 Oracle 环境未绑定 T003 导致，正确绑定后 strict 54/54 PASS；等待 Re-review。
- Commit / PR：代码 Head `643e5334880e9cc7d4f57c597e14c437613f90cd` / forbidden before approval。
