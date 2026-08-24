# Phase 6A Collector Abstraction 验收

> 日期：2026-08-19
> 基线：`a3d499594b2bd2bf52a43e31ca6440f63b9a8cd6`
> 范围：权威 Android Agent 与服务端质量入口；旧桌面链保持隔离，不接入 JD、淘宝、1688。

## 1. 结果

```text
CollectionTask
  -> CollectorRegistry.require(platform)
  -> Collector / SearchCollector / DetailCollector
  -> RawResult / unified result
  -> platform Parser
  -> global Normalizer / QualityGate
  -> Product / Snapshot or Quarantine
```

- 正式 ADR：`docs/decisions/phase6a-collector-contract.md`。
- Android Contract/Registry：`android_collector/app/src/main/java/com/collector/pdd/collector/`。
- 服务端 Contract/Registry：`server/collectors/`。
- PDD 结构迁移：`PddCollector` 包裹既有 `PddActions`、`DetailReader`、`GoodsLinkResolver`、页面分类和错误映射；未重写 PDD 算法。
- 核心入口：`TaskEngine` 只按 `platformCode` 查询 Registry，不直接 import/构造 PDD 实现；服务端 QualityGate 通过 Registry 的 identity/capability 处理统一模型。

## 2. 耦合调查与迁移边界

### 迁移前主要耦合

- `TaskEngine` 直接构造 `PddActions`，并直接编排分享链、`goods_id`、SKU 面板、参数、图片、`DetailReader` 和访问状态。
- `server/data_quality.py` 内含 `platform == "pinduoduo"` 数字 ID 规则。
- `server/product_quality.py` 内含 PDD 页面文案、`yangkeduo.com` 与 `goods_id` URL 规则。
- `CollectConfig`、API/Web 默认值和旧桌面链仍存在 PDD 兼容命名；它们不是本阶段重写目标。

### 保持平台无关

- Job / Attempt / Lease / Checkpoint / Outbox / reconciliation。
- Tenant / Enterprise / Workspace / device revoke / Quota ledger。
- Raw / Product identity / EnterpriseProduct / Snapshot / Provenance / Diff / Quarantine 持久化。
- receipt/idempotency、Management 查询、任务终态聚合。

### 进入 PDD Adapter

- App 入口、搜索/排序/列表候选、详情 UI 顺序与返回栈。
- 页面分类、`goods_id`/URL/分享链 identity、SKU/价格/销量/图片解析。
- PDD Parser version、字段 provenance、平台错误到系统错误的映射。

### 不抽象的业务逻辑

- Lease fencing、checkpoint、receipt、Job/Task 完成不变量。
- 服务端权威 QualityGate、Snapshot/Quarantine 事务语义。
- Tenant/Quota/权限、Excel target matching、任务优先级和人工审核。
- 拟人访问与反风控策略；旧桌面链去留仍由 BL-301 决策。

## 3. Contract

- Identity：`platform + platformProductId + optional platformSkuId`；不以 URL、标题、位置或数组下标充当 identity。
- Capability：`SEARCH`、`DETAIL`、offset/cursor pagination 与有限 dynamic fields；Optional 字段结合 capability 区分“不支持”和“本次缺失”。
- Registry：显式进程内注册、平台名 trim/lowercase、重复注册拒绝、未知平台 fail-fast；当前只注册 PDD。
- Search：统一 `SearchRequest` 与 `SearchResult(candidates,nextCursor)`，核心不读取 PDD 原始响应。
- Detail：统一 collection/parse request 与 `DetailCollectionResult`；Raw evidence 对核心保持 opaque。
- Error：`TEMPORARY_FAILURE`、`AUTH_REQUIRED`、`RATE_LIMITED`、`ITEM_NOT_FOUND`、`ITEM_UNAVAILABLE`、`PARSE_ERROR`、`DATA_QUALITY_FAILURE`、`MANUAL_INTERVENTION_REQUIRED`，另有 Registry/Capability fail-fast 错误。

## 4. Compatibility 与中立扫描

- Android before/after：同一输入经旧 `DetailReader`/`ProductQualityGate` 与 Registry→PddCollector 比较 Product、parser/quality 状态、missing/warning，完全相同。
- 服务端 fixture 与质量回归继续验证 identity、核心字段、Snapshot canonical/hash/diff、Quality/Quarantine 语义；既有 Phase 1/2 测试继续验证 receipt、checkpoint 和 completion 行为。
- `TaskEngine.kt`、`server/data_quality.py`、`server/product_quality.py` 中无 `PddActions`/`DetailReader`/`GoodsLinkResolver` import，无 `if platform == pinduoduo`。
- PDD 特例集中在 `PddCollector`；平台 catalog、兼容 wire/schema 默认、测试 fixture 与隔离旧桌面链不计为核心实现分支。

## 5. 成本与停止点

- 未增加外部依赖、数据库表、常驻服务、动态插件系统或基础设施。
- 未修改 Job、Quality、Tenant、Quota 的业务语义，未大改 Web。
- 未正式接入 JD、淘宝或 1688；Phase 6A 完成后停止，Phase 6B 需单独批准。

## 6. 测试记录

### Phase 6A targeted

- `tests.test_phase6a_collectors + tests.test_phase6a_oracle`：`Ran 6 tests ... OK`，无 skip。
- 新增两项真实 Oracle compatibility：
  - accepted：Registry/PddCollector identity、Product Master、两个 Snapshot、QualityResult、price Diff 与 idempotent replay；
  - rejected：QualityGate/Quarantine、无正常 Snapshot 与 idempotent replay。

### Phase 1～6A Oracle

- canonical strict gate 已纳入 Phase 5 与 Phase 6A；最终修复后的独立 Oracle gate：`Ran 40 tests in 114.334s ... OK`，`SUMMARY PASS=1 FAIL=0 BLOCKED=0 STRICT=True`。
- 最终全量中的 Oracle gate：`Ran 40 tests in 121.880s ... OK`，无 skip。
- 覆盖 Task/Job/Attempt/Lease/Checkpoint/receipt、Product identity、Snapshot、Provenance、QualityGate、Quarantine、Diff、Tenant isolation、device revoke、quota 并发与幂等语义。

### 全量回归

- Python：`Ran 170 tests in 87.615s ... OK`。
- Oracle：`Ran 40 tests in 121.880s ... OK`，无 skip。
- Android JVM：`50 tests / 0 failures / 0 errors`，`BUILD SUCCESSFUL in 13s`。
- Web production build：`built in 656ms`，PASS。
- 统一严格入口：`SUMMARY PASS=4 FAIL=0 BLOCKED=0 STRICT=True`。

### 最终 Sol Review 修复与复验

- 公共 `DetailCollector` 已收敛为统一 `collect` 边界；分享链、URL 展开、图片识别等 PDD 私有概念全部留在 `PddCollector`。
- `SearchRequest` 已携带排序/预取语义；搜索排序、翻页、候选恢复由 Adapter 内部完成，入口按 `SEARCH`、`DETAIL`、`PRICE_SORT`、`SALES_SORT` capability fail-fast。
- 统一错误策略已区分有限重试、停止任务、失败单项与 fail-fast；认证、人工介入、解析/质量和不支持错误不再折叠成访问繁忙。
- PDD 风控仍映射统一系统错误，但保留原有 `busyResponse=stop/skip/retry`、有限重试和 `riskCooldownMs`；普通认证/人工介入继续停止任务。
- 未知平台或会话创建失败已进入统一 lifecycle 收口，确保本地 Task 终态、notification、完成回调和 `currentTaskId` 一致结束。
- 修复后按 `targeted -> Oracle -> full strict` 重跑：Android targeted `9/9 PASS`、Phase 6A Python/Oracle targeted `6/6 PASS`、Oracle `40/40 PASS`、全量 `PASS=4 FAIL=0 BLOCKED=0`；最终 Sol Review 无阻塞项。

## 7. 执行资源

- 最终修复后门禁 wall time：targeted `26.8s`、Oracle strict `116.0s`、full strict `228.2s`；不包含代码调查、两轮 Review 和文档/提交时间。
- Agent：Luna 负责耦合/Oracle 矩阵，Terra 负责 Contract/Registry/PDD 迁移与 Oracle compatibility，Sol 负责 ADR 与三轮最终 Review；最终 Review 为 `ACCEPT`、阻塞项 `0`。
- Token：当前执行环境未返回可核验的按 Agent token 计数，因此不写估算值。

## 8. 最终结论

- Phase 6A 的结构迁移及 Oracle compatibility 已验证，未发现 PDD 对外业务语义变化。
- 未增加 JD、淘宝、1688 或其他平台；未增加业务功能，未进入 Phase 6B。
- **Phase 6A ACCEPTED**。
- **Phase 6B UNBLOCKED**，仅解除门禁，不代表已启动或获准接入第二个平台。
