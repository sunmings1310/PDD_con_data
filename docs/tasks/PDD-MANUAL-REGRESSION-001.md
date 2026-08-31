# PDD-MANUAL-REGRESSION-001：关键业务闭环独立手工回归

- **Task ID**：PDD-MANUAL-REGRESSION-001
- **Title**：关键业务闭环独立手工回归
- **Status**：ACCEPTED / REGRESSION COMPLETE
- **Priority**：P0

## Goal

在当前 bind hotfix 运行态上，以浏览器、API、服务日志和隔离 Oracle 只读核对相互印证，完整检查最短业务闭环是否还有阻断问题；先形成可复现证据和分级 bug 清单，不在测试窗口修改代码。

## Context

- 运行基线：bind hotfix 最终代码 `892fa9faf224b3c3160d26dfcdd85bd65522209f`；Task/evidence wrapper `137a6f2a6fcb0978b8bcf9b0521cda1b4632f261`。
- 当前服务：从 hotfix worktree 启动的 `0.0.0.0:8080`；健康检查通过。
- 媒体目录联接是可回滚临时 workaround，不是 Accepted 实现；正式修复单列 `PDD-MEDIA-PATH-STABILITY-001`。
- 复用已有 Task、商品与采集结果，不重新登录拼多多、不重新采集。

## Scope

### Allowed

1. 冷启动、8080 单端口、前端资产身份、JWT/Oracle 配置完整性、登录/退出/刷新。
2. Enterprise/Workspace 上下文、权限、401/403/404 与跨上下文 stale 行为。
3. 设备注册/心跳、任务列表、任务详情和既有成功/未匹配/缺失字段结果展示。
4. 单条编辑保存、批量保存资料库、重复点击/幂等、失败回滚。
5. 商品资料库列表/详情/编辑、主图/多图 HTTP 读取及服务重启后持续可读。
6. Excel 统一入口、模板、校验、预览和创建请求前审核；不得实际启动新采集。
7. 导出、分页、筛选、empty/error/retry；浏览器控制台、Network、服务日志的 400/404/500 与旧 chunk 扫描。
8. Oracle 仅做目标链路的只读核对；测试自身不得写业务数据。

### Forbidden

- 测试窗口直接修改业务代码、Schema/migration、配置或数据库。
- 重新登录拼多多、重新采集、购物车、订单、支付。
- 把媒体目录联接写成正式修复，或混入 bind hotfix。
- 创建/merge 修复 PR、release、Generic SKU、P1 Schema、Phase 6B。

## Non-goals

- 不在本 Task 修复 finding；每个需要代码修改的问题独立建候选 Task，等待 Product Owner 批准。
- 不证明生产环境容量、长期稳定性或真机采集正确性。

## Dependencies

- `PDD-PRODUCT-CHANGE-BIND-HOTFIX-001` 尚未 merge；本回归是其 PR 前运行门禁。
- 当前受控登录会话、现有测试数据和本地服务必须保持可用。

## Affected Modules

- Web：认证、租户上下文、设备、Task、Product、Excel、导出、通用状态反馈。
- Server：auth、tenant、device/task/product/excel/media routes 与日志。
- Oracle：只读核对相关 Task/Product/Raw/Snapshot/Receipt/Change 状态。
- Runtime：单端口 Web dist、缓存/chunk、媒体目录配置。

## ADR

无。本 Task 只产出回归证据和候选 bug；媒体路径设计另建 Task/ADR。

## Acceptance Criteria

- [x] 十组测试矩阵逐项记录 `PASS/FAIL/BLOCKED/SKIPPED`，不得以 HTTP 200 代替业务正确。
- [x] 浏览器行为与 API、服务日志和已完成的持久化事实相互印证；未完成的 Oracle 深层核对明确为 `BLOCKED`。
- [x] 每个 finding 有复现证据摘要、影响、严重级别和建议归属 Task。
- [x] 明确当前 bind hotfix Draft PR 是否被阻断。
- [x] Independent Reviewer 对证据完整性和结论给出 `ACCEPT`。

## Test Plan

| # | Area | Expected | Actual | Status |
|---:|---|---|---|---|
| 1 | cold start / single-port / asset / login | 当前 Head 资源，认证刷新可恢复 | 单监听、health、当前 dist、登录刷新与退出跳转通过；退出后的自动重新登录因不读取凭据而 BLOCKED | PASS / BLOCKED |
| 2 | tenant / workspace / permission | headers 与服务端上下文一致，无越权/泄漏 | Legacy Enterprise / Default Workspace 下设备、任务、商品、质量数据一致；未认证受保护 API 返回 401 | PASS |
| 3 | device / heartbeat / task surfaces | 列表详情一致、状态可解释 | 在线设备 1；成功与失败 Task 列表、详情、进度和状态可解释 | PASS |
| 4 | existing results | success/not_matched/missing fields 均可见且不伪造 | Task 4286 显示 5 个 Snapshot/Raw/Quality；Task 4285 显示 not_matched 且正式结果为 0；本轮没有可识别的 missing-field 样本 | PASS / BLOCKED（missing-field 未执行） |
| 5 | edit / save-batch / replay / rollback | 保存成功、重复安全、失败不部分提交 | Product 1182 编辑并恢复通过；save-batch 源码无持久幂等，UI 选择保存后未取得可审计响应且仍为 draft | FAIL |
| 6 | product/media | list/detail/edit/image HTTP/restart 持续正确 | 73 条资料、Product 1182、图片 HTTP 200；Snapshot 1050 存在但 Product 时间线返回 0 | FAIL |
| 7 | Excel unified flow | template/validate/preview/canonical review，不 dispatch | 统一入口与两种 mode 契约通过；IAB file chooser/download event 无法完成真实上传/下载 | BLOCKED |
| 8 | export/pagination/filter/states | 可用且 empty/error 明确 | 商品分页和空状态通过；不存在 Task 重复错误并混杂空结果区 | PASS / P2 |
| 9 | cache/chunk/HTTP scan | 无旧资产、无未解释 400/404/500 | 54/54 当前 dist 文件 200 且字节一致，未知 chunk 404；未发现当前 chunk 404/500 | PASS |
| 10 | restart persistence/media config | 数据可读；媒体 workaround 与正式缺口分离 | 8080 从 PID 1188 重启到新进程，health 200；商品和媒体继续可读，但依赖临时 Junction | PASS / P1 |

## Oracle Gate

- Required：Read-only corroboration only；不得把未执行称为 PASS。
- Reason：核对 UI/API 展示对应的持久化事实，不执行 migration 或测试写入。
- Fixed Head SHA：`892fa9faf224b3c3160d26dfcdd85bd65522209f`
- Evidence：UI/API 只读事实已交叉核验；本 Task 不把另一个任务的 Oracle strict 失败冒充本 Task 只读 Oracle PASS。Oracle 深层核对未完成，标记 BLOCKED。

## Real-device Gate

- Required：No。
- Device/scenario：复用既有结果，不重新采集或登录平台。

## Rollback

- Code rollback：本 Task 不改业务代码；删除 Task-only evidence commit 即可。
- Runtime rollback：保持 bind hotfix 服务；媒体 workaround 按独立 runbook 处置，不由本 Task 改动。
- Data recovery：测试不得创建业务写入；若 UI 测试必须触发保存，只对既有目标执行幂等操作并核对审计，不删除数据。
- Irreversible items：无。

## Human Decision Points

- 任何代码修复、Schema/migration、bind hotfix Draft PR/merge、媒体正式方案均等待 Product Owner 批准。

## Stop Condition

- 矩阵、bug 分级、PR 阻断结论与 Independent Review 完成后停止。
- 出现认证失效、数据风险、不可逆写入或无法区分测试/正式数据时立即停止相应场景并记录 BLOCKED。

## Evidence

- Original：本轮连续发现的启动、租户、两处 Oracle bind 与跨 worktree media 问题。
- Derived：`docs/tasks/PDD-MANUAL-REGRESSION-001-verification/` 与外部脱敏 E2E evidence 目录。
- Review：`ACCEPT`（证据 Head `f6b939b38e34ab79d6f686465756cb527997d837`；后续仅增加 Review 状态包装）。
- PR：本回归不创建 PR。

## Findings

1. **P1 / `PDD-PRODUCT-TIMELINE-RESOURCE-ID-001`**：ProductList 的 `product_id=1182` 是 legacy ID、`master_product_id=600`；Snapshot 1050 的 `enterprise_product_id=588`。时间线接口把路由参数按 enterprise product ID 解释，导致现有 Snapshot 显示为空。
2. **P1 / `PDD-PRODUCT-SAVE-IDEMPOTENCY-001`**：`save-batch` 没有稳定 idempotency key/receipt；重复请求会刷新保存时间并重复写 change/op-log。UI 也缺少可证实的提交 ACK 展示。
3. **P1 / `PDD-HEALTH-METADATA-REDACTION-001`**：未认证 `/api/health` 暴露数据库网络端点与本机媒体绝对路径。
4. **P1 / `PDD-MEDIA-PATH-STABILITY-001`**：跨 worktree 图片读取依赖临时 Junction；写路径与媒体读取路径尚未统一为稳定配置。
5. **P2 / `PDD-TASK-DETAIL-NOT-FOUND-UX-001`**：不存在 Task 同时显示重复 `task not found` 和完整空结果/明细区。
6. **P2 / `PDD-WEB-ASSET-CACHE-POLICY-001`**：HTML 与 hash asset 缺少明确 `Cache-Control`。

## Gate Conclusion

- Bind hotfix 本身：**不因本回归 finding 阻断 Draft PR**；两处 Oracle bind 修复仍由其独立测试与 Review 证明。
- 整体资料保存/时间线/正式媒体闭环：**不具备 release 条件**；四个 P1 应独立修复后再做 release regression。
