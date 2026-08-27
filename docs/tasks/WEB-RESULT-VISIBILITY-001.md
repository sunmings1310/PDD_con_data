# WEB-RESULT-VISIBILITY-001：采集结果可见性与证据下钻

- **Task ID**：WEB-RESULT-VISIBILITY-001
- **Title**：采集结果可见性与证据下钻
- **Status**：IN_PROGRESS
- **Base**：`origin/main@09e717cdc3f67eaaf620d6a5e796445ec0334674`
- **Branch**：`codex/web-result-visibility-001`
- **Worktree**：`D:\work\PDD_con_data_web_result_visibility`

## Goal

让有权限的管理端用户稳定查看当前 Task 的采集结果，并能以服务端权威资源 ID 从 Task 下钻到 Raw、Quality、Snapshot 或 Quarantine；同时明确区分“本次采集结果”和“已保存商品资料库”，不改变采集、保存或任务成功语义。

## Context

`BL-110-WS-TENANT-BOUNDARY` 已通过 PR #5 普通 merge，当前唯一业务基线为 `main@09e717c`。现有 Task Detail 主要读取 `/api/products?task_id=...`，会遗漏尚未保存到资料库或进入 Quarantine 的任务结果；执行轨迹虽附带 Snapshot/Quarantine，但 Snapshot 导航仍以 Master Product 路由承载，Raw 与 Quality 缺少任务级直达链路。页面也未统一区分 loading、empty、error 与权限拒绝。

## Scope

### Allowed

- 在服务端现有 tenant/workspace 权威查询边界内，补充或修正 Task 结果读取 DTO/API，使 Snapshot、Quarantine、Raw、Quality 使用各自真实资源 ID。
- 修复 draft/待保存结果在 Task 上的可见性；不得要求先保存到商品资料库才可查看本次采集事实。
- 在 Web Task Detail/Trace 及必要的管理详情视图中实现 Task→Raw→Quality 下钻。
- 明确展示“本次采集结果”与“已保存商品资料库”两种状态和动作边界；保留既有人工保存语义。
- 补齐相关页面的 loading、empty、error、retry 和权限拒绝行为，避免失败后残留上一次数据。
- 增加服务端查询/权限/资源 ID 回归测试和适用的 Web 静态契约验证；保持现有构建与 Phase 1～6A 回归。
- 仅在实现确有必要时更新实际架构或既有 API 文档；不新增第二套状态账本。

### Forbidden

- `WEB-CLIENT-CONTRACT-001`、Excel 导入/导出重构或独立 Excel 菜单去留。
- Generic SKU、SKU Schema、ProductAttribute、正式 migration、历史数据回填或清理。
- Phase 6B、第二平台、Android/真机采集逻辑或真机 Gate。
- 改变 Product/Snapshot/Quality、draft→人工保存→资料库、Task Complete 或采集成功语义。
- release、merge、生产操作或生产配置变更。

## Non-goals

- 不统一全站 HTTP client 或权限路由；该工作属于后续 `WEB-CLIENT-CONTRACT-001`。
- 不建设完整质量管理平台，不重做商品资料库 UI，不新增 Schema。
- 不将页面操作、Parser 对象或 HTTP 2xx 重新定义为业务成功。

## Dependencies

- `BL-110-WS-TENANT-BOUNDARY`：已通过 PR #5 merge 到固定 base。
- Accepted Phase 1～6A、Product Consistency P0、Raw Capture、Quality/Quarantine 与 Canonical Product Contract。
- 后续 `WEB-CLIENT-CONTRACT-001` 必须等待本 Task merge 后从新 main 启动。

## Affected Modules

- Web：`web/src/views/tasks/TaskDetail.vue`、`web/src/views/management/TaskTrace.vue`、`ProductTimeline.vue`、`QuarantineList.vue`、必要路由与局部 API 调用。
- Server：`server/routers/management.py`、`server/management_queries.py` 及仅为 Task 结果读取所需的现有 read model。
- Tests：`tests/test_phase4_management.py` 及针对 tenant-bound resource ID/权限的现有测试模块；Web build/静态契约检查。
- Docs：本 Task、`docs/backlog.md`、`docs/CURRENT_STATE.md`、必要的 architecture/verification 证据。

## ADR

不新增 ADR。沿用 Accepted Product/Snapshot、Phase 3 Quality/Quarantine、Phase 4 管理查询和 Phase 5 tenant/workspace 决策。若实现要求改变产品语义、资源身份或新增持久化模型，立即停止并提交 Product Owner/ADR 决策。

## Acceptance Criteria

- [ ] 有 `task:view` 的当前租户用户可看到 Task 范围内的可信 Snapshot、draft/待保存结果与 Quarantine；未保存到资料库不再导致本次采集结果消失。
- [ ] 页面明确区分“本次采集结果”和“已保存商品资料库”；保存动作不改变已确认采集事实。
- [ ] Snapshot 链接和请求使用服务端返回的真实 `snapshot_id`；Master Product、Enterprise Product、legacy `product_id` 不得冒充 Snapshot ID。
- [ ] Task 结果可用服务端权威 ID 下钻到对应 Raw 与 Quality；缺失证据时展示明确 unavailable 原因，不猜测或拼接 ID。
- [ ] Quarantine 结果展示失败原因与可用 Raw/Quality 证据，且不会伪装成正常商品/Snapshot。
- [ ] loading、empty、error、retry、403/无权限均有确定行为；请求失败会清空或隔离陈旧数据，不显示跨 Task/租户残留。
- [ ] 所有读取继续执行 enterprise/workspace 所有权校验；跨租户、无权限及不存在资源不泄露数据。
- [ ] 不改变写入、Task 完成、人工保存、Schema/migration、默认 PDD 采集路径或 Android 行为。
- [ ] targeted、Python module/full、Web production build、Python compile、Android JVM 与 `git diff --check` 按适用门禁通过。
- [ ] 固定 Head Oracle strict（若服务端 Oracle 查询发生变化）和 Independent Review 完成；无新增 P0。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `python -m unittest tests.test_phase4_management` 及新增定向模块 | offline fake cursor + tenant/permission fixtures | draft/Snapshot/Raw/Quality/Quarantine ID 与权限断言通过 | pending |  | BLOCKED |
| Web | `npm run build` | `web/`，固定 Node/npm | production build PASS；必要静态契约测试通过 | pending |  | BLOCKED |
| Python module/full | 仓库 canonical Python test commands | offline + 隔离测试数据 | 无 Phase 1～6A 回归 | pending |  | BLOCKED |
| Android JVM | 仓库 canonical Android JVM command | 不修改 Android，仅回归 | 既有测试通过 | pending |  | BLOCKED |
| Static | `python -m compileall -q server scripts tests`；`git diff --check` | fixed Head | exit 0 | pending |  | BLOCKED |

开发过程中按 targeted→module 执行；固定实现 Head 后再运行 full/Oracle/Independent Review，不以 `SKIPPED` 或 `BLOCKED` 冒充 `PASS`。

## Oracle Gate

- Required：Conditional Yes。若修改任何 Oracle SQL、tenant ownership 查询、Task/Raw/Quality/Snapshot/Quarantine 资源绑定或事务读取，则为 **Yes**；纯 Web 文案/状态修改才可记录 No，并由 Independent Reviewer 核验。
- Reason：本 Task 很可能调整 Oracle-backed 管理查询与 tenant-bound 资源 ID，Hosted CI 不连接数据库。
- Local isolated environment identifier：待固定 Head 后记录；不得使用生产 Schema。
- Fixed Head SHA：pending
- Canonical command / test count / literal result hash / exit：pending
- Evidence generated at / expiry：pending
- Four artifacts / rollback / persistent business changes：实现阶段更新；不得保留业务测试数据。
- Hosted evidence validator：pending
- Independent Reviewer provenance check：pending

## Real-device Gate

- Required：No
- Device/scenario：本 Task 不修改 Android 或真实采集路径；记录为 `SKIPPED (not applicable)`，不得称为 PASS。
- Command or steps / result：不执行真机采集。

## Rollback

- Code rollback：对本 Task 独立 commits 执行 `git revert`，恢复原 Task/管理读取与 Web 路由；禁止 history rewrite。
- Configuration rollback：无配置变更。
- Data recovery：禁止 Schema/migration 与持久业务写入；隔离测试数据按测试脚本清理并记录字面结果。
- Irreversible items：无。

## Human Decision Points

- 产品语义、Product/Snapshot/Quality/draft 保存边界、跨租户可见性策略发生变化。
- 需要 Schema/migration、数据回填/清理、生产操作、真实账号/真机、扩大到被禁止任务。
- 创建 PR 可按当前 Workflow/Task 授权推进；merge 与 release 必须等待 Product Owner 明确批准。

## Stop Condition

- scope/acceptance/test/Oracle/rollback 已冻结，Dev 完成实现与自检，E2E/固定 Head 门禁和 Independent Review 形成可复验证据后停止在 merge 前。
- 若证据推翻现有资源身份/产品语义、要求 Schema/migration、跨入排除范围，或 Oracle/权限环境导致必要验收 `BLOCKED`，立即停止并交由 Control/Product Owner。
- 不自动启动 `WEB-CLIENT-CONTRACT-001`、Excel 导入、Generic SKU/SKU Schema、Phase 6B、真机采集或 release。

## Evidence

- Original evidence：`main@09e717c` 的 `TaskDetail.vue`、`TaskTrace.vue`、`management.py`、`management_queries.py`、`test_phase4_management.py`。
- Derived artifacts：`docs/tasks/WEB-RESULT-VISIBILITY-001-verification/`（开发与固定 Head 阶段持续更新）。
- Review findings：pending
- Commit / PR：Task setup commit pending；PR 未创建。
