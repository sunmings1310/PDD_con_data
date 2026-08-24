# ADR：Phase 6A Collector Contract 与 PDD Adapter 边界

- 状态：Accepted（Phase 6A）
- 日期：2026-08-18
- 决策者：Phase 6A Sol Tech Lead
- 前置：Phase 1～5.5 ADR、`docs/roadmap.md`、`GAP.md`
- 范围：Android 主采集链与服务端质量入口的最小多平台边界

## 1. 背景与目标

Phase 1～5.5 已稳定 Task / Job / Attempt / Lease / Checkpoint / Outbox、Product / Snapshot / Quality / Quarantine、Tenant 与 Quota 语义，但当前运行时仍直接依赖 `PddActions`、`DetailReader`、拼多多 ID/URL 规则和 PDD 错误页面文案。平台码存在并不等于平台边界已经建立。

Phase 6A 只把已验证的 PDD 行为包入最小 Collector Adapter，并冻结一个可由“PDD + 一个未来第二平台”验证的契约：

```text
CollectionTask
  -> CollectorRegistry.require(platform)
  -> Collector / SearchCollector / DetailCollector
  -> RawResult
  -> platform Parser
  -> global Normalizer
  -> global QualityGate
  -> Product / ProductSnapshot（或 Quarantine）
```

本阶段的成功标准是依赖方向改变而业务行为不变，不是重新实现 PDD，也不是提前实现通用插件平台。

## 2. 核心决策

### 2.1 依赖方向与执行所有权

核心流程只依赖 Collector Contract、统一模型、系统错误和能力声明：

- Task / Job 继续拥有用户意图、调度、Attempt、Lease、Checkpoint、重试与终态；它们只传递 `platform` 和统一请求，不解释平台页面、原始响应或错误码。
- `CollectorRegistry` 依据规范化后的精确 `platform` 查找 Collector。TaskEngine 不直接构造 `PddActions`，服务端 QualityGate 不直接导入 PDD 模块。
- Collector 拥有平台入口、会话内动作顺序、搜索、详情获取、身份解析、平台 Parser 和平台错误映射。
- Normalizer、QualityGate、Product / Snapshot 持久化继续是全局层；Collector 不决定 Job 是否完成，不提交 Lease/receipt，不绕过租户与配额事务。
- Android 首版类型位于 `com.collector.pdd.collector`；服务端契约位于 `server/collectors/contract.py`，PDD 实现位于 `server/collectors/pdd.py`。现有根 package 名称属于应用历史命名，不构成核心层可依赖 PDD 实现的许可。

### 2.2 最小接口

Phase 6A 冻结以下概念和名称，具体语言可使用 `interface`、`data class`、`dataclass` 或等价只读类型：

```text
Collector
  platform: String
  capabilities: CollectorCapabilities
  createSession(...) -> platform session

SearchCollector
  search(SearchRequest) -> SearchResult
  restore(SearchRequest) -> SearchRestoreResult

DetailCollector
  collect(DetailCollectionRequest) -> DetailCollectionResult

CollectorRegistry
  register(Collector)
  require(platform) -> Collector
```

`PddCollector` / `PddCollectorSession` 是 PDD Adapter。它们委托既有 `PddActions`、`DetailReader`、链接/页面解析和访问保护逻辑，不复制其算法。公共 session 只暴露 start/reset/finish、关键词间隔、候选浏览等高层生命周期动作；SKU、店铺、分享链、滚动、排序、拟人桥接和 URL helper 均为 PDD Adapter 私有实现。会话类型是运行时资源边界，不进入 Task payload 或持久化模型。

`SearchRequest` 只表达平台无关意图：关键词、排序、最大结果数、有限预取页数以及可选 cursor；PDD 点击、控件文字、滚动和页面节点不属于该请求。`SearchResult` 至少包含统一候选项、可选下一 cursor 和终止信息，上层不得读取 PDD 原始 response。仅为同一平台会话继续导航所需的 candidate position/opaque handle 可以留在本次执行上下文，不能持久化成 Product identity。

`DetailCollectionRequest` 使用 SearchResult 中的统一候选或本次会话的 opaque candidate position；候选已知稳定 ID 时同时携带 `ProductIdentity`。现有 PDD 搜索卡片可能先以页面位置导航、再从分享链/网络证据解析稳定 ID；该导航和解析过程是 `PddCollector` 内部动作。稳定身份解析完成前不得创建 Product。

`RawResult` 是 Collector 输出边界，不等同于平台原始 response。它携带统一 identity、动态字段候选、page/parse 状态、字段来源、parser version、必要的受控原始证据引用和本次 capability snapshot；平台 JSON、无障碍节点、控件文案和平台异常码不得泄漏到 Task / Job API。原始证据按既有保留、脱敏和租户规则落入 Raw Collection。

### 2.3 Identity

统一身份定义为：

```text
ProductIdentity(platform, platformProductId)
SkuIdentity(ProductIdentity, platformSkuId)  # 仅在稳定 ID 存在时
```

- `platformProductId` 是该平台稳定商品 ID；URL、标题、搜索序号、页面节点和内部 Product 主键均不是平台商品 ID。
- `platformSkuId` 为 Optional。只有平台证据提供可跨采集稳定复用的 SKU ID 时才填写；禁止用 SKU 名称、数组下标或组合 hash 伪造。
- 各平台 ID 格式校验和 URL/ID 对应关系由对应 Collector 负责。全局 Normalizer 只做非空、去首尾空白和结构规范化；QualityGate 不出现 `if platform == ...`。
- Oracle 既有全局最小身份键 `(platform_code, platform_product_id)` 以及 Phase 5 Enterprise 私有事实边界保持不变。

## 3. Capability 模型

`CollectorCapabilities` 是某个 Collector 版本的只读声明，由下列有限枚举组成：

- `CollectorCapability.SEARCH`
- `CollectorCapability.DETAIL`
- `CollectorCapability.PRICE_SORT`
- `CollectorCapability.SALES_SORT`
- `CollectorCapability.PAGINATION_CURSOR`
- 支持的 identity 种类（至少 Product；稳定 SKU ID 可选）
- `DynamicField` 集合，例如 `SALES`、`ORIGINAL_PRICE`、`SKU_STOCK`、`PROMOTION`

能力声明用于三个位置：

1. Registry/调用入口在执行前拒绝该平台不支持的操作；Search sort 也必须先验证对应 capability；
2. 请求构造和 API 展示可只开放实际能力；
3. Normalizer/QualityGate 区分“平台不支持”与“平台声称支持但本次缺失”。

核心身份、title 和至少一个有效价格仍是当前 Product/Snapshot 成功契约的必需字段。销量、原价、SKU stock、promotion 等平台差异使用 `Optional` 字段并结合 `DynamicField` 解释：

- capability 未声明：值应为空，不能因缺失直接产生 PDD 风格 warning；
- capability 已声明但本次为空：按统一、版本化质量规则给出 warning/error；
- capability 未声明但返回值：拒绝或记录契约偏差，不能静默扩张 schema。

不得用大量 `if platform == ...` 代替 capability，也不得把任意字符串 map 当作无限可扩展能力系统。新增 enum 必须由真实第二平台 fixture 或已存在 PDD 字段证明。

## 4. Parser 与 Normalizer 边界

### 平台 Parser / Adapter 负责

- 平台页面/响应分类、选择器、控件文案、网络字段和 embedded state；
- 平台原始字段到统一候选字段的语义映射；
- 商品 ID、SKU ID、URL/ID 对应关系与搜索候选解析；
- 平台货币/数量原始表示的解释、SKU 面板结构、售罄/不存在/登录/验证/繁忙识别；
- 字段 provenance 的原始来源、`parser_version` 与平台错误映射。

### 全局 Normalizer 负责

- 统一模型的空值、字符串、Decimal/数值、集合和 canonical JSON 表达；
- 公共字段别名收敛、受控 source 类型收敛和 Snapshot 稳定序列化；
- Optional 字段、capability snapshot 和统一 availability/page/parse 状态的结构化；
- 供 Diff、QualityGate 和存储复用的确定性输出。

Normalizer 不识别“已拼”、`goods_id`、`yangkeduo.com`、PDD 页面结构或平台错误码。Parser 也不决定 accepted/quarantined，不写 Product/Snapshot，不改变全局质量阈值。

`QualityGate` 只消费统一模型和能力声明，继续执行 Phase 3 的服务端权威规则：身份、title、价格、数值范围、来源、page/parse 状态和可选字段一致性。PDD 特有 ID/URL 校验从全局 gate 下沉到 `PddCollector`；accepted upload 的 Raw → QualityResult → Product/Snapshot/Quarantine 单事务不变量保持不变。

## 5. Registry 设计

`CollectorRegistry` 使用进程内显式注册的 `platform -> Collector` 映射：

- platform 先执行统一的 trim/lowercase 规范化；空值、未知平台 fail fast；
- 同一 platform 重复注册必须失败，禁止后注册静默覆盖；
- `require(platform)` 返回唯一 Collector，核心流程不维护 PDD/JD/淘宝条件链；
- Registry 不保存会话、账号、Lease 或租户状态；这些状态通过调用上下文传给 `createSession`；
- 测试可以创建隔离 Registry 并注册 fake collector，证明核心流程的平台无关性。

本阶段使用静态装配 PDD Collector，不做反射、动态 classpath 扫描、远程插件下载、运行时热加载、ServiceLoader/DI 框架或数据库驱动代码发现。

## 6. System Error Mapping

平台异常必须在 Adapter 边界映射为 `SystemCollectorError`，并通过 `CollectorException`（或同义结果类型）传递。Phase 6A 冻结：

| 系统错误 | 统一语义 | 默认调度含义 |
|---|---|---|
| `TEMPORARY_FAILURE` | 网络、页面加载或短暂平台故障 | 可按既有策略有限重试 |
| `AUTH_REQUIRED` | 会话登录/认证失效 | 停止当前动作，等待认证 |
| `RATE_LIMITED` | 频率限制、访问繁忙或明确节流 | 受控退避，不无限循环 |
| `ITEM_NOT_FOUND` | 稳定 identity 对应商品不存在 | 当前 item 确定失败 |
| `ITEM_UNAVAILABLE` | 售罄、下架或暂不可购买 | 形成统一 availability/终态 |
| `PARSE_ERROR` | 已取得证据但平台 Parser 无法产生合法中间结果 | 保留证据并隔离/失败 |
| `DATA_QUALITY_FAILURE` | 统一 QualityGate 拒绝 | Quarantine，不创建正常 Snapshot |
| `MANUAL_INTERVENTION_REQUIRED` | 验证码、挑战或无法自动恢复的访问状态 | 停止并进入人工处置 |
| `PLATFORM_NOT_SUPPORTED` | Registry 无该 platform | 创建/执行入口 fail fast |
| `CAPABILITY_NOT_SUPPORTED` | 请求超出 Collector 声明能力 | 执行前 fail fast |

平台原始异常码、页面文案和 selector 只能作为受控 evidence 留在 Adapter/Raw，不能成为 Job 状态、API 公共错误枚举或重试条件。是否重试仍由 Job 策略根据系统错误、Attempt 次数和 deadline 决定；Collector 不自行改变 Job 状态。QualityGate 生成 `DATA_QUALITY_FAILURE`，平台 Parser 不得借该错误跳过全局 gate。

为保持结构迁移前的 PDD 访问策略，Adapter 可在 `CollectorException` 上附带有限的、平台无关的 recovery hint；PDD 风控证据仍映射 `MANUAL_INTERVENTION_REQUIRED`，但 `RISK_POLICY` hint 让 Task 策略继续遵守既有 `busyResponse=stop/skip/retry`、有限重试和 `riskCooldownMs`。没有该 hint 的认证或人工介入错误仍停止任务。hint 不进入 Job/API 错误枚举，也不授权 Collector 改写 Job 状态。

## 7. PDD 迁移与 Compatibility Contract

`PddCollector` 是结构迁移层：

- 搜索/页面动作委托现有 `PddActions`；
- 详情解析委托现有 `DetailReader`；
- PDD 页面分类、identity/URL 规则和异常识别移入 PDD Adapter；
- `TaskEngine` 通过 Registry 获取 Collector/session；
- Registry 查询和 session 创建位于 Task lifecycle 收口范围内；未知平台或会话创建失败也必须落为确定终态、发送结束通知/回调并清理本地执行指针；
- 服务端 `product_quality.py`、`data_quality.py` 通过 Registry 做平台规则调用，不再内嵌 PDD 条件。

迁移前后的同一 fixture 和任务输入必须验证：

1. Product identity 相同；
2. title、价格、销量、店铺、SKU、availability 等核心字段相同；
3. Snapshot canonical 语义、provenance 和版本相同；
4. QualityGate accepted/warning/quarantined、错误码和 missing fields 相同；
5. Quarantine 是否创建及原因相同；
6. PDD 原始异常到既有任务行为的映射等价；
7. receipt、checkpoint slot、Job/Task completion 和 replay 行为相同。

Compatibility test 是 PDD 行为冻结依据。若抽象要求改变 Parser 语义、Quality Rules、访问策略或任务完成行为，该变化退出 Phase 6A，另立决策与版本；不得把预期差异伪装成 Adapter 重构。

## 8. 保持平台无关与不得抽象的业务逻辑

以下模块保持平台无关，且不得依赖 PDD 实现：

- Task / Job / Attempt / Lease / Checkpoint / Outbox / reconciliation；
- TenantContext、Enterprise/Workspace、设备执行权、Quota/ledger；
- Raw/Quality/Quarantine、Product identity 注册、EnterpriseProduct、Snapshot、Diff、provenance；
- receipt/idempotency、事务边界、Management 查询和任务终态聚合。

以下业务逻辑不因 Collector 抽象而改写：

- Phase 1 成功不变量及“HTTP 2xx 不等于业务成功”；
- Phase 2 Lease fencing、迟到 Attempt 拒绝、checkpoint 与 completion 聚合；
- Phase 3 服务端权威 QualityGate、不可变 Snapshot、Quarantine 与 Diff；
- Phase 5/5.5 租户隔离、设备 revoke、配额 reservation/commit/release；
- 业务 target matching、任务优先级、deadline、人工审核和管理口径。

平台内的点击、返回栈恢复、搜索排序验证、分享取链、SKU 面板、页面文案和访问状态属于 Adapter；全局业务层只观察统一结果。拟人访问细节和反风控策略既不是 Collector Contract，也不在本阶段修改。

## 9. 非目标与成本控制

Phase 6A 明确不做：

- 接入或建立 JD、淘宝、1688 的正式 Collector、fixture、凭据或任务入口；
- 重写 PDD 搜索/详情流程、优化访问策略、改变 Parser/Quality 语义；
- 重设计 Job、QualityGate、Web、Enterprise 或存储架构；
- 建立动态插件、跨进程 Collector 服务、消息队列、缓存、新数据库表或新外部依赖；
- 为假设中的平台设计几十个接口、任意字段 DSL、通用 workflow engine 或协议协商系统；
- 把旧桌面采集链强行并入 Android 权威链。旧桌面链的正式定位仍按既有 ADR/roadmap 独立处理。

成本边界：复用现有 Android/FastAPI/Oracle 运行时和 fixture；Registry 为轻量内存映射；不增加云服务、基础设施、付费 API 或常驻进程。新增抽象必须有 PDD 当前耦合点或合理第二平台差异作为证据。

## 10. 验收与回滚边界

完成 Phase 6A 前必须通过：

- Contract/Registry/Capability/Error Mapping 单元测试；
- PDD Before/After compatibility fixture；
- 核心层扫描：无新增 PDD-specific import、field 或条件链；
- Phase 1～5.5 Python、Oracle、Android JVM、Web 全量回归；
- Registry 未知平台、重复注册、缺失能力和系统错误映射测试。

回滚以 Adapter 接入点为边界：保留既有 PDD 实现，由旧 TaskEngine 调用路径或本阶段前提交恢复；不得回滚或改写 Phase 1～5.5 schema、租户、配额、Job 或 Product/Snapshot 事实。回滚演练必须确认 PDD compatibility fixture 仍得到同一业务结果。

Phase 6A 完成后停止。只有上述契约由 PDD 完整验证、核心层扫描和全回归通过，才具备在独立 Phase 6B 用第二个平台验证 Contract 的条件；“具备条件”不代表本阶段已经接入第二平台。
