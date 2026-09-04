# Product Requirements Baseline

> 状态：Current product authority
> Requirement baseline：`PRODUCT-REQ-V1`
> 对齐实现基线：`main@d6553704e2a73f4376f52de5bfd1054fa52923e4`
> 更新日期：2026-09-04
> 动态实现状态见 [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)，任务状态见 [`docs/backlog.md`](docs/backlog.md)。

本文是产品范围、稳定需求和产品不变量的唯一权威入口，不是发布计划、任务看板或测试报告。开发 Task 必须引用一个或多个已批准 Requirement ID，并把对应验收条件具体化；`Planned`、`Deferred` 或 `Unknown` 需求在实施前必须由 Product Owner 批准。

## 1. 状态与维护规则

- **Accepted**：产品语义已批准，可由 Task 在既有范围内实现或维护。
- **Planned**：方向已记录，但尚未批准启动实现。
- **Deferred**：明确延后，不得由当前 Task 顺带实现。
- **Unknown**：证据或产品决定不足，不得猜测为已批准行为。
- Requirement ID 一经发布不得复用；语义变化通过新增 ID 或显式替代关系记录。
- 动态排期只写入 [`docs/roadmap.md`](docs/roadmap.md)，任务状态只写入 [`docs/backlog.md`](docs/backlog.md)，实现状态只写入 [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)。
- 架构与事务细节保留在 Accepted ADR；逐次命令、测试输出和证据保留在 Task，不复制到本文。

## 2. 项目目标、用户与范围

### 项目目标

建设长期可维护的数据采集与比价系统，使采集任务可恢复、结果可确认，商品事实可追溯、可验证、可版本化，并在受控边界内支持 Enterprise 与 Workspace 隔离。

### 目标用户

- 创建、审核和观察采集任务的运营管理员；
- 查询商品、历史快照、质量与异常证据的数据使用者；
- 负责设备、任务可靠性、数据质量、权限与审计的工程和运维人员。

### V1 范围

- Vue 管理端、FastAPI/Oracle 服务端和 Android Agent 构成的拼多多采集主链；
- Task / Job / Attempt / Lease / Checkpoint / Outbox 的可靠执行与恢复；
- Product、Snapshot、Raw、Field Source、Quality、Diff 与 Quarantine；
- Enterprise / Workspace 数据边界、设备注册与撤销、配额和审计；
- Collector Contract/Registry 及 PDD Adapter 的受控扩展边界。

### V1 非目标

- Phase 6B 与第二平台 Collector；
- 未通过证据和决策门禁的正式 SKU/ProductAttribute Oracle 模型；
- 历史回填、污染清洗、破坏性迁移或生产数据删除；
- 完整动态插件系统、全站管理平台重构或无限后台常驻保证；
- 旧 PyQt6/BitBrowser/SQLite 桌面链的新能力扩展。

## 3. 稳定产品需求

### 3.1 医疗商品采集（MED）

#### MED-001 — 医疗输入保真
- **状态**：Accepted
- **目标/价值**：药品和医疗器械输入在导入、匹配与下发过程中不被静默改写或丢弃。
- **范围**：保留批准文号/注册号、品名、规格和生产厂家；支持混合证件类型与特殊字符（包括 `●`）。
- **验收**：合法行逐行具有可解释状态；原始文本可追溯；Excel“规格”只作为 ProductAttribute 候选。
- **约束**：不得把输入规格直接推导为 SKU 维度、组合或平台 SKU ID。

#### MED-002 — 目标身份匹配门禁
- **状态**：Accepted
- **目标/价值**：避免把推荐或相似商品误当成用户目标。
- **范围**：批准文号/注册号、品名、规格、厂家参与可解释匹配；候选不匹配与完全无候选使用不同原因码。
- **验收**：不匹配候选不能进入购买/SKU 面板；Item 以非重试 `not_matched` 终结；Raw/Snapshot/成功统计不产生伪结果。
- **约束**：不得仅凭标题片段、URL、主图或主价格确认身份。

#### MED-003 — 真实账号只读边界
- **状态**：Accepted
- **目标/价值**：真实采集保持最小、可审计且不改变交易状态。
- **范围**：受控登录会话可执行搜索、详情与获批的只读面板观察。
- **验收**：证据明确操作范围、时间与退出路径；未发生订单或支付。
- **约束**：禁止加入购物车、确认订单、提交订单或支付；验证码、风控和登录失效必须停止。

### 3.2 Excel 与统一任务创建（EXCEL）

#### EXCEL-001 — 单一 canonical Task 创建契约
- **状态**：Accepted
- **目标/价值**：手动输入与 Excel 导入共享同一配置、审核、幂等与提交语义。
- **范围**：来源→解析/校验/去重→候选选择→采集配置→审核摘要→统一提交→Task Detail。
- **验收**：两种来源生成同构 canonical payload；ACK 丢失重试复用相同 submission/payload；用户编辑后生成新提交身份。
- **约束**：页面或兼容 Excel API 不得形成第二条任务下发真相。

#### EXCEL-002 — 行状态、去重与上下文栅栏
- **状态**：Accepted
- **目标/价值**：每行都具有明确、可恢复、可解释的提交状态。
- **范围**：matched、multiple、unmatched、invalid、duplicate、excluded 与 choice-required；tenant/workspace/platform/route generation fence。
- **验收**：未明确排除的 blocked/duplicate 行会阻止提交；多候选必须显式选择；旧响应不能覆盖新上下文。
- **约束**：不得通过静默过滤让非法、重复或未决行进入提交。

#### EXCEL-003 — 任务导入与资料库查库分离
- **状态**：Accepted
- **目标/价值**：用户清楚区分创建采集任务与查询/导出已有商品。
- **范围**：任务创建页的 embedded 模式只产出 draft rows；资料库模式负责批量查库/导出；旧 `/excel` 仅作兼容跳转。
- **验收**：任务模式无导出和直接下发；资料库模式无任务创建；生产 Web 不调用旧直接下发端点。
- **约束**：服务端兼容 route 的删除另立 Task。

### 3.3 关键词与字段来源（LINEAGE）

#### LINEAGE-001 — 搜索关键词端到端血缘
- **状态**：Accepted
- **目标/价值**：能够回答“用户输入什么、系统实际搜索什么”。
- **范围**：原始输入→canonical payload→Task/Item→Job/Attempt→Android 搜索→Raw/结果展示。
- **验收**：每个执行单元可追溯原始与规范化关键词；任何合成或回退关键词有明确来源标签。
- **约束**：不得用日志中的临时文本覆盖用户原始输入。

#### LINEAGE-002 — 关键字段 provenance
- **状态**：Accepted
- **目标/价值**：title、price、sales、shop、SKU 等关键字段可解释。
- **范围**：记录 search response、detail response、embedded state、normalized result 等来源及 parser/quality rules version。
- **验收**：可信 Snapshot 的关键字段具备来源；来源缺失可触发质量拒绝或隔离。
- **约束**：Git commit 不是唯一业务版本标识。

### 3.4 候选观察与未匹配可见性（OBS）

#### OBS-001 — candidate_rejected 可审计可见
- **状态**：Accepted
- **实现/证据状态**：Unknown — 产品语义已由 Product Owner 批准，但实现仍在独立 Task 中，进入 main 前不得声称已验收。
- **目标/价值**：目标未匹配时，用户仍能看到实际观察到的候选与拒绝原因。
- **范围**：独立 Candidate Observation / Unmatched Evidence，含 matched=false、字段差异、采集时间、来源和 Task/Item 关联。
- **验收**：Task Detail 展示候选摘要与拒绝原因；幂等重放不重复；tenant/workspace/Lease fence 生效。
- **约束**：不得写入 canonical Product/Snapshot、资料库、Quality 通过结果或成功统计。

#### OBS-002 — no_candidate 明确语义
- **状态**：Accepted
- **实现/证据状态**：Unknown — 产品语义已批准；真实平台 `no_candidate` E2E 尚无可复核 Accepted 证据。
- **目标/价值**：完全没有候选时给出明确、非伪造的用户反馈。
- **范围**：Task Detail 显示 `no_candidate`、时间与执行来源，不制造空候选对象。
- **验收**：无候选终态非重试且统计正确；平台实际返回推荐候选时不得标为 no_candidate。
- **约束**：真实平台证据未满足时，相关 E2E 只能报告 `BLOCKED`，不得冒充通过。

#### OBS-003 — 候选证据保留策略
- **状态**：Accepted
- **实现/证据状态**：Unknown — 30 天 Raw/脱敏截图与永久 TaskItem 摘要是已批准产品策略，清理实现仍待独立 Task 验收并 merge。
- **目标/价值**：在可审计性与数据最小化之间取得边界。
- **范围**：候选 Raw 与受控脱敏截图默认保留 30 天；TaskItem `not_matched` 终态与必要摘要永久保留。
- **验收**：到期清理有边界、幂等与租户隔离测试；清理不改变 TaskItem 终态。
- **约束**：原始敏感截图、账号、Token、手机号或收货信息不得进入仓库。

### 3.5 任务可靠性（TASK）

#### TASK-001 — 服务端确认后的成功语义
- **状态**：Accepted
- **目标/价值**：杜绝假完成和静默数据丢失。
- **范围**：结果、Raw、媒体和 manifest/receipt 的服务端确认参与完成门禁。
- **验收**：页面完成、Parser 对象或 HTTP 2xx 单独不能使 Task Complete；未确认 outbox 可恢复重投。
- **约束**：客户端本地状态不能承担全局成功判断。

#### TASK-002 — Task / Job / Attempt 职责分离
- **状态**：Accepted
- **目标/价值**：用户目标、稳定业务单元和一次执行尝试可独立审计。
- **范围**：Task 聚合，Job 持有稳定 identity，Attempt 记录设备、时间、错误与重试。
- **验收**：Worker 重启不改变 Job 业务含义；重复 Attempt 不产生重复业务结果。
- **约束**：不得把 Attempt 状态直接等同于 Task 状态。

#### TASK-003 — Lease、恢复与旧执行者隔离
- **状态**：Accepted
- **目标/价值**：断网、进程重启、设备失联后任务可恢复且不被旧 Worker 覆盖。
- **范围**：原子 acquire、heartbeat、expiration、reclaim、checkpoint 与 active lease 查询。
- **验收**：同一时刻只有一个有效执行者；旧 lease/attempt 提交被拒绝；过期 Job 可回收。
- **约束**：服务端 Oracle 是任务真相源。

#### TASK-004 — 错误分类与有限重试
- **状态**：Accepted
- **目标/价值**：临时错误可恢复，业务不匹配不会产生 retry storm。
- **范围**：transient、permanent、business rejection、quality、authentication、manual intervention 分类与上限。
- **验收**：`not_matched` 为非重试业务终态；`LOCAL_TASK_FINISHED` 不得无条件映射为 transient。
- **约束**：不得统一无限重试。

### 3.6 Product、Snapshot 与质量（PROD / QLT）

#### PROD-001 — 稳定商品身份
- **状态**：Accepted
- **目标/价值**：同一平台商品不重复，不同商品不误合并。
- **范围**：平台商品 identity 至少为 `(platform_code, platform_product_id)`，并有数据库级唯一约束。
- **验收**：幂等重复请求返回同一业务商品；标题、URL 或 SKU 变化不创建错误 Product。
- **约束**：跨 Enterprise 的共享边界遵循 Accepted tenancy ADR。

#### PROD-002 — 不可变历史 Snapshot
- **状态**：Accepted
- **目标/价值**：价格、销量、库存、促销和状态变化可追溯。
- **范围**：可信采集事实形成不可变 Snapshot，并支持差异检测。
- **验收**：新采集不覆盖历史；可识别价格、销量、SKU、状态、标题和店铺变化。
- **约束**：失败或隔离数据不能进入正常 Snapshot。

#### PROD-003 — 用户侧资源身份正确
- **状态**：Accepted
- **目标/价值**：Web/API 使用 tenant-facing Product resource ID，而非全局 master 或遗留 ID。
- **范围**：Task→Result→Snapshot→Product 下钻与资料库一致。
- **验收**：跨租户 ID 返回权威 NOT_FOUND/禁止访问；Snapshot 链接解析到正确商品。
- **约束**：UI 不自行猜测资源 ID。

#### PROD-004 — 人工保存进入资料库
- **状态**：Accepted
- **目标/价值**：采集结果与用户维护的商品资料分离。
- **范围**：draft 结果经人工审核保存后进入资料库。
- **验收**：本次采集结果与已保存资料库明确区分；候选观察不可被当作可保存成功结果。
- **约束**：普通编辑不覆盖不可变采集事实。

#### QLT-001 — 统一 QualityGate
- **状态**：Accepted
- **目标/价值**：Parser 成功不等于业务数据可信。
- **范围**：身份、必填字段、价格、SKU 一致性、销量、类型、范围、页面/解析状态和字段来源。
- **验收**：规则可测试、可版本化、可解释；只有 PASS 数据进入正常持久化。
- **约束**：HTTP 200 不能替代质量判定。

#### QLT-002 — Quarantine 隔离
- **状态**：Accepted
- **目标/价值**：不可信数据既不静默丢弃，也不污染正常数据。
- **范围**：记录 Task、可识别 identity、Raw reference、版本、失败原因、错误码和采集时间。
- **验收**：隔离记录可查询；正常 Product/Snapshot 与质量指标不受污染。
- **约束**：进入正常业务数据需另有明确复核流程。

### 3.7 SKU（SKU）

#### SKU-001 — 只接受真实 SKU 面板事实
- **状态**：Accepted
- **目标/价值**：避免从输入或主商品信息伪造规格组合。
- **范围**：维度、选项、实际存在组合、组合价格、可选状态和图片只来自真实 SKU_PANEL 或等价平台证据。
- **验收**：未观察字段标记 `NOT_OBSERVED`；输入“规格”仅为 ProductAttribute 候选。
- **约束**：不得复制主价格、从标题推导组合或批量越过交易边界。

#### SKU-002 — 平台 SKU ID 可选且不可伪造
- **状态**：Accepted
- **目标/价值**：在平台确实提供稳定 ID 时保留身份，否则保持未知。
- **范围**：记录 platform_sku_id 的来源与 observation status。
- **验收**：未观察到时保存 `NOT_OBSERVED`，不生成合成 ID。
- **约束**：不能以 option 文本拼接替代平台 ID。

#### SKU-003 — 正式 SKU/ProductAttribute Schema 与 runtime
- **状态**：Deferred
- **目标/价值**：待真实证据和独立 ADR 后提供组合级持久化与采集。
- **范围**：正式 Oracle 表、migration、Generic SKU 默认 runtime 与历史回填。
- **验收**：需先完成证据矩阵、Schema ADR、可回滚 migration 和隔离 Oracle 门禁。
- **约束**：当前任务不得顺带实施；需要 Product Owner 明确批准。

### 3.8 Raw 与媒体（MEDIA）

#### MEDIA-001 — Raw 证据不可变且可 Replay
- **状态**：Accepted
- **目标/价值**：解析、质量和差异结果可由原始证据复核。
- **范围**：Raw identity、hash、manifest、source locator、parser input 与 replay。
- **验收**：同一 Raw 不可原地覆盖；Replay 可复现 DTO 或明确版本差异。
- **约束**：仓库只提交合法脱敏 fixture，不提交真实敏感 Raw。

#### MEDIA-002 — 租户绑定的媒体访问与完整上传
- **状态**：Accepted
- **目标/价值**：图片和截图不跨租户泄露，上传不形成半成功。
- **范围**：tenant/workspace identity、受控引用、签名/授权访问、上传 receipt。
- **验收**：跨租户读取被拒绝；商品成功门禁按契约验证所需媒体确认。
- **约束**：文件路径或 URL 不能绕过服务端授权。

### 3.9 Enterprise、Workspace 与权限（TENANT）

#### TENANT-001 — 私有事实隔离
- **状态**：Accepted
- **目标/价值**：Enterprise/Workspace 私有任务、快照、媒体与质量数据不跨边界。
- **范围**：所有业务读取、写入、幂等与资源下钻。
- **验收**：缺失或越权上下文按权威 RBAC/NOT_FOUND 语义失败；数据库测试覆盖隔离。
- **约束**：UI 隐藏不能替代服务端授权。

#### TENANT-002 — 商品主数据与私有事实边界
- **状态**：Accepted
- **目标/价值**：避免把共享身份与企业私有事实混成同一对象。
- **范围**：全局最小平台身份与 Enterprise/Workspace 私有 Product/Snapshot/业务资料边界。
- **验收**：用户侧资源 ID 与租户绑定；共享规则符合 Accepted tenancy ADR。
- **约束**：扩大跨 Enterprise 共享字段必须由 Product Owner 决定。

#### TENANT-003 — 服务端权威上下文与 RBAC
- **状态**：Accepted
- **目标/价值**：路由、按钮、Excel 与 API 使用一致权限语义。
- **范围**：selected enterprise/workspace、role permission、stale context 与 403/404 映射。
- **验收**：切换上下文后旧请求失效；关键动作在服务端重新校验权限。
- **约束**：客户端 header 仅表达上下文，不授予权限。

### 3.10 设备与可观测性（DEVICE）

#### DEVICE-001 — 设备注册、心跳与撤销
- **状态**：Accepted
- **目标/价值**：只有受控设备可领取任务，离线与撤销状态可见。
- **范围**：设备 enrollment、online/heartbeat、worker identity 与 revoke。
- **验收**：撤销设备不能领取或续租；标识与凭据不在日志或仓库回显。
- **约束**：不得使用共享默认密钥冒充设备身份。

#### DEVICE-002 — 生命周期恢复与降级
- **状态**：Accepted
- **目标/价值**：App/Agent 重启、断网或被杀后不静默丢任务。
- **范围**：WorkManager/启动恢复/网络恢复与服务端 lease reclaim 的合理组合。
- **验收**：本地状态丢失后可从服务端恢复；无法自动唤醒时 lease 到期可由后续 Worker 接管。
- **约束**：不承诺 Android 不允许的无限后台常驻。

#### DEVICE-003 — 任务执行轨迹可重建
- **状态**：Accepted
- **目标/价值**：工程与运营可解释一次任务为何成功、失败或未匹配。
- **范围**：task_id、job_id、attempt_id、device/worker、lease、trace、event、error_code、timestamp 及 Raw/Quality 关联。
- **验收**：Task Detail/API 能沿 Task→Item→Job→Attempt/Lease→Result/Raw/Quality 下钻。
- **约束**：展示摘要不能改变服务端权威状态。

### 3.11 多平台边界（PLAT）

#### PLAT-001 — Collector Contract 与 Adapter 隔离
- **状态**：Accepted
- **目标/价值**：核心任务、质量和持久化不依赖拼多多页面细节。
- **范围**：Collector/Search/Detail/Parser/Normalizer 契约、Registry 与 PddAdapter。
- **验收**：Selector、点击与平台文案留在 Adapter；核心模型使用 platform code 和规范 DTO。
- **约束**：不为未来平台过度设计动态插件系统。

#### PLAT-002 — 第二平台与 Phase 6B
- **状态**：Deferred
- **目标/价值**：未来可接入京东、淘宝、1688 或其他平台。
- **范围**：第二 Accepted Adapter、契约兼容验证与平台级验收。
- **验收**：需独立 Task、真实证据、平台权限与 Product Owner 批准。
- **约束**：当前不得启动或声称已完成。

### 3.12 治理（GOV）

#### GOV-001 — 单一产品需求基线
- **状态**：Accepted
- **目标/价值**：避免 feature list、roadmap、backlog 与 Task 各自成为产品需求账本。
- **范围**：本文维护稳定需求与 Requirement ID，其他文档只维护各自权威内容并回链。
- **验收**：新开发 Task 引用已批准 ID；历史清单明确非权威；无第二套需求状态表。
- **约束**：测试数量、分支 Head 和动态排期不复制到本文。

#### GOV-002 — 高风险人工批准门禁
- **状态**：Accepted
- **目标/价值**：产品语义、数据与发布风险由 Product Owner 明确决策。
- **范围**：跨企业共享、破坏性 migration/删除/回填、生产操作、真实账号或人工验证、明显不同产品行为、merge 与 release。
- **验收**：相关 Task 在门禁前停止并记录决定；普通实现与测试可按已批准 Task 自动推进。
- **约束**：Agent 不得把技术便利当作产品批准。

## 4. 核心产品不变量

1. 页面完成、Parser 返回对象或 HTTP 2xx 均不等于业务成功；只有服务端确认持久化的 receipt/manifest 才允许 Job/Task 成功。
2. Task、Job、Attempt、Lease、Checkpoint、租户与业务结果以服务端 Oracle 状态为真相；客户端状态只用于执行与恢复。
3. 过期或被 reclaim 的 Lease 不能覆盖新 Attempt。
4. Product 是稳定身份，Snapshot 是某一时点的不可变可信事实；动态字段不得只覆盖保存到 Product。
5. 候选观察和未匹配证据不进入 Product、Snapshot、Quality 通过结果、资料库或成功统计。
6. 异常或不可信结果进入 Quarantine 并保留原因、版本与证据；不得静默丢弃或污染正常数据。
7. Enterprise/Workspace 私有事实不得跨租户读取或写入。
8. 平台点击、Selector、页面文案和原始解析留在 Adapter；核心调度、质量和租户模型不得依赖 PDD 实现。

## 5. 需求追溯矩阵

| Requirement | 权威设计/验收入口 | 动态状态入口 |
|---|---|---|
| MED-001～003、EXCEL-001～003 | [`WEB-TASK-IMPORT-001`](docs/tasks/WEB-TASK-IMPORT-001.md)、[`WEB-NAV-EXCEL-CONSOLIDATION-001`](docs/tasks/WEB-NAV-EXCEL-CONSOLIDATION-001.md) | [`docs/backlog.md`](docs/backlog.md) |
| LINEAGE-001～002、MEDIA-001～002 | [`Raw identity ADR`](docs/decisions/2026-08-24-raw-capture-identity-immutability.md)、[`Phase 3 ADR`](docs/decisions/phase3-data-quality-contract.md) | [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) |
| OBS-001～003 | Product Owner 批准语义与实现未合并边界记录于本治理 [`Task Context`](docs/tasks/PRODUCT-REQUIREMENTS-BASELINE-001.md#product-owner-approved-input)；实现/证据均保持 Unknown，直到 `PDD-COLLECTION-OBSERVABILITY-001` 独立验收并 merge | [`docs/backlog.md`](docs/backlog.md) |
| TASK-001 | [`Phase 1 ADR`](docs/decisions/phase1-success-data-contract.md) | [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) |
| TASK-002～004、DEVICE-002～003 | [`Phase 2 ADR`](docs/decisions/phase2-job-attempt-lease.md)、[`T003 ADR`](docs/decisions/T003-authoritative-task-state.md) | [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) |
| PROD-001～004 | [`Product field semantics ADR`](docs/decisions/2026-08-20-product-field-semantics-p0.md)、[`Product timeline task`](docs/tasks/PDD-PRODUCT-TIMELINE-RESOURCE-ID-001.md) | [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) |
| QLT-001～002 | [`Phase 3 ADR`](docs/decisions/phase3-data-quality-contract.md) | [`docs/gaps/current.md`](docs/gaps/current.md) |
| TENANT-001～003、DEVICE-001 | [`Phase 5 ADR`](docs/decisions/phase5-product-master-tenancy.md)、[`BL-110 task`](docs/tasks/BL-110-WS-TENANT-BOUNDARY.md) | [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) |
| PLAT-001～002 | [`Phase 6A ADR`](docs/decisions/phase6a-collector-contract.md) | [`docs/roadmap.md`](docs/roadmap.md) |
| GOV-001～002 | [`WORKFLOW.md`](WORKFLOW.md)、[`Task template`](docs/tasks/TEMPLATE.md) | [`docs/backlog.md`](docs/backlog.md) |

## 6. 尚待决策或证据

| 决策 | 状态 | 当前边界 | 启动门禁 |
|---|---|---|---|
| 正式 SKU/ProductAttribute Schema、Generic SKU runtime 与历史回填 | Deferred | 只接受证据与 ADR 建议 | Product Owner 批准 Schema/migration Task |
| 真实平台 `no_candidate` 全链 E2E | Unknown | 代码与离线语义可验证，真实平台可能返回推荐候选 | 获得真实无候选证据 |
| 旧桌面链去留 | Unknown | 不扩展新能力 | Product Owner 选择保留/归档/迁移 |
| 第二平台与 Phase 6B | Deferred | 仅保留 Collector Contract 边界 | 独立平台 Task 与真实验收条件 |
| 扩大 Product 跨 Enterprise 共享字段 | Deferred | 维持 Accepted 最小身份/私有事实边界 | 明确产品共享决策与 migration 方案 |

## 7. 成功标准

- 未确认数据导致的错误 Complete、重复业务事实、过期 Lease 覆盖、异常页伪商品和未匹配候选污染均为 0；
- 关键字段来源、Parser 版本、质量规则版本、Raw 与差异可查询；
- 用户能区分本次采集结果、资料库商品、候选观察、无候选和隔离数据；
- Python、Android JVM、Web 与专用 Oracle 门禁可由固定命令重复执行；缺少外部环境时明确报告 `BLOCKED`/`SKIPPED`，不冒充 `PASS`；
- 新开发 Task 可以从 Requirement ID 追溯到批准的产品目标、验收、约束及证据。

## 8. 文档权威边界

| 文档 | 唯一职责 |
|---|---|
| `PRODUCT.md` | 产品范围、稳定需求、Requirement ID、产品不变量与决策门禁 |
| `docs/CURRENT_STATE.md` | 唯一当前实现与 Accepted baseline 状态 |
| `docs/backlog.md` | 唯一任务状态账本 |
| `docs/roadmap.md` | 未来阶段、顺序与依赖，不批准需求 |
| `docs/gaps/current.md` | 当前开放缺口 |
| `docs/decisions/` | 架构决定及替代关系 |
| `docs/tasks/` | 单次 Task 范围、验收、测试与证据 |
| `docs/architecture.md` | 当前实际架构 |
| `WORKFLOW.md` | 开发、Review、E2E、PR、merge 与 release 流程 |
| `docs/product/feature-list*.md` | Historical 实现盘点，不是产品需求或状态权威 |
