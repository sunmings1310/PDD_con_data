# PDD_APP 当前状态

> **Status: CURRENT IMPLEMENTATION AUTHORITY**
> 更新日期：2026-08-25
> 本文只记录仍影响开发、Review、E2E 和发布决策的当前事实。产品范围见 [`../PRODUCT.md`](../PRODUCT.md)，流程见 [`../WORKFLOW.md`](../WORKFLOW.md)，任务状态见 [`backlog.md`](backlog.md)。

## 1. 当前可信基线

| 项目 | 当前值 |
|---|---|
| 主分支 | `main` |
| 当前主线基线 | `42610e15cf683158eb2f96a3dc3d08e8b1f5e018` |
| Accepted Business Baseline | `02234f2fd50d4b4afeceec6ff782d0151016887d`，来源 PR [#2](https://github.com/sunmings1310/PDD_con_data/pull/2) |
| Accepted Governance Baseline | PR [#3](https://github.com/sunmings1310/PDD_con_data/pull/3)，Head `767a5ffe12de38d93570451566def314699043bf`，merge commit `713cd714902c728cc0e7b796bdde4972c78042c9` |
| 治理任务状态 | `REPO-GOV-ALIGN-001：MERGED / ACCEPTED BASELINE` |
| 冻结旧治理候选 | `codex/repo-governance-baseline@28addc917706904bf84252cb1e1cbff01c75aa3d` |
| Golden Sample | PDD `platform_product_id=985843042423` |

PR #2 已于 2026-08-24 merge，形成 Accepted Business Baseline。PR #3 已于 2026-08-25 merge；`main@713cd71` 完整包含治理 Head `767a5ff`，因此业务与治理基线现已同时进入主线。

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

## 7. 文档唯一职责

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

## 8. 下一交接

`BL-110-WS-TENANT-BOUNDARY` 已在独立分支完成本地实现、适用门禁与 Independent Review `ACCEPT`；它尚未创建 PR、merge 或 release，因此 `main` 仍不包含该能力。已验证分支把实时日志连接绑定到服务端 identity、membership、`device:view`、Device/Task 归属与 token expiry；每次投递前重新校验撤销状态，Hub 只在同 Enterprise/Workspace/Device channel 内发送；Oracle commit 后才线程安全调度，失败有日志和计数，8 秒 HTTP 轮询仍为恢复路径。

当前执行队列必须保持依赖顺序：`WEB-RESULT-VISIBILITY-001` 只能从本项 merge 后的 `main` 开始。本轮停止，不自动创建 PR、不启动后项或新业务阶段：

- Generic SKU runtime：仍为 `NOT STARTED`；
- P1 SKU/ProductAttribute Schema：仍为 `NOT STARTED`；
- Phase 6B：仍为 `NOT STARTED`。

任何后续阶段必须由 Product Owner 另行批准并建立独立 Task。
