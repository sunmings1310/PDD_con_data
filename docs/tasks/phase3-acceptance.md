# Phase 3 数据质量验收

- 日期：2026-08-17
- 分支：`codex/phase3-data-quality`
- 状态：PASS；停止在 Phase 3，等待 Phase 4 批准

## 1. 交付范围

| 能力 | 实现 |
|---|---|
| 稳定商品身份 | `SJZQ_PRODUCT_MASTER`，唯一键 `(PLATFORM_CODE, PLATFORM_PRODUCT_ID)` |
| 采集事实 | `SJZQ_PRODUCT_SNAPSHOT` 只追加；同 request key replay 返回原 Snapshot |
| 原始证据 | `SJZQ_RAW_COLLECTION` 保存脱敏 payload、hash、Task/Job/Attempt/Device 引用 |
| 字段来源 | `SJZQ_FIELD_PROVENANCE` 按 Snapshot/field 保存 source/ref/transformation |
| 质量结果 | `SJZQ_QUALITY_RESULT` 保存 pass/warning/quarantined、错误、缺失与版本 |
| 隔离 | `SJZQ_DATA_QUARANTINE` 保存原因、证据、版本和原任务引用，不创建正常 Snapshot |
| 差异 | `SJZQ_SNAPSHOT_DIFF` 检测 price/sales/SKU/availability/title/shop |
| 版本 | Parser version 来自 Agent；服务端实际规则版本固定为 `phase3-1` |
| Migration | `SJZQ_SCHEMA_MIGRATION` + `P3_001_DATA_QUALITY`，additive、可重入 |

SKU 当前作为 Snapshot 内的不可变集合；在 Collector 能稳定提供平台 SKU ID 前，不创建会错误合并的 SKU 主档。旧 `SJZQ_PRODUCT` 保留兼容，新的 master/snapshot ID 回写关联；未执行历史合并、删除或破坏性迁移。

## 2. 成功、重复与失败语义

1. strict upload 必须先通过当前 Task/Lease fence，再运行服务端 QualityGate。
2. PASS/WARNING 在同一事务写 legacy Product、Master、Raw、Snapshot、QualityResult、Provenance、Diff 和 receipt；提交后才 ACK。
3. 同 idempotency key + 同 payload 返回原 receipt/Snapshot；同 key + 不同 payload 返回 conflict。
4. 不同 key 代表不同确认采集事实，因此追加 Snapshot；内容相同允许空 Diff，但不覆盖历史。
5. Quality failure 写 Raw + QualityResult + Quarantine，返回稳定拒绝；不创建正常 Product/Snapshot。
6. 已持久化 ACK/Quarantine 的纯 replay 不产生新写入，允许在 Lease 释放后返回原结果；任何新业务写入仍受当前 Lease 约束。

## 3. 数据质量指标口径

Phase 4 可直接以 Phase 3 表生成管理指标：

- **质量接受率**：`QUALITY_RESULT.ACCEPTED=1 / 全部 QUALITY_RESULT`。
- **隔离率**：`DATA_QUARANTINE / RAW_COLLECTION`。
- **必填字段完整率**：accepted 结果中 `MISSING_FIELDS_JSON=[]` 的比例。
- **关键来源完整率**：可信 Snapshot 中 identity/title/price 以及有值 sales/shop/SKU 对应 provenance 均存在的比例；当前门禁目标为 100%。
- **SKU 完整率**：可信 Snapshot 中 `SKU_JSON` 非 `null` 的比例；缺失记录 warning，不伪造。
- **销量完整率**：可信 Snapshot 中 `SALES_NUM IS NOT NULL` 的比例。
- **商品重复率**：同 `(platform, platform_product_id)` Master 数量必须为 1；数据库唯一约束目标为 0 次冲突污染。
- **变化率**：各 `*_CHANGED=1 / 非首条 Snapshot Diff`。
- **错误分布**：按 Quarantine `ERROR_CODES_JSON/FAILURE_REASON` 聚合。

## 4. 验收证据

| 层 | 结果 |
|---|---|
| Python | 135 tests，PASS；10 个 Oracle opt-in 在 unit 层按设计 skip |
| Oracle integration | 32 tests，PASS；含 Phase 3 2 个真实事务测试 |
| Android JVM | `BUILD SUCCESSFUL`，exit 0 |
| Web build | 1665 modules transformed，PASS；保留大 chunk warning |
| Migration rerun | 连续两次 `ensure_schema_patches()`，`PHASE3_MIGRATION_RERUN_OK`，exit 0 |
| 固定质量 fixture | 10 个离线 case 全通过 |

真实 Oracle Phase 3 测试验证：一个 Master、两条不可覆盖 Snapshot、receipt replay 不增行、parser/rule version 可查询、关键 provenance 存在、价格变化生成 Diff；质量拒绝重复提交只生成一个 Quarantine 且正常 Product/Snapshot 为 0。测试数据按唯一 tag 清理。

## 5. GAP 与技术债

### 已关闭/收敛

- P1-01 主档/快照/身份去重：关闭。
- P1-05 NULL/来源/版本不可追溯：关闭。
- P1-06 后端统一门禁与隔离：关闭后端范围；管理处置 UI 留 Phase 4。
- P2-01 fixture 基线：关闭。
- P2-04 Phase 3 migration 版本化：本阶段关闭；旧 patch 尚未全部迁入版本框架。

### 保留

- 历史 `SJZQ_PRODUCT` 重复记录未回填或合并，避免未经批准的数据破坏。
- SKU 缺稳定平台 ID，暂不建立 SKU 主档/SKU Snapshot 分表。
- Quarantine 缺查询、审核、处置 UI；数据已为 Phase 4 准备。
- 原始证据保留期、归档与删除策略尚无业务决定。
- 旧 migration 每次检查会重建兼容 view，虽可重复且不影响数据，仍需纳入统一 migration 版本体系。
- Web 仍有大 chunk warning；与 Phase 3 数据正确性无关。

## 6. Phase 4 启动条件与建议

Phase 4 具备启动条件：质量事实、错误原因、版本、来源和 diff 均已持久化，任务/Job/Attempt/Lease 语义继续通过回归。推荐顺序：

1. Quarantine 列表/详情/审核/重试工作台，所有操作走状态和审计入口。
2. Product Master + Snapshot 时间线、字段 provenance 和变化展示。
3. 上述指标的查询 API、趋势和告警阈值；先定义分页与容量目标。
4. Task/Job/Attempt 轨迹与质量事件关联视图。
5. API/Web 自动测试与权限测试，禁止 UI 直接任意更新质量事实。

## 7. Agent 效率复盘

- **调查复用**：复用了 Phase 1/2 的上传调用链、receipt/lease 语义、Oracle 环境与测试入口；没有重新全仓审计。
- **分工**：Luna 只做 schema/上传契约定位与最终针对性 Review；Terra 只负责独立 schema/migration 文件；Sol 负责契约、QualityGate、跨上传事务、Oracle 验证与最终 Review。
- **并行控制**：同时保持 2 个高价值子任务；核心 `products.py` 只由 Sol 修改，避免并行冲突。
- **重复工作**：未出现重复全仓搜索；发生一次必要的 schema/SQL 精确列名复核。Oracle 初次全回归暴露旧 fixture 缺 title provenance，修正后只重跑 Oracle 层。
- **Review/测试**：中途只跑相关 46-test/fixture/Phase3 Oracle；实现稳定后才跑 Python、Oracle、Android、Web 全回归，没有每次小改都全量执行。
- **主要上下文消耗**：跨 Phase 1/2/3 的 `products.py` 事务/幂等 Review 和 Oracle 失败定位；schema DDL、fixture 与文档为次要消耗。
- **下一 Phase 降本**：先冻结管理查询 API/权限矩阵，再让一个 Agent 做后端列表、一个 Agent 做 Web 页面；共用同一 response fixture；只在跨模块收口时做一次 Sol 全 Review。

Token 使用量按本阶段对话与工具输出粗估约 **4 万 tokens**（非账单口径）。Phase 3 使用 3 个子 Agent 任务（2 个调查/Review、1 个 schema 实现），未启动重复探索任务。按首个 Phase 3 文件创建时间至最终验收计算，总执行时间约 **20 分钟**；其中两轮最终 Python/Oracle/Android/Web 与 migration 验证约 4 分钟。
