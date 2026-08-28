# WEB-NAV-EXCEL-CONSOLIDATION-001：收敛 Excel 入口与统一任务创建流程

- **Task ID**：WEB-NAV-EXCEL-CONSOLIDATION-001
- **Title**：收敛 Excel 入口与统一任务创建流程
- **Status**：ACCEPTED / PR CANDIDATE
- **Base**：`origin/main@f7d037cd612df09059dcea83189e63f99097042d`
- **Branch / worktree**：`codex/web-nav-excel-consolidation-001` / `D:\work\PDD_con_data_web_nav_excel_consolidation`

## Goal

删除独立 Excel 任务下发认知，让任务导入只从“任务调度 → 创建任务 → Excel 导入创建”进入；同时把 Excel 批量查库/导出能力放入商品资料库上下文，并以显式 mode 保证任务导入与资料库查库动作互斥。

## Context

- `TaskCreate.vue` 已支持 manual / Excel source，并通过 embedded `ExcelMatch` 形成 canonical `POST /api/tasks`。
- `AdminLayout.vue` 仍暴露一级“Excel匹配回填”；`/excel` 仍直接渲染独立 `ExcelMatch`。
- 独立页面仍调用兼容端点 `/api/excel/unmatched-to-task`，形成第二条直接下发路径。
- embedded `ExcelMatch` 仍显示批量导出，与已批准“Excel 导出不进入创建页”冲突。

## Scope

### Allowed

- 删除左侧 Excel 一级菜单；
- `/excel` 兼容重定向到 `/tasks/create?source=excel`；
- `TaskCreate` 可靠读取 query 并选择 Excel source，同时保持 tenant/workspace/route stale fence；
- 在商品资料库提供“Excel 批量查库/导出”上下文入口，可使用 `/products/excel-match` 或等价最小路由；
- `ExcelMatch` 明确 `task-import` 与 `library-match` 两种 mode：前者只输出 draft rows，后者只查库/导出；
- 删除生产 Web 对 `/api/excel/unmatched-to-task` 的调用及直接下发 UI；服务端 route 保留兼容；
- 补真实 mounted component、router contract、静态负向约束及必要 helper/test。

### Forbidden

- 修改 Server 业务、Schema、migration 或 Oracle 数据；
- 修改 Android、采集节奏、canonical Task payload/submission id 或 Task 完成语义；
- 修改 draft→人工保存→资料库语义；
- Generic SKU runtime、P1 Schema、Phase 6B、release；
- 顺手处理系统设置、报表、OTA、图片清理或全站 UI 重构。

## Non-goals

- 不删除服务端 `/api/excel/unmatched-to-task` 兼容 route；
- 不新增 Excel 服务端契约；
- 不用导航隐藏替代服务端权限；
- 不改变 Excel 模板、匹配、多候选、export-batch 或 canonical task create 的服务端语义。

## Dependencies

- `WEB-TASK-IMPORT-001`、`WEB-CLIENT-CONTRACT-001`、`WEB-STATE-UX-001` 已 MERGED / ACCEPTED；
- 当前可信 `main@f7d037cd612df09059dcea83189e63f99097042d`。

## Affected Modules

- `web/src/layout/AdminLayout.vue`
- `web/src/router/index.js`
- `web/src/views/tasks/TaskCreate.vue`
- `web/src/views/excel/ExcelMatch.vue`
- `web/src/views/data/ProductList.vue`
- 必要的紧邻 Web helper/scripts/tests
- 本 Task、`docs/backlog.md`、`docs/CURRENT_STATE.md` 与专属验证制品

## ADR

不新增 ADR。该修改落实已批准 Web 入口归属，不改变长期数据或任务契约。

## Acceptance Criteria

- [x] 左侧导航不存在 Excel 一级菜单；
- [x] `/excel` 重定向至 `/tasks/create?source=excel`；
- [x] query 可靠选择 Excel source，错误值安全回退；
- [x] 商品资料库存在明确“Excel 批量查库/导出”入口；
- [x] `task-import` mode 不显示导出、不直接下发，只 emit draft rows；
- [x] `library-match` mode 可模板/上传/匹配/候选/导出，但不创建或下发 Task；
- [x] 生产 Web 不引用 `/api/excel/unmatched-to-task`；
- [x] tenant/workspace/platform 切换与 unmount stale/abort 行为保持；
- [x] canonical Task payload、submission id 与 ACK retry 行为保持；
- [x] mounted component/router contract、existing Excel/task regressions 与 production build 通过；
- [x] Independent Review `ACCEPT`；Draft PR Hosted CI 全绿后 STOP before merge。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Baseline mounted | `npx -y node@22.18.0 scripts/test-task-import-components.mjs` | Node 22.18；`npm ci --include=optional` | existing mounted flows pass | 7 component groups PASS | 0 | PASS |
| Baseline contracts | `test-task-import-contract.mjs` + `test-client-contract.mjs` | Node 22.18 | canonical/client contracts pass | contract PASS；client contract PASS | 0 | PASS |
| Baseline build | `Push-Location web; npx -y node@22.18.0 node_modules/vite/bin/vite.js build; $exit=$LASTEXITCODE; Pop-Location; exit $exit` | dependencies installed by Node 22.18/npm 10.9.3 | production build | `✓ built in 672ms` | 0 | PASS |
| Targeted | `npx -y node@22.18.0 scripts/test-nav-excel-consolidation-components.mjs` | mounted TaskCreate/ExcelMatch/ProductList + actual router + delayed adapter | navigation/query/mode/permission/stale fences | 4 PASS lines | 0 | PASS |
| Existing mounted | `npx -y node@22.18.0 scripts/test-task-import-components.mjs` | existing mounted task-import/state flows | no regression | 7 component groups PASS | 0 | PASS |
| Node contracts | `test-task-import-contract.mjs` + `test-client-contract.mjs` | Node 22.18 | canonical/client contracts pass | all printed contracts PASS | 0 | PASS |
| Python offline targeted | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe -m unittest tests.test_task_import_contract tests.test_web_client_contract` | Python 3.10 / pydantic 2.13.4 | compatibility contracts pass | `Ran 15 tests` / `OK` | 0 | PASS |
| Python offline full | `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'` | Python 3.10 / no Oracle env | applicable regression | `Ran 257 tests` / `OK (skipped=39)` | 0 | PASS |
| Module/full | `Push-Location web; npx -y node@22.18.0 node_modules/vite/bin/vite.js build; $exit=$LASTEXITCODE; Pop-Location; exit $exit` | Node 22.18 | production build | `✓ 1683 modules transformed.` / `✓ built in 672ms` | 0 | PASS |
| Android | no Android source or Gradle change | Web-only scope | not applicable | `SKIPPED / not applicable` |  | SKIPPED |

Baseline 首次在系统 Node 20.11.1 且缺 `node_modules` 时得到 component/client `ERR_MODULE_NOT_FOUND`、build `vite is not recognized`；随后使用固定 Node 22.18/npm 10.9.3 执行 `npm ci --include=optional` 后，以上 baseline PASS。失败历史不计为 PASS。

## Oracle Gate

- Required：No
- Reason：批准范围为纯 Web route/navigation/component mode；禁止 Server/SQL/transaction/Schema 修改。
- Status：`SKIPPED / not applicable`；不得称为 PASS。

## Real-device Gate

- Required：No
- Device/scenario：无 Android 或真实采集变更；`SKIPPED / not applicable`。

## Rollback

- Code rollback：revert Task commits 或应用专属 `ROLLBACK.sh` 到另一固定 base 副本；
- Configuration rollback：无配置变更；
- Data recovery：无数据/Schema 变更；
- Irreversible items：无。

## Human Decision Points

- merge 与 release 必须由 Product Owner 明确批准；
- 若实现要求改变 canonical Task、服务端权限语义、Schema 或产品入口范围，停止并请求决定。

## Stop Condition

- Review `ACCEPT`、Draft PR 和 Hosted CI 完成后停止在 merge 前；
- 出现产品语义冲突、服务端/Schema 需求或无法维持两 mode 严格互斥时停止；
- 不启动 `WEB-PRODUCT-SURFACE-ALIGN-001` 或任何后续任务。

## Evidence

- Original evidence：固定 base 源码与 Product Owner 批准事实；原始 Task blob SHA-256 在 `VERIFICATION.txt` 记录，未覆盖。
- Derived artifacts：`WEB-NAV-EXCEL-CONSOLIDATION-001-verification/`；`MODIFIED_FILE` 保持本 Task 当前 changed 内容，`DIFF_FILE.patch` 仅包含 base→候选的业务/治理目标文件，四制品自身不进入自引用补丁。
- Dev evidence：新增 mounted/router test 覆盖 `/excel` redirect、query fallback/route abort、task-import/library-match 互斥、ProductList permission entry；既有 mounted/Node/Python/Web build 全部 PASS。
- Historical environment failure：系统 Python 3.10 的 pydantic 1 与缺少 `loguru`/`jwt` 使 discovery 失败（exit 1）；改用既有 `D:\work\PDD_con_data\.venv-t001\Scripts\python.exe`（pydantic 2.13.4）后 full PASS，失败不计为通过。
- Oracle / Real-device：均为 `SKIPPED / not applicable`；本 Task 未触及 Server/SQL/transaction/Schema 或 Android。
- Review findings：fixed Head `03839ad09adb885008e453391275f7191f7134d1` Independent Review `ACCEPT`，无 P0/P1/P2；首轮唯一 P1 为 build 命令缺少工作目录，已修复并复现通过。
- Commit / PR：功能 Head `cc9190e030421659ab76a6d8c974f4302daf6667`；Review evidence Head `03839ad09adb885008e453391275f7191f7134d1`；Draft PR 待 Control 创建，禁止 merge。
