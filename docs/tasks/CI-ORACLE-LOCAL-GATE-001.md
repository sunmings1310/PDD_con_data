# CI-ORACLE-LOCAL-GATE-001：Oracle 本地严格证据合并门禁

- **Task ID**：CI-ORACLE-LOCAL-GATE-001
- **Title**：Oracle 本地严格证据合并门禁
- **Status**：REVIEW
- **状态权威**：[`../backlog.md`](../backlog.md)

## Goal

保留 Hosted offline CI 与 Oracle applicability 分类，把真实 Oracle 门禁改为固定 PR Head 的本地隔离 Oracle strict 证据；GitHub Actions 不访问数据库。

## Context

Product Owner 已批准此门禁语义。基线为 `origin/main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`。PR #5 为 Draft，Head `6f35f2e342f8e283cef340e42de610c21bd78952`，保持独立且在本治理 merge 前继续 `BLOCKED`。

## Scope

### Allowed

- `.github/workflows/ci.yml`、PR 模板与门禁 validator；
- Workflow/Task/Current State/backlog/roadmap 治理文档；
- 本 Task、测试和四制品/rollback 验证产物。

### Forbidden

- 业务代码、Schema、migration、数据库数据；
- Generic SKU、P1/P2、Phase 6B；
- 修改、merge 或解除 PR #5 的 Draft/BLOCKED 状态；
- 删除当前七项 GitHub Oracle repository secrets；
- 自动 merge 或 release。

## Non-goals

- Hosted runner 不执行 Oracle 测试；
- Validator 不声称能从 GitHub 自动证明本地数据库运行真实性；
- 不改变 Oracle suite 的业务测试集合。

## Dependencies

- Product Owner 已批准目标门禁；
- `main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`；
- 本地隔离、可写、可 rollback 的 Oracle 环境。

## Affected Modules

- `.github/` CI 与 PR 模板；
- `.github/scripts/validate_oracle_local_evidence.py`；
- `WORKFLOW.md` 与 `docs/` 治理状态、模板、证据。

## ADR

None。该任务改变仓库合并治理，不改变产品/数据架构。

## Acceptance Criteria

- [ ] Hosted CI 保留 Python offline、Android JVM、Web build、Governance 与 Oracle applicability；
- [ ] Hosted CI 不连接数据库、不引用 T003 Oracle/JWT repository secrets；
- [ ] Oracle-sensitive PR 必须提交绑定固定 Head 的 fresh local strict manifest；
- [ ] Manifest 包含 exact command、Head、测试数量、字面结果/hash、exit、环境标识、时间、四制品与 rollback/无持久业务变更；
- [ ] Validator 拒绝错误 Head、缺字段、非零 exit、SKIPPED/BLOCKED、结果/制品篡改、过期和错误命令；
- [ ] 文档与模板统一 merge 条件和 remaining trust boundary；
- [ ] Independent Review 明确确认没有把 Oracle 门禁降为可任意跳过；
- [ ] 固定 clean Head 推送并创建独立 Draft PR；Hosted CI 不访问数据库；merge 前停止。

## Evidence Manifest

PR body 必须含且只含一个 `<!-- oracle-local-evidence:v1 -->` marker，随后为 JSON code block。Validator schema 由 [`.github/scripts/validate_oracle_local_evidence.py`](../../.github/scripts/validate_oracle_local_evidence.py) 唯一定义。Canonical command：

```powershell
powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict
```

四制品角色固定为 `modified_file`、`diff_file`、`verification`、`rollback`，每个记录 repository-relative path 和 SHA-256；rollback 文件必须以 Git mode `100755` 提交。Head 移动后必须在新 Head 重跑并更新 PR body。

GitHub 能核验 manifest 结构、当前 Head、72 小时时效、canonical command、全量零 skip/blocked/failure、字面输出 SHA-256、四制品内容 SHA-256 与 executable rollback。提交者仍可伪造一套内部一致的本地输出；因此 Independent Reviewer 必须核验运行来源、隔离环境和 rollback。此 remaining trust boundary 不等价于 Hosted DB run。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Validator unit | `python -m unittest -v docs/tasks/CI-ORACLE-LOCAL-GATE-001-verification/test_validate_oracle_local_evidence.py` | 临时 Git repo + manifest fixtures | 11 cases PASS | `Ran 11 tests in 2.149s` / `OK` | 0 | PASS |
| Applicability unit | `python -m unittest -v docs/tasks/CI-ORACLE-LOCAL-GATE-001-verification/test_oracle_scope.py` | canonical runner、九文件、server/migration/oracle tests、治理 docs | required/not-applicable 分类正确 | combined targeted：`Ran 15 tests in 2.130s` / `OK` | 0 | PASS |
| Governance/static | `python docs/tasks/CI-ORACLE-LOCAL-GATE-001-verification/validate_governance.py --check <yaml/ci/markdown>` | workflow、54 Markdown、scope | YAML/Markdown/scope/secret absence PASS | `YAML_PARSE=PASS files=1`; `CI_STATIC=PASS hosted_db_access=absent oracle_bypass=absent`; `MARKDOWN_LINKS=PASS files=54` | 0 | PASS |
| Python full | `.\scripts\test-baseline.ps1 -Suite python -Strict` | Python 3.10.6，复用已确认项目 venv | offline suite PASS | `Ran 195 tests in 0.377s`; `OK (skipped=23)`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Android JVM | `.\scripts\test-baseline.ps1 -Suite android -Strict` | JDK 17.0.20 / SDK 34 | PASS | `BUILD SUCCESSFUL in 1m 7s`; XML `70 tests, 0 failures, 0 errors, 1 skipped`; strict summary PASS | 0 | PASS |
| Web build | `.\scripts\test-baseline.ps1 -Suite web -Strict` | Node 22 project toolchain / existing lockfile modules | PASS | `1673 modules transformed`; `built in 6.88s`; strict summary PASS | 0 | PASS |
| Compile | `python -m compileall -q .github/scripts docs/tasks/CI-ORACLE-LOCAL-GATE-001-verification` | Python 3.10.6 | no output | `COMPILEALL=PASS` | 0 | PASS |
| Diff | `git diff --check origin/main...HEAD` | fixed Head | no output | pending fixed Head |  |  |
| Rollback | `python <fresh-clone>/.../ROLLBACK.sh <copy>` | `git clone -c core.autocrlf=true --no-local .`，`PATCH_HAS_CRLF=True` | restored baseline behavior/status | `ROLLBACK=PASS restored_sha256=65f047... hosted_oracle_job=restored local_evidence_job=absent` | 0 | PASS |

## Oracle Gate

- Required：No（本 Task 不修改 Oracle-sensitive 业务/Schema；applicability 必须明确输出 not applicable）。
- Reason：该 Task 设计并测试门禁 validator，不执行或改变数据库行为。
- Hosted database：禁止访问。

## Real-device Gate

- Required：No；不修改 Android 行为。

## Rollback

- Code rollback：对本治理 commit 执行 revert，或用四制品 `ROLLBACK.sh` 在验证 copy 反向应用 `DIFF_FILE.patch`。
- Configuration rollback：恢复旧 workflow；不删除或修改 repository secrets。
- Data recovery：None；无数据库连接或数据变更。
- Irreversible items：None。

## Human Decision Points

- Independent Review ACCEPT 后可创建 Draft PR；merge 必须等待 Product Owner 明确批准。
- 七项旧 repository secrets 的删除属于另一个外部状态动作，待新门禁生效后另行批准。

## Stop Condition

独立 Draft PR 的 clean fixed Head、Independent Review 和不访问数据库的 Hosted CI 完成后，在 merge 前停止并请求 Product Owner 批准。

## Evidence

- Original baseline：`origin/main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`；
- PR #5 observed state：Draft / open / Head `6f35f2e342f8e283cef340e42de610c21bd78952`；
- Derived artifacts：[`CI-ORACLE-LOCAL-GATE-001-verification/`](CI-ORACLE-LOCAL-GATE-001-verification/)；
- Review / fixed Head / Draft PR：pending。

## Independent Review Findings

首轮 Review（Head `f9e1d4926a6e724faa144eebb02b8357cb99b956`）：`CHANGES_REQUIRED`，无 P0。

| Finding | Priority | Fix | Verification |
|---|---:|---|---|
| applicability 漏判 `scripts/test-baseline.ps1`、`test_phase2_schema_contract.py`、`test_job_service.py` | P1 | 独立 classifier 固定 canonical 九文件、runner、server/migration/oracle-test rules | `test_oracle_scope.py` |
| context-less artifact patch 在 fresh Windows CRLF checkout rollback 失败 | P1 | 生成 `--unified=0` patch；rollback 使用 `--unidiff-zero --ignore-space-change`；fresh CRLF checkout 回归 | `ROLLBACK=PASS ... original SHA-256 restored` |
| CURRENT_STATE 未同步 | P2 | 记录 main 基线、本治理 REVIEW 语义、PR #5 后续门禁 | Markdown/governance validation |
