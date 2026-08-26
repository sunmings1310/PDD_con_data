# Repository Workflow

> 状态：Active
> 更新日期：2026-08-25

## 1. 工作流状态

```text
BACKLOG → READY → IN_PROGRESS → TEST → REVIEW
                                      ├→ CHANGES_REQUIRED → IN_PROGRESS
                                      └→ ACCEPTED → PR → MERGED → E2E → RELEASED
```

- **BACKLOG**：已记录但尚未具备实施条件。
- **READY**：目标、范围、依赖、验收、门禁、回滚和人工决策点已明确。
- **IN_PROGRESS**：在独立分支/worktree 中进行单一目的变更。
- **TEST**：按分层顺序执行适用门禁并记录字面结果。
- **REVIEW**：由未承担同一核心实现的 Reviewer 独立检查。
- **CHANGES_REQUIRED**：Review 发现未关闭，回到实现并重测。
- **ACCEPTED**：Review 与本地适用门禁通过，允许创建/更新 PR；不等于已 merge。
- **PR / MERGED / E2E / RELEASED**：分别代表 PR 待维护者处理、已合并、合并后端到端验证、获准发布完成。
- **BLOCKED** 与 **SKIPPED** 是门禁结果而非成功状态，绝不能写成 `PASS`。

`docs/backlog.md` 是任务状态唯一账本；Task 文件保存范围、执行和证据，不并行维护另一套任务状态表。

## 2. 角色、交接与唯一维护责任

这些是一次 Task 中的工作角色，不是固定 Agent 名册，也不要求长期占用独立模型。

| 角色 | 唯一职责 | 接收条件 | 交接出口 |
|---|---|---|---|
| Product Owner | 批准产品行为、范围、优先级、破坏性数据动作、merge 与 release | Control 提供可选择方案、影响和证据 | 明确批准、拒绝或产品决定 |
| Control | 维护流程、Task/backlog 状态、分支/worktree、Agent 调度、门禁汇总、PR 与 CURRENT_STATE | 已批准 Task 或明确用户指令 | 固定 Head、完整证据和范围交给 Independent Review |
| Dev | 在批准范围内实现、分层测试、自检并记录证据 | READY Task、独立分支/worktree、明确文件边界 | 进入 TEST/REVIEW；不得自我 ACCEPT 或 merge |
| Independent Review | 对固定 Head 独立检查范围、不变量、测试、风险和回滚 | Head 未移动、Dev 自检与适用门禁完成 | `ACCEPT`、`CHANGES_REQUIRED` 或 `BLOCKED` |
| E2E | 从已 merge 的 main 或明确发布候选执行 Task 定义的端到端场景 | MERGED，环境、账号/设备和步骤明确 | 可复现 E2E 证据交给 Control；不替代 Product Owner 的 release 批准 |

Control 在已批准 Task 范围内可自动推进调查、拆解、分支/worktree、Dev 调度、`IN_PROGRESS → TEST → REVIEW → CHANGES_REQUIRED` 循环、测试修复、证据整理，以及不涉及生产操作的已定义 E2E。Review `ACCEPT` 后，Control 默认可自动创建或更新 Draft PR；如果当前 Task 的 Stop Condition 或 Human Decision Points 明确禁止 PR 或要求另行批准，则以该 Task-specific override 为准并停止。以下动作必须等待 Product Owner：新增或改变产品行为/优先级、Generic SKU/P1/Phase 6B 启动、破坏性迁移或数据删除/回填、生产操作、真实账号/密钥/人工验证、明显不同的产品方案、merge 和 release。

唯一维护责任：Product Owner 批准 `PRODUCT.md` 与 roadmap 优先级；Control 唯一维护 `docs/backlog.md` 状态、分支分配、PR 元数据和 `docs/CURRENT_STATE.md`；Dev/Reviewer/E2E 只向 Task 写各自证据，Control 负责同步状态；架构作者提出 ADR，Accepted 状态仍需相应人工批准。

## 3. Task 创建与开工条件

从 [`docs/tasks/TEMPLATE.md`](docs/tasks/TEMPLATE.md) 建立 Task。进入 `READY` 前必须具备：可验证 Goal、Scope/Non-goals、依赖、受影响模块、关联 ADR、验收条件、测试计划、Oracle/真机门禁、回滚、人工决策点和停止条件。

开工前依次阅读 [`PRODUCT.md`](PRODUCT.md)、[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)、相关 Accepted ADR、Task 和适用 `AGENTS.md`。复用已有调查；不得用旧 roadmap/GAP 条目代替当前授权。

## 4. Branch、worktree 与 Codex 窗口

- 从 Task 指定的稳定提交创建 `codex/<topic>`；一个分支只承载一个 Task 目的。
- 并行任务使用独立 worktree；同一 worktree 或同一核心文件不得由多个 Agent 同时修改。
- 开新 Codex 窗口时，在首条上下文中提供仓库、基线提交、分支、Task、允许/禁止范围、已确认结论、当前测试与停止条件；新窗口不得重新全面审计。
- 开始和提交前检查 `git status`，不得覆盖或夹带他人的变更；禁止强推和改写他人历史。

## 5. Agent 并行与升级

- 仅对文件边界真正独立的任务并行；调查结论先压缩为文件、调用链、约束、风险和验证，后续直接复用。
- 调查 Agent 发现跨模块或复杂状态语义时升级给实现 Agent/Tech Lead；实现连续两次不能可靠解决时由 Tech Lead 接管。
- 同一核心文件只能有一个修改者；简单单文件修复由当前 Agent 直接完成。
- Review 必须保持独立性：实现者先自检，关键架构、跨模块与最终验收由未承担该核心实现的人复核。

## 6. 修改、测试与证据

先调查再修改；每次只改变一个可验证变量。原始 fixture、日志和捕获证据与派生报告、补丁和构建产物分离保存。

测试顺序：

```text
targeted tests → module tests → full regression → required integration/E2E gates
```

核心本地入口：

```powershell
.\scripts\test-baseline.ps1 -Suite python -Strict
.\scripts\test-baseline.ps1 -Suite android -Strict
.\scripts\test-baseline.ps1 -Suite web -Strict
git diff --check
```

实际报告必须包含命令、输入/环境、字面输出摘要、退出码和 `PASS / FAIL / BLOCKED / SKIPPED`。不得把“未运行”“无环境”或 HTTP 2xx 描述为业务通过。Oracle-sensitive PR 还必须在固定 PR Head 上生成本地证据 manifest，并由 Hosted CI 的 `Oracle local evidence gate` 校验 Head 绑定、时效、测试计数、字面结果 hash、四制品 hash 与 rollback 状态。

## 7. Oracle Gate 与真机 Gate

- GitHub Actions 只执行 Python offline、Android JVM、Web build、Governance、Oracle applicability 分类与本地证据 validator；Hosted runner 不连接数据库，也不读取或要求 T003 Oracle/JWT repository secrets。
- 涉及 migration、tenant、transaction、Lease/幂等、Oracle repository 或 Oracle 方言的 Task，在最终验收前必须在隔离、可写、可清理的本地 Oracle 测试环境，对固定 PR Head 运行 `powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict`。Task 或 CI 差异分类明确判定 Oracle 不适用时才可记为 `SKIPPED`；Oracle Gate 为 Required 而缺环境、参数、合格证据或 Reviewer 核验时必须输出 `BLOCKED` 并失败，绝不能记为 `PASS` 或 `SKIPPED`。
- Required evidence 至少记录 exact command、Head SHA、测试集合/数量、字面结果及 SHA-256、exit code、隔离环境标识、生成时间、四制品 SHA-256、显式 rollback 与“无持久业务变更”。格式与 validator 见 [`docs/tasks/CI-ORACLE-LOCAL-GATE-001.md`](docs/tasks/CI-ORACLE-LOCAL-GATE-001.md)。证据放在 PR body，避免提交证据后改变其所绑定的 Head。
- Validator 能拒绝错误 Head、缺字段、非零 exit、`SKIPPED`/`BLOCKED`、结果或制品篡改、过期和错误命令；它不能从 GitHub Hosted runner 自动证明本地数据库运行确实发生。Independent Reviewer 必须核对本地运行来源、隔离性和四制品/rollback，且不得把此人工信任边界描述为 Hosted DB run 的等价替代。
- Schema/migration 必须版本化、可重入并附恢复说明；破坏性迁移、已有数据删除/回填必须先获人工批准。
- 涉及 Android 生命周期、系统 kill/force-stop、Doze、网络恢复、真实 App 页面或设备行为时必须执行真机 Gate；无设备不能以 JVM 测试替代并宣称 PASS。

## 8. Review、merge、E2E 与发布

- PR 使用 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)，列出实际测试、外部门禁、风险、已知问题和回滚。
- Agent 不自动 merge。Oracle-sensitive PR 只有 Independent Reviewer `ACCEPTED`、GitHub offline CI 通过、本地 Oracle evidence gate 通过且维护者明确批准后才能 merge。
- merge 后执行 Task 指定的 E2E；E2E 通过且发布获得批准后才标记 `RELEASED`。
- 回滚必须说明代码回退、配置恢复和数据恢复；不可逆项必须在实施前得到批准。

## 9. 文档更新时间

- 架构实际变化随实现更新 `docs/architecture.md`；重要长期决策先写 ADR。
- Task 在状态转换、测试、Review 和验收时更新证据；`docs/backlog.md` 同步唯一任务状态。
- `docs/CURRENT_STATE.md` 在变更达到 `ACCEPTED` 时记录已验证分支状态，merge/E2E/release 后再次更新对应事实；不得提前写成已发布。
- 历史证据不删除；由新文档替代时添加 Superseded/Historical 标识和权威链接。

## 10. 必须暂停询问用户

遇到以下任一情况必须暂停：产品业务行为或跨企业共享边界未决；破坏性迁移、数据删除/回填；生产操作；需要真实账号、密钥或人工验证；两种方案产生明显不同产品行为；Roadmap/ADR 存在重大架构冲突；无法在批准范围内完成；或 merge/发布需要人工批准。
