# ADR：Phase 5 Product Master 租户边界

- 状态：Accepted / Implemented（用户于 2026-08-17 确认方案 C）
- 日期：2026-08-17
- 决策者：Phase 5 Sol Tech Lead
- 前置：Phase 1～4 ADR、`GAP.md`
- 范围：Product identity、Enterprise 私有采集事实、跨企业比较与删除语义

## 1. 决策摘要

推荐采用 **C：全局最小商品身份注册表 + Enterprise 私有 Product + Workspace 私有采集事实**。

当前 `SJZQ_PRODUCT_MASTER` 不应继续同时承担“全局平台商品身份”和“租户可见商品主档”。Phase 5 将概念拆分为：

1. `PlatformProductIdentity`：全局内部注册表，仅保存 `(platform_code, platform_product_id)`、内部主键和最小生命周期字段；不保存标题、店铺、价格、销量、SKU、来源、质量、采集时间线或企业关系；不直接通过租户 API 暴露。
2. `EnterpriseProduct`：Enterprise 私有商品主档，以租户内不透明 ID 对外；唯一键为 `(enterprise_id, platform_identity_id)`，保存企业对该商品的可见状态、保留策略和删除状态。
3. `ProductSnapshot`、Raw、QualityResult、Quarantine、Diff、Provenance、图片和 Collection Data：均为 Enterprise 私有，并具有明确 `enterprise_id`；可被 Workspace 拥有的事实同时具有 `workspace_id`。
4. 默认比价只在同一 Enterprise 的授权 Workspace 集合内进行。任何跨 Enterprise 的对标或聚合必须作为未来独立数据产品，具有明确授权、去标识化阈值和审计，不能复用普通租户查询。

因此，对问题“Product Master 是否跨 Enterprise 共享”的精确回答是：**平台商品身份键可以全局去重，但租户可见 Product Master 与全部动态/采集事实不得跨 Enterprise 共享。**

## 2. 背景与不变量

Phase 3 以 `(platform_code, platform_product_id)` 建立全局 `SJZQ_PRODUCT_MASTER`，Snapshot 通过 `MASTER_PRODUCT_ID` 串成跨所有采集的时间线。该模型适合单一业务空间，但在多企业下会产生三类问题：

- `MASTER_PRODUCT_ID`、`FIRST_SEEN_AT/LAST_SEEN_AT` 和跨租户 `PREVIOUS_SNAPSHOT_ID` 可泄露其他企业的采集存在性与时间；
- Diff 可能把 Enterprise B 的 Snapshot 当作 Enterprise A 的上一条事实；
- 直接按 Master 查询、分页或聚合容易越过租户边界。

Phase 5 必须满足：Enterprise A 的普通用户、Agent 和管理员不能通过 ID、搜索、分页、指标、Trace、Quarantine、Snapshot、日志或导出观察 Enterprise B 的私有数据。前端隐藏不是隔离边界；服务端查询和数据库键必须携带租户条件。

## 3. 方案比较

| 评估项 | A. 每 Enterprise 独立 Product | B. 全局 Product Master + 私有 Snapshot | C. 全局最小身份 + 私有 EnterpriseProduct（推荐） |
|---|---|---|---|
| 数据隔离 | 最直观；所有商品数据天然带租户 | Snapshot 可隔离，但 Master 元数据、ID 和跨租户时间线易泄漏 | 私有主档和事实天然隔离；全局层不承载租户业务数据 |
| 数据重复 | 平台身份及主档重复最多 | 身份重复最少 | 只共享极小身份键；业务数据按企业保留 |
| 比价业务 | 企业内简单；跨企业需额外映射 | 全局关联简单，但容易误把跨企业数据当作可见数据 | 通过内部 identity 对齐，默认仍保持企业内比较 |
| 后续多平台 | 每租户重复平台映射 | 全局平台 identity 扩展方便 | 同 B，且平台 identity 与租户业务模型解耦 |
| 存储成本 | 身份和主档有少量重复；Snapshot 本来就占主要空间 | 最低，但节省主要集中在很小的 Master 行 | 接近 B；每企业每商品只增加一条轻量映射 |
| 查询复杂度 | 租户内最低，跨企业最高 | 表面最低，实际每条事实查询仍必须防泄漏 | 多一次受控 join，但查询边界清晰、可统一封装 |
| 企业隐私 | 最强 | Master 首末发现时间、状态及共享 ID 可能泄漏策略 | 全局层不保存发现者/时间线；租户 API 只见私有 ID |
| 数据授权 | 简单但难以复用合法公共数据 | 容易把技术共享误当授权共享 | identity 共享不授予事实访问权，授权边界明确 |
| 删除企业数据 | 可直接按租户删除 | Master 与跨租户链路使删除和保留含混 | 删除 EnterpriseProduct 与全部私有事实；全局孤儿 identity 可延迟清理 |
| 未来 SaaS 化 | 隔离好但重复模型笨重 | 成本好但合规和产品语义风险最高 | 隔离、去重、授权和未来数据产品之间最平衡 |

## 4. 推荐模型

```text
PlatformProductIdentity (global, internal only)
  identity_id
  platform_code
  platform_product_id
  UNIQUE(platform_code, platform_product_id)

EnterpriseProduct (tenant private)
  enterprise_product_id
  enterprise_id
  identity_id
  status / retention_state / deleted_at
  UNIQUE(enterprise_id, identity_id)

ProductSnapshot / RawCollection / QualityResult / Quarantine / SnapshotDiff
  enterprise_id NOT NULL
  workspace_id NOT NULL
  enterprise_product_id (when identity is known)
  task_id / job_id / attempt_id
```

数据库约束应保证子记录的 `enterprise_id/workspace_id` 与其父 Task、Job、Attempt、EnterpriseProduct 一致。Oracle 不使用会话隐式默认租户来替代显式谓词；应用层 repository/service 的每个读取和写入都接收不可省略的 `TenantContext`。

租户 API 不返回全局 `identity_id`。资源定位使用 `enterprise_product_id`，并以 `(enterprise_id, resource_id)` 查询；跨租户 ID 与不存在资源返回同样的 404 语义，避免枚举确认。

## 5. Product、Snapshot 与 Diff 行为

- 同一平台商品被两个 Enterprise 采集时，内部可复用一条 `PlatformProductIdentity`，但会创建两条互不可见的 `EnterpriseProduct`。
- Snapshot 链和 `PREVIOUS_SNAPSHOT_ID` 只允许指向同一 `enterprise_id + workspace_id + enterprise_product_id` 的可信 Snapshot；不会跨企业生成 Diff。
- Enterprise 内是否允许跨 Workspace 比较由显式授权决定。基础实现按 Workspace 隔离时间线；未来可增加 Enterprise 级受权视图，但不能通过省略 `workspace_id` 自动放宽。
- Quarantine 即使能识别平台商品 ID，也只关联当前 EnterpriseProduct；不得借全局 identity 查出其他企业是否采集过该商品。
- 质量指标、Dashboard、分页总数和导出均从租户私有事实聚合，不从全局 identity 计数。

## 6. 删除、保留与授权

删除 Enterprise 时，按 `enterprise_id` 清除或按保留策略封存全部 Workspace、Membership、Task/Job/Attempt、Raw、Snapshot、Quarantine、日志、导出与 EnterpriseProduct。全局 `PlatformProductIdentity` 不证明任何企业关系；当它不再被任何 EnterpriseProduct 引用时，可由独立可审计清理任务删除。

共享 identity 仅表示两个租户提交了相同的公共平台业务键，不代表任一租户获得另一租户的 Snapshot、采集时间、字段来源或统计。未来跨企业数据产品必须引入独立授权对象、用途限制、最小聚合阈值和退出/删除传播机制，本 ADR 不预授权该能力。

## 7. 迁移影响

该决策产生明显不同的产品行为；用户确认后已实施 Phase 5 migration。

确认后建议采用 additive-first：

1. 将现有 `SJZQ_PRODUCT_MASTER` 收敛为内部 `PlatformProductIdentity` 语义，移除其租户 API 可见性；
2. 新增 EnterpriseProduct，并为现有单租户数据建立默认 Enterprise/Workspace 映射；
3. 为私有事实增加不可空租户键，先回填、校验，再启用约束；
4. 按租户重建 Snapshot predecessor 与 Diff 边界，禁止继承跨租户 predecessor；
5. API 先双读校验、再切换到私有 ID，最后停止旧 `MASTER_PRODUCT_ID` 路由；
6. migration 使用新版本 ID 和固定 checksum，可重复执行；不得修改 Phase 3/4 已发布 checksum。

## 8. 被拒绝的替代方案

- 拒绝 A 作为默认方案：它隔离最简单，但重复平台身份、跨平台映射和未来合法聚合成本更高，且并未减少占主要存储的私有 Snapshot。
- 拒绝原始 B：共享包含首末发现时间、状态或可查询 ID 的 Product Master 会把技术去重扩大成数据共享，并容易形成跨租户 Snapshot/Diff 链。
- 拒绝只在 Web 层隐藏 Master：不能覆盖 API、Agent、导出、指标、后台任务和直接 ID 访问。

## 9. 待确认的产品行为

请确认是否接受以下行为：

1. 租户只能看到自己的 EnterpriseProduct ID，不看到全局 identity/master ID；
2. 默认比价与时间线不跨 Enterprise，且基础版本按 Workspace 隔离；
3. 相同平台商品在不同 Enterprise 的标题、价格、销量、SKU、采集时间和质量状态完全独立；
4. 跨企业基准比较不属于 Phase 5 基础能力，未来必须单独授权和聚合化设计。

确认后，Phase 5 实施将以本 ADR 为约束继续；若要求租户直接共享 Product Master 或跨企业比较，需要先修订本 ADR 的授权、泄漏面和删除语义。
