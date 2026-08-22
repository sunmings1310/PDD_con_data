# Codex 会话交接基线

> 更新日期：2026-08-23
> 用途：新 Agent 的当前状态入口；只记录仍影响开发决策的事实。
> 治理入口：[`../PRODUCT.md`](../PRODUCT.md) → 本文 → Accepted ADR → Active Task/验收 → [`architecture.md`](architecture.md) → 历史规划证据。完整规则见 [`../AGENTS.md`](../AGENTS.md) 和 [`../WORKFLOW.md`](../WORKFLOW.md)。

## 1. 项目目标

把现有 PDD 数据采集系统建设为可构建、可恢复、可验证、可追溯、租户隔离且可持续扩展的平台。当前权威链路是：

`Vue Web → FastAPI/Oracle → Android Agent → PDD App → Raw/Quality/Product/Snapshot/Media → Web`

旧 PyQt6/BitBrowser/SQLite 桌面链仍是兼容/待决策链，不是新增能力的默认落点。新增工作必须保持网络、业务、数据分层，优先修根因，不做无关重构。

## 2. 当前稳定 baseline

| 项目 | 当前值 |
|---|---|
| 当前分支 | `codex/repo-governance-baseline`（治理分支，业务稳定基线仍为下行提交） |
| 稳定提交 | `13b4301` (`feat: unify raw evidence and product data contracts`) |
| 上游 | `origin/codex/phase6-multiplatform-collector`，与本地提交一致 |
| 主线关系 | 尚未 merge；`main`/`origin/main` 当前停在 `a3d4995` |
| 当前开发状态 | `REPO-GOV-001` 处于 `REVIEW`；仅建立治理文档、规则、模板和首版 CI，等待独立 Review，不自动 merge |
| Golden Sample | PDD `platform_product_id=985843042423` |

本地真实 Raw Capture、验证产物和本地数据库不是版本库 baseline：`server/data/`、`artifacts/`、`pdd_system.db` 均被忽略。仓库只提交实现、脱敏 fixture、契约、ADR 和测试。

## 3. 已完成并验收的阶段

| 阶段 | 状态 | 核心结果 | 权威证据 |
|---|---|---|---|
| Phase 1 | ACCEPTED | 成功语义、质量门禁、持久 Outbox、幂等 Receipt/Finish Manifest | `docs/tasks/phase1-acceptance.md` |
| Phase 2 | ACCEPTED | Task/Job/Attempt/Lease/Checkpoint、恢复、Pause/Resume、Reconciliation | `docs/tasks/phase2-acceptance.md` |
| Phase 3 | ACCEPTED | Product Master/Snapshot、Raw、Quality、Provenance、Diff、Quarantine | `docs/tasks/phase3-acceptance.md` |
| Phase 4 | ACCEPTED | 管理查询、真实分页、质量指标、Trace 与只读工作台 | `docs/tasks/phase4-acceptance.md` |
| Phase 5 | ACCEPTED | Enterprise/Workspace、私有 EnterpriseProduct/事实边界 | `docs/tasks/phase5-acceptance.md` |
| Phase 5.5 | ACCEPTED | Enrollment/Revoke、旁路 TenantContext、配额账本、真实 Oracle 门禁 | `docs/tasks/phase55-acceptance.md` |
| Phase 6A | ACCEPTED | Collector Contract/Registry/PddAdapter；PDD 行为兼容 | `docs/tasks/phase6a-acceptance.md` |
| 商品一致性 P0 | ACCEPTED | Canonical Read Model、DTO/Edit 边界、动态事实不可普通编辑 | `docs/decisions/2026-08-20-product-field-semantics-p0.md`、`13b4301` |
| Raw/Schema/SKU 调查 | 当前范围完成 | 可重放 Raw、字段盘点、SKU_PANEL 直接证据和通用动态维度契约 | `docs/backlog.md` 最新记录、`13b4301` |

Phase 6B 虽满足 Phase 6A 技术前置，但 **NOT STARTED**，且没有本阶段授权。

## 4. 当前正在做什么

当前没有正在实施的业务 Phase。2026-08-23 执行 `REPO-GOV-001`，范围仅为治理文档、规则、GitHub 模板和 CI；未修改业务代码、Schema 或生产配置。治理分支完成本地验证后停在独立 Review，业务状态仍等待 SKU 证据充分性门禁和后续明确批准。

本次治理建立：`PRODUCT.md`、`WORKFLOW.md`、Task/ADR/PR 模板、根与模块级 `AGENTS.md`、无真实 Oracle 的核心 CI，以及历史/当前文档的明确权威边界。最近完成的业务工作是：

治理验收记录见 [`tasks/REPO-GOV-001.md`](tasks/REPO-GOV-001.md)。

1. Raw Capture 的脱敏、哈希、Manifest、离线 Replay 与不可变证据边界；
2. 多样本 Schema Discovery 和 Field Observation 状态模型；
3. SKU_PANEL 的直接证据采集、动态维度/组合观察和 ProductAttribute/SKU 分离；
4. 商品数据一致性 P0：统一名称、规格、价格、DTO、读取模型及编辑策略；
5. Android durable upload mapper 收口，Web 两个编辑窗口改为请求 Edit DTO。

当前动作是等待 **SKU 证据充分性门禁** 和后续明确批准，不进行 Oracle 大规模模型迁移。

## 5. 已冻结的重要架构决策

- **成功与可靠性**：HTTP 2xx 不等于业务成功；只有已确认商品/图片和 Finish Manifest 才能完成任务。Lease 失效的旧执行者不能写入新事实。
- **任务状态**：服务端状态机是权威；设备运行状态不等于任务业务状态。见 `T003-authoritative-task-state.md`、`phase2-job-attempt-lease.md`。
- **租户边界**：只允许全局去重最小平台 Identity；EnterpriseProduct、Snapshot、Raw、Quality、Media 等业务事实按 Enterprise/Workspace 私有。见 `phase5-product-master-tenancy.md`。
- **Collector 边界**：平台点击、页面文案、Selector、原始错误和解析留在 Adapter；Task/Job/Quality/Tenant 核心不得依赖 PDD 实现。见 `phase6a-collector-contract.md`。
- **商品字段**：`platform_title`、`canonical_name`、`product_attribute_spec`、`sku_dimensions`、`sku_combinations` 含义固定；兼容列只在权威 Mapper 中翻译。见 `2026-08-20-product-field-semantics-p0.md`。
- **价格**：五种价格语义及 Effective Price 优先级只由 `server/product_contract.py` 决定；API、Report、Excel、Web 不得各自重排。
- **读取与编辑**：Detail/Capture 从 Canonical Product Read Model 派生；Edit DTO 只含稳定可编辑字段。价格、销量、库存、促销、SKU observed price、Raw、Snapshot 不得由普通 PUT 覆盖。
- **SKU 与属性**：ProductAttribute 是商品参数；SKU 只能来自 SKU_PANEL 的直接购买选择证据。不得从“规格”文本推导 SKU，不得伪造平台 SKU ID，不得把主商品价格复制到所有组合。
- **观察状态**：`VALUE(0)` 与 `NOT_OBSERVED` 不同；Raw 永不被 derived replay 回写。Field Observation Model 当前仍是 Proposed，正式 Oracle 表达需 P1 再确认。
- **Legacy 兼容**：`SJZQ_PRODUCT` 暂留；Legacy 无法建立 Raw/Snapshot 来源时返回 `provenance unavailable`，不得伪造来源。

## 6. 当前 P0 / P1 / P2

这里指 2026-08-20 商品数据一致性专项，不要与早期全局 Backlog 优先级混淆。

| 优先级 | 状态 | 范围 |
|---|---|---|
| P0 | DONE / ACCEPTED | 统一字段和价格语义、Canonical Read Model、Detail/Edit/Capture/Snapshot DTO、稳定字段白名单、动态事实保护、核心 Mapper 收口、Golden Sample 一致性 |
| P1 | NOT STARTED / REQUIRES APPROVAL | 正式 ProductAttribute、SKU Dimension、SKU Combination、SkuSnapshot Schema，以及兼容 migration |
| P2 | NOT STARTED | 历史回填、污染 SKU 清洗、完整 Manual Override 生命周期 |

其他仍开放但不应抢占当前门禁的技术债统一登记在 [`gaps/current.md`](gaps/current.md)。

## 7. 禁止提前开始

- 不进入 Phase 6B，不接入 JD、淘宝、1688 或其他第二平台；
- 不执行 P1/P2 正式 SKU/ProductAttribute 大规模 Oracle migration；
- 不回填或清洗历史商品/SKU，不直接删除疑似污染数据；
- 不实现完整 Manual Override，除非有独立业务需求和 ADR；
- 不用 UI 临时 Mapper、字符串截取或列表 row 复制绕过 Canonical DTO；
- 不修改 Raw/Snapshot，不允许普通编辑接口覆盖动态观察；
- 不为了消除警告升级大型依赖、做缓存/队列/多实例或无指标性能重构；
- 不 merge 当前分支，除非用户另行明确批准。

## 8. 下一验收门禁

下一门禁是 **SKU 证据充分性门禁**，不是 Schema migration。至少补齐并复核：

1. 三维及以上购买维度样本；
2. disabled/unavailable option 与 combination；
3. SKU 图片和组合的可靠关联证据；
4. 平台 SKU ID 的直接证据，或继续明确 `NOT_OBSERVED`；
5. v1.0.82 真机回归及 Raw → Replay → DTO 一致性；
6. 现有 Phase 1～6A 回归、P0 Golden Sample、Legacy 读取继续通过；
7. 结论从 `SKU MODEL NEEDS MORE EVIDENCE` 转为可评审的 Schema Proposal。

门禁未通过时，只能继续采样、证据分析、契约/测试修正；不得创建正式 SKU Oracle 表。

## 9. 门禁通过后的下一任务

先提交 P1 的独立设计与批准请求：冻结 ProductAttribute/SKU Dimension/Combination/SkuSnapshot 的 Oracle Schema、兼容读取、迁移/回滚、租户键、不可变性和 Legacy 路径。获得明确批准后才实施小步 migration；仍不自动进入 P2 或 Phase 6B。

## 10. 回归入口与最近证据

统一入口：

```powershell
.\scripts\test-baseline.ps1 -Suite all -Strict
```

Oracle 套件要求隔离 T003 环境变量和 Phase 1～6A opt-in flags；缺少环境时必须报告 BLOCKED，不能把 skip 当通过。`13b4301` 提交前最近一次 P0 回归为 Python `191 tests / OK (skipped=18)`、Android `BUILD SUCCESSFUL`、Web `1673 modules transformed / build PASS`；Golden Sample `985843042423` 的实际 Oracle 只读一致性验证为 PASS。Phase 6A 最终严格门禁证据为 Oracle `40/40 PASS`、总计 `PASS=4 FAIL=0 BLOCKED=0`。

首版 GitHub Actions 位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)：PR/push 核心门禁运行 Markdown/YAML、离线 Python、Android JVM 和 Web build；Oracle job 只有仓库变量 `ORACLE_CI_ENABLED=1` 时才启用，并强制检查全部专用环境输入。托管 runner 的首次实际结果需在 PR 中记录，不能用本地验证冒充 hosted CI PASS。

## 11. 文档权威边界与历史处置

| 文档 | 唯一职责 |
|---|---|
| [`../PRODUCT.md`](../PRODUCT.md) | 产品范围、用户、场景与不变量 |
| 本文 | 唯一当前实现状态 |
| [`backlog.md`](backlog.md) | 唯一任务状态账本 |
| [`roadmap.md`](roadmap.md) | 未来阶段与依赖，不直接授权实施 |
| [`gaps/current.md`](gaps/current.md) | 当前开放缺口入口 |
| [`decisions/`](decisions/) | 架构决定及替代关系 |
| [`tasks/`](tasks/) | 单个 Task 的范围、执行和证据 |
| [`architecture.md`](architecture.md) | 当前实际架构 |
| [`../WORKFLOW.md`](../WORKFLOW.md) | 开发、测试、Review、merge 与发布流程 |

2026-08-23 已将根 `GAP.md`、`gap-analysis.md`、`issues.md`、`milestone.md` 标记为 Historical/Superseded，并指向当前权威入口；`backlog.md` 和 `roadmap.md` 分别更新为当前任务状态与未来阶段入口。历史正文不删除、不批量重写，以下矛盾作为来源证据继续保留：

- `docs/roadmap.md` 的 M0/M4 正文仍保留 2026-08-13 状态，例如缺 JDK、Web 无法构建、Oracle/迁移 UNKNOWN、当前目录不是 Git 仓库；这些已被 Phase 1～6A 验收和 Git history 推翻。末尾 Phase 6A 记录较新，应优先解释。
- `docs/roadmap.md` 的“跨阶段决策清单”仍把工具链、Oracle migration、秘密注入、Lease、商品身份、质量契约等标为 UNKNOWN；其中多项已有 Accepted ADR 和实现，清单未回填。
- `GAP.md` 主结论和完成度矩阵仍以 Phase 1/2 初期为口径，声称 Lease、ProductSnapshot、企业隔离未完成，并列出 T004/T005/T007/T008 为下一任务；同文件尾部又记录 Phase 3～6A 已完成，前后矛盾。
- `docs/backlog.md` 的旧 Phase 表格仍包含 `BL-011 DetailReaderTest TODO` 等历史状态；顶部已明确其不覆盖当前状态，且“等待批准后进入 Phase 3”的旧结论已显式替代。
- `docs/backlog.md` 的 Phase 5/5.5 “停止、不进入下一 Phase”属于当时验收停止点，已被之后 Phase 6A 的独立批准取代，不应当作当前禁止 Phase 6A 的依据。
- `docs/architecture.md` 的 Canonical Read Model、Raw、SKU_PANEL 和 Phase 6A 内容与当前实现基本一致；其中部署守护、多实例和负载均衡标为 UNKNOWN，当前没有相反证据，应继续保留为未知项。
- 根和模块级 `AGENTS.md` 已扩充为当前强制规则；第一轮不批量重命名历史 ADR/Task。

发生冲突时，不要自行猜测或批量重写历史文档；先以当前代码、测试、Accepted ADR、验收报告及本文为准，再发起小范围文档修订。
