# PRODUCT-REQUIREMENTS-BASELINE-001：统一产品需求权威基线

- **Task ID**：PRODUCT-REQUIREMENTS-BASELINE-001
- **Title**：将稳定产品需求统一到根 `PRODUCT.md`
- **Status**：ACCEPTED
- **Requirement IDs**：GOV-001、GOV-002
- **Base**：`main@d6553704e2a73f4376f52de5bfd1054fa52923e4`
- **Branch**：`codex/product-requirements-baseline-001`

## Goal

扩充现有 `PRODUCT.md` 为单一稳定产品需求基线，建立不可复用的 Requirement ID、状态、验收与来源追溯；不创建第二份 PRD、状态账本或业务实现。

## Context

当前稳定产品语义分散在 `PRODUCT.md`、feature list、roadmap/backlog、CURRENT_STATE、Accepted ADR 与已验收 Task 中。部分历史清单仍携带旧分支和旧状态，容易被误当作当前需求或重复开发依据。

### Product Owner approved input

- Product Owner 已批准“目标未匹配仍展示实际候选观察，但不得写入 Product/Snapshot/成功统计”的产品语义；
- 候选 Raw 与受控脱敏截图默认保留 30 天，TaskItem `not_matched` 终态和必要摘要永久保留；
- 上述是产品需求批准，不等同于 `PDD-COLLECTION-OBSERVABILITY-001` 已实现、验收或 merge；当前 main 上的实现/证据状态必须保持 `Unknown`；
- 真实平台 `no_candidate` 证据尚不足，不能将离线语义或模拟测试写成真实 E2E PASS。
- 企业管理只作为现有 Web 管理端中的简化模块：平台管理员可查看、新建、编辑、启用/停用企业，创建时自动建立默认 Workspace；
- 企业内人员、角色、设备、任务和商品复用现有页面及当前 Enterprise/Workspace 上下文；默认只用一个 Workspace，不建设复杂 Workspace 管理 UI；
- 套餐、计费、续期、自助开通、复杂额度、集团组织、跨企业分析、独立部署及复杂注销/数据清除均为 Deferred；
- 上述企业管理语义为 Accepted，但功能实现状态是 `Unknown / Not Started`，必须由后续独立开发 Task 验收，不得在本 docs-only Task 实现。

## Scope

### Allowed

- 扩充根 `PRODUCT.md`，覆盖医疗采集、Excel 统一下发、关键词血缘、候选不匹配可见、Product/SKU、媒体、租户、简化企业管理、设备与任务可观测性；
- 为稳定需求定义 ID、`Accepted / Planned / Deferred / Unknown`、目标/价值、范围、验收与约束；
- 在 Workflow/Task 模板加入 Requirement ID 追溯规则；
- 为 Historical feature list、roadmap、backlog、CURRENT_STATE 补充最小权威边界与当前主线事实；
- 新增本 Task 和专属验证/回滚制品。

### Forbidden

- 业务代码、Schema/migration、运行时数据或生产配置；
- Generic SKU runtime、P1 Schema、Phase 6B、历史回填或新产品能力；
- 复制动态排期、测试数量或分支状态到 PRODUCT；
- 创建第二套 PRD、backlog、roadmap、Control 状态表或 Requirement 状态账本。

## Non-goals

- 不重写历史 ADR/Task/验收证据；
- 不解决 roadmap/backlog 中所有历史文案；
- 不批准 `Deferred/Unknown` 项；
- 不标记 PR Ready，不 merge 或 release。

## Dependencies

- `main@d6553704e2a73f4376f52de5bfd1054fa52923e4`；
- Accepted Phase 1～6A、PR #2～#17 已合并事实；
- Product Owner 对本 Task 范围的明确批准。

## Affected Modules

- 根治理文档：`PRODUCT.md`、`WORKFLOW.md`；
- 状态/计划文档：`docs/CURRENT_STATE.md`、`docs/backlog.md`、`docs/roadmap.md`；
- 历史产品盘点：`docs/product/feature-list*.md`；
- Task 模板与本 Task 验证目录。

## ADR

不新增 ADR。本 Task 只汇总既有 Accepted 产品语义并链接原权威 ADR；不改变架构决定。

## Requirement Trace

| Requirement ID | 本 Task 的具体化验收 | 状态/批准依据 |
|---|---|---|
| GOV-001 | `PRODUCT.md` 成为唯一稳定需求入口；Task 模板引用 Requirement ID；其他文档只回链 | Product Owner 当前批准 |
| GOV-002 | 保留跨租户共享、破坏性 migration、生产、真实账号、merge/release 等人工门禁 | Product Owner 当前批准与既有 Workflow |

## Acceptance Criteria

- [x] `PRODUCT.md` 定义稳定、不重复的 Requirement ID 和四种状态语义；
- [x] 每项需求包含目标/价值、范围、验收与约束；
- [x] 覆盖获批核心产品主题，含简化企业管理边界；Deferred/Unknown 不被误写为 Accepted 实现；
- [x] 动态排期、实现状态和测试证据留在原权威文档；
- [x] Workflow 与 Task 模板要求开发 Task 引用已批准 Requirement ID；
- [x] Historical feature list 明确非权威并链接当前入口；
- [x] 所有新增/修改 Markdown 链接有效，YAML/governance、allowlist、敏感扫描与 `git diff --check` 通过；
- [x] 四个验证/回滚制品可复现，另一副本 rollback 恢复原 hash，`MODIFIED_FILE` 保持 changed；
- [x] Independent Review 为 `ACCEPT`；ACCEPT 后只创建 Draft PR并跟踪 Hosted CI。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `python docs/tasks/PRODUCT-REQUIREMENTS-BASELINE-001-verification/validate_requirements.py` | 当前工作树 | Requirement ID/字段/追溯唯一且完整 | 40 unique requirements / 14 modules；template trace present | 0 | PASS |
| Governance | Markdown links + YAML + allowlist + sensitive scan | 当前 diff | 无失效链接、非法 YAML、越界文件或敏感值 | 68 Markdown；YAML PASS；allowlist 0；sensitive 0 | 0 | PASS |
| Static | `git diff --check` | base..worktree | no output | no output | 0 | PASS |

## Oracle Gate

- Required：No
- Reason：docs-only，不修改 Schema、SQL、transaction、tenant repository 或 Oracle 方言。
- Status：`SKIPPED / not applicable`，不得称为 PASS。

## Real-device Gate

- Required：No
- Device/scenario：docs-only，不修改 Android、采集或真实页面行为。
- Status：`SKIPPED / not applicable`，不得称为 PASS。

## Rollback

- Code rollback：在独立副本按 `ROLLBACK.sh <probe-root> <base-sha>` 恢复允许文件并删除本 Task 新增文件。
- Configuration rollback：无配置变更。
- Data recovery：无数据库或运行数据变更。
- Irreversible items：无。

## Human Decision Points

- Independent Review `ACCEPT` 后允许创建 Draft PR；
- Ready、merge 与 release 仍需 Product Owner 明确批准；
- 任何新增产品语义或把 Deferred/Unknown 改为 Accepted 必须暂停请求决定。

## Stop Condition

完成文档、验证、Independent Review、Draft PR 与 Hosted CI 后停止在 Ready/merge 人工门禁；若发现权威文档无法消解的产品语义冲突则停止并报告。

## Evidence

- Original evidence：`PRODUCT.md`、CURRENT_STATE/backlog/roadmap、Accepted ADR 与 Task；原始 `PRODUCT.md` SHA-256 记录在 `VERIFICATION.txt`。
- Derived artifacts：`docs/tasks/PRODUCT-REQUIREMENTS-BASELINE-001-verification/`。
- Review findings：初审 finding 已关闭；Product Owner 随后新增简化企业管理决定，当前修订等待 Independent Re-review。
- Commit / PR：原 Review fixed Head `3314df5df8849eb9f257f8dd0f4323a48f21a7c0`；Draft PR #18 已创建，企业决定修订后保持 Draft。
