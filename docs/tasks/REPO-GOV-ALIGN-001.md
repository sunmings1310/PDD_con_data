# REPO-GOV-ALIGN-001：治理基线对齐最新 main

- **Task ID**：REPO-GOV-ALIGN-001
- **Title**：治理基线对齐最新 main
- **Status**：MERGED / ACCEPTED BASELINE
- **状态权威**：[`../backlog.md`](../backlog.md)

## Goal

从唯一可信业务起点 `main@02234f2fd50d4b4afeceec6ff782d0151016887d` 建立最小、单一的治理基线，并将固定 Head 交给 Independent Review。

## Context

旧治理候选 `codex/repo-governance-baseline@28addc917706904bf84252cb1e1cbff01c75aa3d` 基于旧业务历史，规则主体可复用，但其 CURRENT_STATE、backlog 和 roadmap 不能直接进入最新 main。旧分支保持冻结，不 rebase、不 merge、不改写。

## Scope

### Allowed

- 治理文档、根与模块级 `AGENTS.md`；
- Product/Workflow、Task/ADR/PR 模板；
- GitHub CI；
- CURRENT_STATE 大小写 rename、当前状态、backlog、roadmap 和 Historical/Superseded 标记；
- 本 Task 与验证证据。

### Forbidden

- 业务代码、测试断言、Android 采集逻辑、Server/Web 业务逻辑；
- Oracle Schema、migration、生产配置；
- Generic SKU、P1、Phase 6B；
- 修改旧治理分支；
- 在 Independent Review、Hosted CI 和 Product Owner 单独批准完成前创建 PR 或 merge；这些门禁后来已依次满足，最终结果记录在本 Task 的 Evidence。

## Non-goals

- 不设计第二套 Operating Model；
- 不创建第二份 backlog、Control/Release 状态账本或固定 Agent 池；
- 不重写历史 GAP/issues/milestone 证据。

## Dependencies

- `main@02234f2fd50d4b4afeceec6ff782d0151016887d`；
- PR #2 已 merge；
- 旧治理候选只作为治理内容来源。

## Affected Modules

- 根治理入口；
- `.github/` 模板与 CI；
- `docs/` 当前状态、任务、决策、缺口与历史入口；
- `server/`、`android_collector/`、`web/` 模块级 Agent 规则。

## ADR

None。此任务不改变产品或架构语义。

## Acceptance Criteria

- [x] 新分支从精确 main SHA 创建，旧治理分支保持不变；
- [x] 只移植仍适用的治理文件，无业务实现；
- [x] Accepted Business Baseline 已进入 main；
- [x] Generic SKU runtime、P1 Schema、Phase 6B 明确为 NOT STARTED；
- [x] `WORKFLOW.md` 只有一处角色/交接/Control/责任矩阵；
- [x] `AGENTS.md` 只增加精简子模型路由并引用 Workflow；
- [x] 历史 GAP/issues/milestone 只增加状态和权威链接；
- [x] 首轮 Independent Review 给出 `CHANGES_REQUIRED`，所有 P1/P2 finding 已完成最小修复并等待复审；
- [x] 第二轮 Independent Review 的 diff-base `BLOCKED` 语义与字面证据 finding 已完成最小修复并等待复审；
- [x] Independent Review 对固定 Head `767a5ffe12de38d93570451566def314699043bf` 给出最终结论 `ACCEPT`；
- [x] Product Owner 单独批准 merge，PR #3 已合并为 `713cd714902c728cc0e7b796bdde4972c78042c9`。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Markdown links | `python docs/tasks/REPO-GOV-ALIGN-001-verification/validate_governance.py --check markdown` | 59 Markdown files | 所有 repository-relative 链接存在 | `Validated 59 Markdown files` | 0 | PASS |
| YAML/CI | `python docs/tasks/REPO-GOV-ALIGN-001-verification/validate_governance.py --check yaml`；`--check ci` | `.github/workflows/ci.yml`、resolver | YAML 可解析；6 个 jobs、Android 与 Oracle 语义存在 | `YAML_PARSE=PASS`; `CI_STATIC=PASS` | 0 | PASS |
| Diff-base resolver | `python docs/tasks/REPO-GOV-ALIGN-001-verification/validate_governance.py --check resolver` | PR、push、workflow_dispatch 及无效 base/head/fetch/merge-base 故障注入 | 正常范围 PASS；所有不可判定范围输出 `BLOCKED`、exit 2 | `RESOLVER_TESTS=PASS`，四类故障均为字面 `BLOCKED`/2 | 0 | PASS |
| Rename | `git show --summary e1ed4cb59551e6b97511c2daf8755cdba4bd95f2`；`git ls-files docs/current-state.md docs/CURRENT_STATE.md` | rename-only commit | 100% 大小写 rename；只保留 uppercase | `rename ... (100%)`; `docs/CURRENT_STATE.md` | 0 | PASS |
| Scope/static | `python docs/tasks/REPO-GOV-ALIGN-001-verification/validate_governance.py --check scope` | 27 changed paths（大小写 rename 计两个路径） | 无业务/Schema/测试断言修改 | `CHANGED_FILES=27`; `SCOPE_STATIC=PASS` | 0 | PASS |
| Android hosted | GitHub Actions Core CI #32756266442 | Head `767a5ffe12de38d93570451566def314699043bf` | wrapper main 实际执行 JVM tests | `Android JVM tests|success` | 0 | PASS |
| Whitespace | `git diff --check origin/main...HEAD; if ($LASTEXITCODE -eq 0) { Write-Output 'DIFF_CHECK=PASS' }` | fixed Head | 无错误 | `DIFF_CHECK=PASS` | 0 | PASS |

## Oracle Gate

- Required：No
- Reason：只修改治理文档、模板和 CI；`oracle-scope` 必须显式分类为不适用后才 `SKIPPED`。若分类为 Required/启用而缺参数，Oracle job 输出 `BLOCKED` 并 exit 2。

## Real-device Gate

- Required：No
- Reason：不修改 Android 业务或生命周期行为。

## Rollback

- Code rollback：在未 merge 前删除新分支/worktree；若未来 merge，revert 本治理 commit。
- Configuration rollback：None。
- Data recovery：None；无数据库或生产数据变更。
- Irreversible items：None。

## Human Decision Points

- Independent Review 已 `ACCEPT`；Product Owner 已单独批准 PR #3 merge。该批准只适用于本治理 Task，不授权 Generic SKU、P1、Phase 6B 或 release。

## Stop Condition

PR #3 merge 并更新权威状态后停止；不进入 Generic SKU、P1 或 Phase 6B。

## Evidence

- Original baseline：`main@02234f2fd50d4b4afeceec6ff782d0151016887d`；
- Old governance source：`28addc917706904bf84252cb1e1cbff01c75aa3d`；
- Verification artifacts：[`REPO-GOV-ALIGN-001-verification/`](REPO-GOV-ALIGN-001-verification/)；
- Rename-only commit：`e1ed4cb59551e6b97511c2daf8755cdba4bd95f2`；
- Accepted governance Head：`767a5ffe12de38d93570451566def314699043bf`；
- PR：[REPO-GOV-ALIGN-001 #3](https://github.com/sunmings1310/PDD_con_data/pull/3)，最终 Review `ACCEPT`；
- Merge commit / current main baseline：`713cd714902c728cc0e7b796bdde4972c78042c9`。
