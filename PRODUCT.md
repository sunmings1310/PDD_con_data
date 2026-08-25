# Product Baseline

> 状态：Current product authority
> 更新日期：2026-08-25
> 当前实现状态见 [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)。

当前可信业务基线为 `main@02234f2`：Accepted Phase 6A、Raw Capture foundation、Product Consistency P0、Canonical Product Contract 及已验收 lifecycle/recovery 修复已进入主线。Generic SKU runtime、正式 P1 SKU/ProductAttribute Schema 与 Phase 6B 不属于当前批准范围。

## 项目目标

建设长期可维护的数据采集与比价系统，使采集任务可恢复、结果可确认，商品事实可追溯、可验证、可版本化，并在受控边界内支持企业和 Workspace 隔离。

## 目标用户

- 负责创建、审核和观察采集任务的运营管理员；
- 需要查询商品、快照、质量与异常证据的数据使用者；
- 负责设备、任务可靠性、数据质量和审计的工程及运维人员。

## 核心业务场景

1. 管理员创建并审核采集目标，Android Agent 领取任务并执行拼多多搜索与详情采集。
2. 服务端确认 Raw、质量结果、商品身份、快照和媒体持久化后，任务才进入成功终态。
3. 用户比较同一商品在不同采集时点的可信事实，并追溯字段来源、Parser 与质量规则版本。
4. 失败或不可信数据进入可解释的隔离记录，供后续复核而不污染正常数据。

## V1 范围

- Vue 管理端、FastAPI/Oracle 服务端和 Android Agent 组成的拼多多采集主链；
- Task / Job / Attempt / Lease / Checkpoint / Outbox 的可靠执行与恢复；
- Product、Snapshot、Raw evidence、Field Source、Quality Result、Diff、Quarantine；
- Enterprise / Workspace 数据边界、设备注册与撤销、配额和审计；
- Collector Contract/Registry 及 PDD Adapter 的受控扩展边界。

## V1 非目标

- Phase 6B、第二平台 Collector 以及京东、淘宝、1688 接入；
- 未通过证据门禁的正式 SKU/ProductAttribute Oracle 模型；
- 历史数据回填、污染清洗、破坏性迁移或生产数据删除；
- 完整动态插件系统、完整管理平台重构或无限后台常驻保证；
- 旧 PyQt6/BitBrowser/SQLite 桌面链的新能力扩展。

## 核心业务对象

- **Enterprise / Workspace / User / Role**：租户、工作空间与访问边界；
- **CollectionTask / CollectionJob / CollectionAttempt**：用户目标、稳定执行单元和一次执行尝试；
- **Lease / Checkpoint / Outbox / Receipt**：执行权、已确认进度、可靠投递和服务端确认；
- **Product / ProductSnapshot**：稳定商品身份与某一时点的不可变事实；
- **Raw Collection / Field Source / Quality Result / Quarantine**：原始证据、字段来源、质量判定和异常隔离；
- **Collector / Adapter**：跨平台契约与平台特定实现。

## 关键产品不变量

1. 页面完成、Parser 返回对象或 HTTP 2xx 均不等于业务成功；只有服务端确认持久化的 receipt/manifest 才允许 Job/Task 成功。
2. Task、Job、Attempt、Lease、Checkpoint、租户和业务结果以服务端 Oracle 状态为真相；客户端状态只用于执行和恢复。
3. 过期或被 reclaim 的 Lease 不能覆盖新 Attempt。
4. 平台商品身份与采集事实分离；动态价格、销量、库存、促销和 SKU 进入不可变 Snapshot/Raw，不由普通编辑覆盖。
5. 商品身份至少由平台与平台商品 ID 确定；不得用标题、店铺或规格错误合并商品。
6. 异常或不可信结果进入 Quarantine 并保留原因、版本和证据；不得静默丢弃或污染正常数据。
7. Enterprise/Workspace 私有事实不得跨租户读取或写入。
8. 平台点击、Selector、页面文案和原始解析留在 Adapter；核心调度、质量和租户模型不得依赖 PDD 实现。

## 成功标准

- 未确认数据导致的错误 Complete、重复业务事实、过期 Lease 覆盖和异常页伪商品均为 0；
- 关键字段来源、Parser 版本、质量规则版本和差异可查询；
- 受支持的 Python、Android JVM、Web 与专用 Oracle 门禁可由固定命令重复执行；
- 缺少外部门禁环境时明确报告 `BLOCKED`/`SKIPPED`，不冒充 `PASS`。

## 需要人工批准的产品决策

- 改变产品成功语义、商品身份、Snapshot 不可变性或跨企业共享边界；
- 进入第二平台、Phase 6B、正式 SKU/ProductAttribute 模型或旧桌面链去留实施；
- 破坏性 Schema 迁移、已有数据删除/回填/清洗或生产环境操作；
- 需要真实账号、密钥、人工验证，或两种方案会形成明显不同产品行为的选择。

上述变化必须先形成 Task/ADR 并获得明确批准，再更新本文和 `docs/CURRENT_STATE.md`。
