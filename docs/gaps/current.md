# Current Open Gaps

> 状态：Current gap authority
> 更新日期：2026-08-25
> 本文只记录仍开放的缺口；任务状态以 [`../backlog.md`](../backlog.md) 为准，当前实现以 [`../CURRENT_STATE.md`](../CURRENT_STATE.md) 为准。

| Gap | 状态 | 决策/验收入口 |
|---|---|---|
| 正式 SKU/ProductAttribute Oracle 模型缺少充分真实证据 | OPEN / PRODUCT GATE | 先完成 SKU 证据 Task 和独立 ADR；不得由旧 backlog 条目直接授权实现 |
| Generic SKU runtime 与 Phase 6B 尚未获准 | NOT STARTED / PRODUCT GATE | 只有 Product Owner 明确批准后才能建立实施 Task；历史调查不构成生产能力 |
| Task `DEADLINE_AT` 的产品终态策略未定 | OPEN / HUMAN DECISION | 明确超时后的 failed/partial/cancelled 行为后建立 Task |
| 托管 CI 尚未证明隔离 Oracle 门禁 | OPEN / EXTERNAL GATE | CI 核心门禁不把 Oracle skipped 计为 PASS；相关 Task 最终验收需实际 Oracle |
| 真机 kill/force-stop/Doze/断网长稳证据仍有限 | OPEN / REAL-DEVICE GATE | 涉及 Android 生命周期的 Task 必须单独执行真机验收 |
| 旧 PyQt6/BitBrowser/SQLite 桌面链去留未决 | OPEN / PRODUCT DECISION | 未获决策前不扩展新能力 |
| 已记录的工具链与 Web 性能警告 | OPEN / P2 | 仅在有指标、范围和验收的独立 Task 中处理 |

历史 GAP 和 issues 中已关闭或过期的条目不自动重新开放。发现新缺口时先在本文登记，再按 [`../../WORKFLOW.md`](../../WORKFLOW.md) 创建 Task。
