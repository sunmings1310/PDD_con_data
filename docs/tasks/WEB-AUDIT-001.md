# WEB-AUDIT-001：前端功能、数据可见性与产品流程审计

- **Task ID**：WEB-AUDIT-001
- **Title**：前端功能、数据可见性与产品流程审计
- **Status**：REVIEW

## Goal

梳理全部 Web 页面、路由、用户功能、API、Enterprise/Workspace 过滤、服务端处理、Oracle 数据源、展示字段、空态、错误态与刷新机制，并以近期任务 `1568` 只读核对 `Oracle → API → Web 请求 → 页面渲染`，查明采集成功但用户页面无数据的真实断点。

## Context

Product Owner 已批准本只读审计。`SKU-EVIDENCE-001` 保持 `REVIEW / SCHEMA REVIEW CANDIDATE`、固定 Head `39998723924760a5ea5c4143af15b49c648492e0`；调查性 SKU Raw 尚未启用正式 Generic SKU 展示，不得与普通 Task/Product/Snapshot/Quality 的可见性混为一谈。

## Scope

### Allowed

- 读取 Web、FastAPI、Oracle 查询实现和治理文档；
- 运行现有测试、Web production build、静态检查；
- 启动本地只读服务并检查浏览器请求；
- 对已批准测试 Oracle 执行只读查询，以任务 `1568` 为样本；
- 修改本 Task、`docs/backlog.md`、本审计报告及验证制品。

### Forbidden

- 修改前端、后端、API、Schema、migration、配置或业务数据；
- 保存密钥、真实账号或未脱敏 Raw；
- 创建 PR、merge、发布；
- 启动 Generic SKU runtime、P1 SKU/ProductAttribute Schema 或 Phase 6B。

## Non-goals

- 不实现任何 finding；
- 不重构页面或服务端；
- 不处置 Quarantine、不重放任务、不补采数据；
- 不把调查性 SKU Raw 误报为正式 SKU 产品数据。

## Dependencies

- `main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- `PRODUCT.md`、`WORKFLOW.md`、`docs/CURRENT_STATE.md`、`docs/backlog.md`
- 已批准测试 Oracle 的只读访问与任务 `1568`

## Affected Modules

- 只读：`web/`、`server/`
- 文档变更：本 Task、`docs/backlog.md`、`docs/tasks/WEB-AUDIT-001-report.md` 与验证制品

## ADR

- 不新增 ADR；审计若发现产品行为或租户边界决策，作为后续任务的人工决策点。

## Acceptance Criteria

- [x] 完整页面/路由/功能矩阵与 API/服务端/Oracle 数据源映射。
- [x] 记录 Enterprise/Workspace 过滤、展示字段、空态、错误态与刷新机制。
- [x] 使用任务 `1568` 复现并定位 `Oracle → API → Web` 真实断点。
- [x] 区分调查性 SKU Raw 与普通 Task/Product/Snapshot/Quality 可见性。
- [x] 按 P0/P1/P2/P3 输出可复现 findings、端到端用户流程与最小整改排序。
- [ ] 现有适用测试与独立 Review 完成，固定 clean Head。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `python artifacts/web-audit-001/query_1568.py`（ignored，只读调查脚本）及现有 handler/query 直接调用 | 已批准测试 Oracle；Task 1568；凭据仅经既有环境加载 | 映射完整且显式 rollback | Task 4/4；Product/Raw/Quality/Snapshot 各 4；default products 不含 1568，task filter 返回 4；`TRANSACTION=ROLLBACK` | 0 | PASS |
| Targeted | Snapshot identifier contract probe | `master_product_id=249`、`enterprise_product_id=237`、tenant 1/1 | 复现并定位假空态 | `WEB_LINK_ID=249 TOTAL=0 ... ID=237 TOTAL=1 SNAPSHOT_IDS=[410] TRANSACTION=ROLLBACK` | 0 | PASS（finding reproduced） |
| Module | `npm ci`; `npm run build` | Node v22.18.0 / npm 10.9.3 | production build 通过 | 1673 modules；`✓ built in 3.79s`；large-chunk warning 保留 | 0 | PASS |
| Full regression | `scripts/test-baseline.ps1 -Suite web -Strict` | 固定 Web 工具链 | Web strict gate 通过 | `[PASS] web-build: exit=0`; `SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Diff | `git diff --cached --check`; reverse apply check | Task 允许文档与完整 DIFF artifact | 无 whitespace error；patch 可反向验证 | `DIFF_CHECK_EXIT=0 PATCH_REVERSE_CHECK_EXIT=0` | 0 | PASS |

## Oracle Gate

- Required：Yes（只读调查，不是 migration Gate）
- Reason：必须以任务 `1568` 核对权威持久化事实与租户范围。
- Environment：已批准测试 Oracle；凭据只经现有环境注入，不写入报告。
- Command / result / exit：只读 Task 1568 query + handler contract，Task/Product/Raw/Quality/Snapshot 均存在；显式 `ROLLBACK`；exit 0，PASS。

## Real-device Gate

- Required：No
- Device/scenario：本 Task 不新增采样；复用已完成的任务 `1568` 证据。
- Command or steps / result：SKIPPED（审计差异不涉及 Android/真机实现）。

## Rollback

- Code rollback：不修改业务代码；删除或 revert 本 Task 的治理文档提交。
- Configuration rollback：无配置变更。
- Data recovery：只读查询，不写业务数据。
- Irreversible items：无。

## Human Decision Points

- 遇新账号、登录、OTP、CAPTCHA、人工操作或 P0 finding 立即停止并升级。
- 后续整改、产品流程变化、PR、merge、release 均需独立批准。

## Stop Condition

独立 Review 完成、固定 Head、工作树 clean 后停止；不创建 PR、不 merge、不发布、不直接修复 findings。

## Evidence

- Original evidence：当前源码、已批准测试 Oracle 中任务 `1568` 的只读查询结果（仅脱敏摘要）。
- Derived artifacts：[`WEB-AUDIT-001-report.md`](WEB-AUDIT-001-report.md) 与 `WEB-AUDIT-001-verification/`。
- Review findings：P0=0；P1=7；P2=2；P3=1。等待独立 Review。
- Commit / PR：Task 建立提交 `7e6c77335aaebf4fc021f4b039423feb7874bcc3`；最终 fixed Head 待 Review 后记录；PR 禁止。
