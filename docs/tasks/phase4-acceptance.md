# Phase 4 管理与可观测性验收

- 日期：2026-08-17
- 分支：`codex/phase4-management-observability`
- 状态：PASS；停止在 Phase 4，不进入 Phase 5

## 1. 完成能力

- Quarantine：服务端分页、时间/原因/错误码/平台/商品身份/Task/Job/版本筛选；详情关联脱敏 Raw、QualityGate、原始 field sources、Task/Job/Attempt/Device 和可识别 Product。
- Product Snapshot：不可变历史时间线展示价格、销量、状态、SKU、Parser/规则/质量状态、字段来源及既有 Diff。
- 质量指标：服务端真实聚合总量、PASS、QUARANTINE、通过率、Parser failure、identity/title/price 缺失、price 缺失、SKU 异常、Parser/规则版本表现、错误码集中度和基础异常提示。
- 执行轨迹：Task 摘要 → Jobs → Attempts → Task/Attempt Events，关联 Device、trace、错误、Snapshot/Quarantine 计数。
- 真实分页：Quarantine、Snapshots、Tasks、Products、Jobs、Attempts、Events 均由 Oracle `COUNT + OFFSET/FETCH` 执行并使用稳定双键排序。
- Web：质量仪表板、Quarantine 工作台、Product Timeline、Task Trace 均具备 loading、error/retry、empty 和 ID 导航。

## 2. 主要 API 与页面

管理 API 共 9 个，统一前缀 `/api/management`：Quarantine 2 个、Snapshot 1 个、Metrics 1 个、Trace/Jobs/Attempts/Task Events/Attempt Events 5 个。

页面：`/quality`、`/quarantines`、`/products/:id/timeline`、`/tasks/:id/trace`；商品库和任务详情已增加入口。

## 3. 指标定义

指标口径以 `docs/decisions/phase4-management-observability.md` 为准。特别说明：PASS 等于 `ACCEPTED=1`（包含 warning）；Parser failure 使用精确解析错误码，避免把其他 QualityGate 拒绝误算为 Parser failure；SKU missing warning 不计 SKU abnormal。

## 4. 实测结果

| 验证 | 结果 |
|---|---|
| Phase 4/分页/migration targeted | 18/18 PASS |
| Python 全量 unit | 146 tests PASS，10 个隔离 Oracle opt-in 按保护设计 skip |
| Android JVM | BUILD SUCCESSFUL，exit 0 |
| Web production build | 1673 modules transformed，PASS；仅既有大 chunk warning |
| 管理路由 | 9/9 注册；Job/Attempt 当页业务结果批量关联 |
| Python compileall / git diff check | exit 0 |
| 实际 Oracle 管理查询 | 21 QualityResult、14 PASS、7 Quarantine；分页、详情、Snapshot、版本和错误聚合成功 |
| 实际 Oracle 原列表分页 | Tasks total=56/page items=2；Products total=72/page items=2 |
| 故障注入轨迹 | Task 518 → failed Job → failed Attempt → `P4_INJECTED_TIMEOUT` Event 可完整定位；事务 rollback 后 Task count=0 |

当前会话没有设置专用 `T003_ORACLE_*` opt-in 变量，因此未把既有隔离 Oracle 全套作为普通单测误接到应用 Schema；Phase 4 的 Oracle 只读查询和 rollback-only 故障注入已在当前项目 Oracle 实际执行。Phase 1～3 写入代码未被 Phase 4 修改，Python/Android/Web 回归继续通过。

## 5. GAP、技术债务与 P0

- P1-06 管理查看/定位闭环关闭；人工修复/重放仍为后续需求。
- P2-03 Task/Job/Attempt/Device/trace/error/quality 关联关闭。
- P3-03 核心后台列表假分页关闭。
- 未发现新增 P0，未新增静默错误路径。
- `P4_001_MANAGEMENT_INDEXES` 已在实际 Oracle 连续执行两次，状态 applied，7/7 索引存在。
- 技术债务：JSON platform/identity/error 过滤在规模增大后可能需要虚拟列或 JSON search index；旧 Task Detail 的 items/logs 属于既有详情 payload，后续可独立拆分页；Web 仍有既有大 chunk warning。

## 6. Phase 5 条件

Phase 4 目标已完成，Phase 5 具备技术启动条件，但必须单独批准；本次不进入 Phase 5。

## 7. Agent 与效率复盘

- Sol：冻结 API/指标语义、改造 Tasks/Products 分页、跨模块联调、真实 Oracle 故障注入、文档与最终验收。
- Luna：一次定向调查 + 一次后端实现，负责 9 个 API、真实聚合和 query tests。
- Terra：一次定向调查 + 一次 Web 实现，负责 4 个页面、导航和 Web build。
- 避免冲突：Luna 独占新 Server 文件，Terra 独占 Web 管理页；Sol 只在契约冻结后处理既有列表和最终联调。
- 有效纠错：联调阶段一次发现 metrics shape/时间参数不一致并立即收敛；一次识别 `PARSE_STATUS=failed` 不能直接代表 Parser failure。
- Token 使用量：粗估约 4 万 tokens（非账单口径）。
- 执行时间：约 25 分钟；最终 Python/Android/Web/Oracle/migration 验证约 10 分钟。
