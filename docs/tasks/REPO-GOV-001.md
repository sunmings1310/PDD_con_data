# REPO-GOV-001：Codex 项目治理基线

- **Task ID**：REPO-GOV-001
- **Status**：REVIEW
- **Owner**：Sol / Tech Lead
- **Date**：2026-08-23
- **Scope**：仅治理文档、Agent 规则、Task/ADR/PR 模板和 CI

## Governance Summary

从稳定提交 `13b4301445eda9768069a807a13d9f43cedb8e8f` 建立 `codex/repo-governance-baseline`。显式完成 `docs/current-state.md` 到 `docs/CURRENT_STATE.md` 的仅大小写 Git rename；建立产品、流程、文档权威、Task/ADR/PR、模块规则和首版核心 CI。未修改业务代码、Schema、migration、生产配置或测试断言。

## Deliverables

- [`PRODUCT.md`](../../PRODUCT.md)：产品范围、用户、场景、对象、不变量、成功标准与人工决策；
- [`WORKFLOW.md`](../../WORKFLOW.md)：BACKLOG 到 RELEASED 的工作流和门禁；
- 根 [`AGENTS.md`](../../AGENTS.md) 与 Server/Android/Web 模块规则；
- [`TEMPLATE.md`](TEMPLATE.md)、[`decisions/README.md`](../decisions/README.md) 与 [PR 模板](../../.github/PULL_REQUEST_TEMPLATE.md)；
- [Core CI](../../.github/workflows/ci.yml)：Markdown/YAML、diff、Python compile/unit、Android JVM、Web build；
- [`gaps/current.md`](../gaps/current.md)：开放缺口入口；历史 GAP/issues/milestone 保留并标记，backlog/roadmap 更新各自当前职责；
- Oracle integration 保持独立外部门禁，未配置时为 Skipped，启用但缺输入时 `BLOCKED`/exit 2。

## Authority Boundary

1. `PRODUCT.md`：产品范围；
2. `docs/CURRENT_STATE.md`：唯一当前状态；
3. `docs/backlog.md`：唯一任务状态；
4. `docs/roadmap.md`：未来阶段；
5. `docs/gaps/current.md`：开放缺口；
6. `docs/decisions/`：架构决定；
7. `docs/tasks/`：Task 证据；
8. `docs/architecture.md`：实际架构；
9. `WORKFLOW.md`：开发流程。

冲突的完整优先级见根 `AGENTS.md`。

## Actual Tests

| Gate | Exact command / input | Literal result | Exit | Status |
|---|---|---|---:|---|
| Rename | `git status --short ...` + `git diff --cached --summary`（rename commit 前） | `RM ...current-state.md -> ...CURRENT_STATE.md`; `rename ... (100%)` | 0 | PASS |
| Markdown | exact-case repository-relative link validator / 59 Markdown files | `MARKDOWN_LINKS_OK=59` | 0 | PASS |
| YAML | PyYAML safe load / `.github/workflows/ci.yml` | `YAML_OK jobs=5` | 0 | PASS |
| Compile | `.venv\Scripts\python.exe -m compileall -q server scripts tests` | no output | 0 | PASS |
| Python | `.\scripts\test-baseline.ps1 -Suite python -Strict` / offline | `Ran 191 tests; OK (skipped=18); PASS=1 FAIL=0 BLOCKED=0` | 0 | PASS |
| Android JVM | `.\scripts\test-baseline.ps1 -Suite android -Strict` | `BUILD SUCCESSFUL; 70 tests, 0 failures, 1 skipped` | 0 | PASS |
| Web | `.\scripts\test-baseline.ps1 -Suite web -Strict` | `1673 modules transformed; build PASS` | 0 | PASS |
| Oracle absence | strict Oracle with Oracle flags/vars cleared | `[BLOCKED] oracle-integration; PASS=0 FAIL=0 BLOCKED=1` | 2 | BLOCKED（预期，非 PASS） |
| Diff | `git diff --check` | no whitespace errors | 0 | PASS |

Python 的 18 个 skip 是 opt-in Oracle 测试，不计为 Oracle PASS。Hosted GitHub Actions 尚未通过 PR 触发，不能称为 hosted CI PASS。

## Risk / Rollback

- 首个 PR 应观测完整依赖安装时长、Gradle/Maven 网络和 runner 缓存；环境下载失败需与测试失败区分。
- Oracle secrets/variable 由维护者配置；涉及 Oracle 语义的 Task 最终验收仍需隔离 Oracle 实跑。
- rename 已独立提交，可按提交回退；治理文档可整体 revert。`ROLLBACK.sh` 已在副本上验证只恢复原始 `AGENTS.md`。

验证与回滚证据：[`MODIFIED_FILE.txt`](REPO-GOV-001-verification/MODIFIED_FILE.txt)、[`DIFF_FILE.patch`](REPO-GOV-001-verification/DIFF_FILE.patch)、[`VERIFICATION.txt`](REPO-GOV-001-verification/VERIFICATION.txt)、[`ROLLBACK.sh`](REPO-GOV-001-verification/ROLLBACK.sh)。

## Stop Condition

提交并 push 治理分支后停止；不 merge、不进入 SKU、P1 或 Phase 6B，等待独立 Review。
