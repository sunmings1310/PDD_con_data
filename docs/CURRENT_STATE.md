# PDD_APP 当前状态

> **Status: CURRENT IMPLEMENTATION AUTHORITY**
> 更新日期：2026-08-28
> 本文只记录仍影响开发、Review、E2E 和发布决策的当前事实。产品范围见 [`../PRODUCT.md`](../PRODUCT.md)，流程见 [`../WORKFLOW.md`](../WORKFLOW.md)，任务状态见 [`backlog.md`](backlog.md)。

## 1. 当前可信基线

| 项目 | 当前值 |
|---|---|
| 主分支 | `main` |
| 当前主线基线 | `d56787a614aba8559934a085a66e12bd20c12832` |
| 当前 Accepted 主线 | `d56787a614aba8559934a085a66e12bd20c12832`，包含 PR [#13](https://github.com/sunmings1310/PDD_con_data/pull/13) |
| Accepted Business Baseline | `02234f2fd50d4b4afeceec6ff782d0151016887d`，来源 PR [#2](https://github.com/sunmings1310/PDD_con_data/pull/2) |
| Accepted Governance Baseline | PR [#3](https://github.com/sunmings1310/PDD_con_data/pull/3)，Head `767a5ffe12de38d93570451566def314699043bf`，merge commit `713cd714902c728cc0e7b796bdde4972c78042c9` |
| 治理任务状态 | `REPO-GOV-ALIGN-001：MERGED / ACCEPTED BASELINE`；`CI-ORACLE-LOCAL-GATE-001：MERGED / ACCEPTED GATE` |
| 冻结旧治理候选 | `codex/repo-governance-baseline@28addc917706904bf84252cb1e1cbff01c75aa3d` |
| Golden Sample | PDD `platform_product_id=985843042423` |

PR #2 已于 2026-08-24 merge，形成 Accepted Business Baseline。PR #3 已于 2026-08-25 merge；`main@713cd71` 完整包含治理 Head `767a5ff`。PR #4 随后把 accepted governance state 记录合入 `main@42610e1`。PR #6 于 2026-08-26 merge 为 `main@b3a7e2c`，启用固定 PR Head 的本地隔离 Oracle evidence gate。PR #5 已普通 merge 为 `main@09e717c`；PR #7 与 #8 已完成 Web 结果可见性及状态收口。PR #9 已普通 merge 为 `main@a02c8a8`，`WEB-CLIENT-CONTRACT-001` 正式进入 Accepted 主线。PR #11 已普通 merge 为 `main@40e3e95`，`WEB-TASK-IMPORT-001` 正式进入 Accepted 主线。PR #13 已普通 merge 为当前 `main@d56787a`，`WEB-STATE-UX-001` 正式进入 Accepted 主线。

## 2. 当前权威主链

```text
Vue Web → FastAPI / Oracle → Android Agent → PDD App
         → Raw / Quality / Product / Snapshot / Media → Web
```

- Oracle 是 Task、Job、Attempt、Lease、Checkpoint、Outbox/Receipt、租户和业务结果的权威来源。
- Android Room 只保存可恢复的本地 assignment、checkpoint、outbox 和执行状态。
- 页面完成、Parser 对象或 HTTP 2xx 均不等于业务成功；服务端确认持久化是完成前提。
- 旧 PyQt6/BitBrowser/SQLite 桌面链仍保留，但不是新增能力默认落点；去留仍是 Product 决策。

## 3. 已进入 main 的 Accepted Business Baseline

- Phase 1～Phase 5.5 已验收的成功语义、任务可靠性、数据质量、管理查询和 Enterprise/Workspace 边界；
- Phase 6A Collector Contract、Registry、Capability 与 PddAdapter；
- Accepted Raw Capture foundation、Raw immutable evidence 与 tenant/workspace-bound identity；
- Product Consistency P0、Canonical Product Read/Edit Contract；
- 已验收的 lifecycle/recovery、late cancel、retry/reacquire、checkpoint、canonical receipt binding 和 Oracle reconciliation compatibility 修复；
- 默认 PDD 采集路径不执行自动 SKU panel、购买入口或组合遍历。

主要证据：

- [`tasks/phase6a-acceptance.md`](tasks/phase6a-acceptance.md)
- [`tasks/BASELINE-SPLIT-001.md`](tasks/BASELINE-SPLIT-001.md)
- [`decisions/2026-08-24-raw-capture-identity-immutability.md`](decisions/2026-08-24-raw-capture-identity-immutability.md)
- PR [#2](https://github.com/sunmings1310/PDD_con_data/pull/2)

## 4. 明确未开始或未获准

- **Generic SKU runtime：NOT STARTED**；历史 Schema/SKU panel/Generic SKU 调查只构成实验与证据，不构成 Accepted production capability。
- **P1 SKU/ProductAttribute Oracle Schema：NOT STARTED**；没有正式 migration。
- **Phase 6B：NOT STARTED**；未接入京东、淘宝、1688 或其他第二平台 Collector。
- 不执行历史数据回填、污染 SKU 清洗、破坏性迁移或生产数据删除。

上述事项只有 Product Owner 明确批准、建立 Task/ADR 并满足门禁后才能实施。

## 5. 最近实际门禁

Accepted Business Baseline 最终 Review 记录的实际结果：

| Gate | 实际结果 |
|---|---|
| Independent Review | `ACCEPT`，无新 P0/P1 |
| Python full | 195 tests，`OK (skipped=23)`；Oracle opt-in skip 未计为 Oracle PASS |
| Android JVM | 70 tests，0 failures，0 errors，1 skipped |
| Web production build | 1673 modules，PASS |
| Python compile | `python -m compileall -q server scripts tests`，exit 0 |
| Isolated Oracle strict | 46/46 PASS，skipped=0 |
| Product Golden Sample | `985843042423`，`result=PASS` |

完整字面输出、环境和 Review 修复证据保存在 PR #2 及对应 Task；本文不复制第二份测试日志。

## 6. 治理基线完成状态

`REPO-GOV-ALIGN-001` 已以 `MERGED / ACCEPTED BASELINE` 完成。PR #3 只把旧治理候选中仍适用的治理文档、AGENTS、模板和 CI 对齐到 Accepted Business Baseline：

- 不修改业务代码、测试断言、Schema、migration 或生产配置；
- 不移植 Generic SKU 工具或过期业务状态结论；
- 不修改、rebase 或合并冻结旧治理分支；
- 最终 Independent Review 为 `ACCEPT`；Hosted Core CI [#32756266442](https://github.com/sunmings1310/PDD_con_data/actions/runs/32756266442) 整体成功；
- 经 Product Owner 单独批准后，PR #3 已 merge 为 `713cd714902c728cc0e7b796bdde4972c78042c9`。

治理 Head、Review、验证与 merge 证据以 [`tasks/REPO-GOV-ALIGN-001.md`](tasks/REPO-GOV-ALIGN-001.md) 和 PR #3 为准。

## 7. Oracle 本地证据门禁状态

`CI-ORACLE-LOCAL-GATE-001` 已获 Product Owner 批准并通过 PR [#6](https://github.com/sunmings1310/PDD_con_data/pull/6) merge 为 `b3a7e2c493f44f4cb0bde7645d2c79340d019d65`；Independent Review 对固定实现 Head `40fd4a6989f95b3fa06a9e25afbe19b9a664a6d1` 给出 `ACCEPT`，无 P0/P1/P2 finding：

- GitHub Actions 保留 Python offline、Android JVM、Web build、Governance 与 Oracle applicability，但不连接数据库、不读取 T003 Oracle/JWT repository secrets；
- Oracle-sensitive PR 必须在固定 PR Head 的本地隔离 Oracle 上执行 canonical strict command，并在 PR body 提交结构化 manifest；
- Hosted validator 检查 Head、时效、canonical 九文件集合/计数、字面输出和四制品 hash、rollback 与无持久业务变更；`BLOCKED`/`SKIPPED` 不能冒充 `PASS`；
- Independent Reviewer 仍必须核验本地运行来源与隔离性。该人工信任边界不等价于 Hosted DB run；
- 门禁已经进入 main；GitHub Actions 不运行数据库测试。Oracle-sensitive PR 必须由本地隔离 Oracle strict manifest 和 Hosted evidence validator 共同通过。PR #7 已在固定 Head `2309af8` 完成本地 Oracle 46/46、skipped=0、Hosted evidence validator 与 Independent Review provenance 核验。

## 8. 文档唯一职责

| 文档 | 唯一职责 |
|---|---|
| [`../PRODUCT.md`](../PRODUCT.md) | Product Owner 批准的产品范围与不变量 |
| 本文 | 唯一当前实现、基线和阶段状态 |
| [`backlog.md`](backlog.md) | 唯一任务状态账本 |
| [`roadmap.md`](roadmap.md) | 未来阶段与依赖，不构成实施授权 |
| [`gaps/current.md`](gaps/current.md) | 当前开放缺口入口 |
| `decisions/` | 架构与长期决策 |
| `tasks/` | Task 范围、测试、Review 与执行证据 |
| [`architecture.md`](architecture.md) | 实际架构 |
| [`../WORKFLOW.md`](../WORKFLOW.md) | 角色、开发、Review、merge、E2E 和 release 流程 |

`GAP.md`、`gap-analysis.md`、`issues.md` 和 `milestone.md` 是 Historical/Superseded 证据，不得直接授权新工作。

## 9. 下一交接

`WEB-TASK-IMPORT-001` 已通过 PR [#11](https://github.com/sunmings1310/PDD_con_data/pull/11) 普通 merge 为当前 `main@40e3e958aa27b37cd0dcbf06150317789898895f`；功能 Head 为 `caf4746f808421b6b9eb5e3d427591717e463402`。最终门禁为 Independent Review `ACCEPT`、E2E `PASS`、Hosted Core CI [#33145908892](https://github.com/sunmings1310/PDD_con_data/actions/runs/33145908892) 六项检查全部 `success`，本地隔离 Oracle 53/53（skipped=0、cleanup 五表为 0、persistent business changes=false）。任务状态为 `MERGED / ACCEPTED`。

`WEB-STATE-UX-001` 已通过 PR [#13](https://github.com/sunmings1310/PDD_con_data/pull/13) 普通 merge 为当前 `main@d56787a614aba8559934a085a66e12bd20c12832`；Feature Head 为 `1d964c629ee8f5d7a0da69ec9c71ad427669157a`。最终门禁为 Independent Review `ACCEPT`、E2E `PASS`、Hosted Core CI [#33151685082](https://github.com/sunmings1310/PDD_con_data/actions/runs/33151685082) 的适用检查全部 `success`；Oracle 与真机对该 Web-only Task 均为 `SKIPPED / not applicable`。任务状态为 `MERGED / ACCEPTED`。

已批准的 Web 执行队列至第 5 项全部完成。当前等待 Product Owner 选择下一阶段；下列未启动路线仅记录事实，不构成批准、排序或启动：

`WEB-NAV-EXCEL-CONSOLIDATION-001` 是当前未合并的 Web-only `TEST / REVIEW CANDIDATE`：导航移除独立 Excel 一级入口，兼容 `/excel` 重定向到 canonical TaskCreate，资料库承载 Excel 查库/导出，未修改 Server/Schema/canonical Task/Android。实际 Node mounted/router、既有 Node contracts、Python offline full（257 / skipped=39）和 Web build 已通过；Oracle/真机均 `SKIPPED / not applicable`。下一门禁为 Independent Review，禁止自行建 PR、merge 或 release。

- Generic SKU runtime：仍为 `NOT STARTED`；
- P1 SKU/ProductAttribute Schema：仍为 `NOT STARTED`；
- Phase 6B：仍为 `NOT STARTED`；
- release：未执行。
