# WEB-AUDIT-001 审计报告

> 审计基线：`main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
>
> 审计方式：源码与现有测试只读检查；批准测试 Oracle 的只读查询；FastAPI 现有只读 handler/query 直接调用；未登录真实账号、未修改业务数据、未启动业务实现。
>
> 总结：**任务 1568 数据没有丢失；用户看到“没有数据”的主要原因是页面入口、过滤语义、标识契约和刷新/状态反馈不完整。另有一个独立 P0：实时日志 WebSocket 未认证、未按 Enterprise/Workspace 分区且调度可静默失败。P0=1，P1=7，P2=2，P3=1。**

## 1. 核心结论

任务 `1568` 的普通采集链路已完整持久化：

```text
Task 1568 succeeded（4/4）
→ 4 Jobs / 4 Attempts
→ 4 legacy Product rows（PRODUCT_ID 536～539，全部 library_status=draft）
→ 4 immutable Raw（RAW_ID 518～521）
→ 4 Quality Results（3 passed + 1 accepted warning）
→ 4 Product Snapshots（SNAPSHOT_ID 410～413）
→ 0 Quarantine
```

因此，本次“无数据”现象不是 `Android → Oracle` 丢数据，也不是普通 Product/Snapshot/Quality 未生成。实际可见性断点如下：

1. `/products` 默认只返回 `saved` 商品；任务 `1568` 的 4 条结果均为 `draft`，所以商品资料库不会显示。页面空态只写“暂无商品”，没有解释“采集结果需从任务详情保存入库”。
2. `/tasks/1568` 使用 `task_id` 查询时，现有 API 确实返回 4 条 draft 商品；这是当前唯一完整的普通结果入口。
3. Product、Task Trace 和 Quarantine 页面把全局 `master_product_id` 放入时间线路由，但服务端在租户模式下把该参数解释为 `enterprise_product_id`，导致 Snapshot 时间线返回空。
4. Task 列表和商品资料库不自动刷新；采集中停留在这些页面会看到旧状态。Task 详情虽每 5 秒轮询，但任务与商品请求被 `Promise.all` 绑定且没有页面级错误/空态，任一请求失败都可能留下空白或旧数据。
5. 已接受 Raw 没有独立 Web 查询入口；Quality 页面也不支持 `task_id/job_id` 筛选。用户无法从 Task 直接核对 Raw/Quality，只有 Quarantine 详情能显示 Raw 引用。

独立 Review 同时发现一个必须先处理的安全与可靠性断点：`/ws/realtime` 无认证、权限和租户校验，所有连接进入一个全局广播集合；Web 连接也不发送 token、Enterprise 或 Workspace。同步路由的通知调度还会吞掉异常。因此当前实时日志要么静默不推送，要么在调度成功时可能把 Task/Device/日志内容广播给未认证或其他租户连接。该 P0 与 Task 1568 的 Oracle 持久化完整性是两件事，不能互相抵消。

### SKU 边界

- 本次调查性 SKU Panel Raw 仍只属于 `SKU-EVIDENCE-001` 证据，不代表正式 Generic SKU runtime 或正式 SKU Schema。
- 现有 Product 页面中的“多规格售价”读取已存在的 Snapshot/legacy SKU 字段，不是 Generic SKU 组合主档。
- 因此“不显示正式 SKU 组合”当前符合批准范围；但 Task、普通 Product、Snapshot、Quality 和 Raw 引用仍应可追踪，不能以 SKU 未启用解释这些页面的空白。

## 2. 任务 1568 的 Oracle → API → Web 复现

### 2.1 Oracle 权威事实

只读查询在 `enterprise_id=1 / workspace_id=1` 中得到：

| 对象 | 数量 | 关键状态 |
|---|---:|---|
| Task | 1 | `succeeded`，success=4，fail=0 |
| Task Item | 4 | 4 个采集目标 |
| Job / Attempt | 4 / 4 | 4 个 Job 均 `success` |
| Legacy Product | 4 | `product_id=536..539`，全部 `library_status=draft` |
| Raw | 4 | `raw_id=518..521`，hash 已存在 |
| Quality Result | 4 | accepted=4；3 `passed`，1 `warning/partial` |
| Snapshot | 4 | `snapshot_id=410..413` |
| Quarantine | 0 | 无 |
| Upload Receipt | 8 | 产品与完成 receipt 已存在 |

查询结束显式执行 `ROLLBACK`，未写业务数据；报告不保存凭据或 Raw 内容。

### 2.2 API 现有行为

| 调用 | 实际结果 | 解释 |
|---|---|---|
| `GET /api/products?page=1&limit=50` 的 handler 等价调用 | 当前资料库 72 条；不含 Task 1568 | 服务端在未传 `task_id` 时追加 `NVL(LIBRARY_STATUS,'saved')='saved'` |
| `GET /api/products?task_id=1568&page=1&limit=50` 的 handler 等价调用 | 4 条，IDs `539,538,537,536` | Task 详情能够取得 draft 结果 |
| `GET /api/tasks/1568` 的 handler 等价调用 | status=`succeeded`，items=4，logs=6 | Task 详情数据存在 |
| Management trace query | jobs=4，attempts=4，snapshots=4，quarantine=0 | 执行链完整 |
| Snapshot timeline 使用 Web 链接 ID `249` | total=0 | Web 传的是 `master_product_id=249` |
| 同一商品使用实际 `enterprise_product_id=237` | total=1，snapshot=`410` | 服务端租户契约要求 Enterprise Product ID |

Task 1568 的映射反例为：

```text
PRODUCT_ID 536 → MASTER_PRODUCT_ID 249 → ENTERPRISE_PRODUCT_ID 237
Web link /products/249/timeline → 0 rows
Correct tenant resource /products/237/timeline → Snapshot 410
```

其余三条也存在同样错位：`250→238`、`251→239`、`252→240`。

### 2.3 Web 渲染结果

```text
/products
  → 不传 task_id
  → 服务端仅返回 saved
  → Task 1568 的 4 条 draft 不进入 table
  → 页面显示“暂无商品”或既有资料库数据

/tasks/1568
  → GET /api/tasks/1568 + GET /api/products?task_id=1568
  → API 均有数据
  → 正常时显示 4 条“待保存”商品
  → 任一请求失败时 Promise.all 整体 reject，页面没有明确错误态

/products/{master_product_id}/timeline
  → 服务端按 enterprise_product_id 解释参数
  → ID 契约不一致
  → 页面显示“该商品暂无可查看的 Snapshot”
```

## 3. 页面、API 与数据源矩阵

普通 HTTP 业务请求原则上经 `web/src/api/http.js` 自动附带 Bearer Token、`X-Enterprise-Id` 和 `X-Workspace-Id`；服务端以 `require_tenant_perms` 和 Oracle tenant predicate 过滤。已确认两类例外：Excel 的三个 raw axios blob/upload 请求缺租户头；实时日志 WebSocket 不经过 HTTP client，既不发送身份/租户上下文，服务端也不校验或分区。

| 页面 / 路由 | 主要用户功能 | API | Oracle / 服务状态来源 | 空态、错误态、刷新 |
|---|---|---|---|---|
| 登录 `/login` | 登录并取得用户/租户上下文 | `/api/auth/login`、`/api/auth/me` | User、Role、Membership、Workspace | 登录错误 toast；无轮询 |
| 设备 `/devices` | 设备、绑定、终止任务 | `/api/devices`、platforms、account operators | Device、Task、Job/Attempt/Lease、Account/User | 手动刷新；缺统一 loading/error/empty |
| 实时监控 `/devices/:id/live` | 当前任务与屏幕状态 | devices、task detail、`/ws/realtime` | Device、Task/Item/Log + 全局内存 WS Hub | 8 秒 HTTP 轮询；WS 未认证/未带租户/全局广播且调度可能静默失败（P0） |
| 投屏 `/devices/:id/cast` | 启停投屏、任务日志 | cast start/stop、devices、task detail、WS | 内存 cast state + Device/Task/Log | 日志 5 秒轮询；画面空态；错误主要 toast |
| 任务列表 `/tasks` | 筛选、审核、进入详情 | `/api/tasks`、review | Task | 有 loading/error/empty；仅手动刷新 |
| 创建任务 `/tasks/create` | 选择平台/设备/账号并创建 | platforms、devices、accounts、`POST /api/tasks` | Platform、Device、Account、Task/Item/Job | 提交 loading；初始依赖失败缺页面级恢复 |
| 任务详情 `/tasks/:id` | 进度、日志、结果、保存入库、重下发 | task detail、products by task | Task/Item/Log/Anomaly、legacy Product/Image | 5 秒轮询；无页面级 loading/error；零结果区被隐藏 |
| 执行轨迹 `/tasks/:id/trace` | Task→Job→Attempt→Event→Result | management trace/jobs/attempts/events | Task、Job、Attempt、Event、Snapshot、Quarantine | 分区 loading/error/empty；手动刷新；Snapshot 链接 ID 错误 |
| 商品资料库 `/products` | 查询 saved 商品、详情、导出、编辑 | products、platforms | legacy Product/Image + canonical read model | loading/error/empty；仅手动刷新；未说明 draft 被过滤 |
| 商品时间线 `/products/:id/timeline` | Snapshot、Diff、Provenance、SKU JSON | management snapshots | Enterprise Product→Master、Snapshot、Diff、Provenance | loading/error/empty；标识契约错导致假空态 |
| 数据质量 `/quality` | 质量聚合、版本、缺失率、异常 | management quality metrics | Quality Result + Raw | loading/error/empty；手动；无 Task/Job 筛选 |
| Quarantine `/quarantines` | 筛选、查看 Raw/Quality/执行关联 | management quarantine list/detail | Quarantine、Raw、Quality、Master、Task/Job/Attempt/Device | loading/error/empty 完整；时间线链接 ID 错误 |
| Excel `/excel` | 模板、匹配、导出、未匹配转任务 | excel template/match/export/task | Product/Image、Device、Task/Item、Platform | 操作 loading；三个 raw axios 请求缺租户头 |
| 账号 `/accounts` | 账号养护与告警 | accounts/alerts/operators/devices | Platform Account、Alert、User、Device | 初始 `Promise.all`；缺统一 loading/error/empty |
| 报表 `/reports` | 商品数量、销量、均价趋势 | reports overview | legacy Product | 手动加载；缺 loading/error/empty |
| 人员 `/users` | 用户、角色、重置密码 | users、roles | User、Role、Membership | 手动；缺统一 loading/error/empty |
| 角色 `/roles` | 角色与权限 | roles、permission catalog | Role、Role Permission | 手动；缺统一 loading/error/empty |
| 操作日志 `/logs` | 审计日志查询 | op-logs | Operation Log | 手动；缺统一 loading/error/empty |
| 系统设置 `/settings` | health、OTA、图片清理 | health、ota、image purge | 服务健康、OTA state、Device/Product Image | 多写操作；状态反馈以 toast 为主 |
| 个人中心 `/profile` | 修改密码、个人日志 | change-password、my-logs | User、Operation Log | 手动；缺统一 loading/error/empty |

## 4. Findings

### P0

#### F0 — 实时日志 WebSocket 未认证、未按租户分区且调度不可靠

- **复现**：`server/ws_hub.py` 把所有 WebSocket 放入一个全局 `set` 并向全部 peers 广播；`/ws/realtime` 连接直接 `accept()`，没有 token、`device:view`、Enterprise/Workspace membership 或资源归属检查。`DeviceLive.vue` 的连接 URL 不携带任何上下文，Task progress 广播数据也没有租户字段。
- **可靠性反例**：`notify_sync()` 从同步 handler 调用 `get_event_loop()/create_task()`，只在 loop running 时调度，并吞掉全部异常；因此 UI 声称的“WebSocket 推送日志”可能静默不工作。
- **影响**：一旦广播被成功调度，未认证连接或其他租户连接可能收到 `task_id/device_id/message/level`；调度失败时用户又会得到无提示的陈旧日志。现有 HTTP tenant predicate 不能保护该独立 WS 通道。
- **最低修复**：复用已有 `BL-110`，建立一个受控的最小 WS 子任务：握手认证、`device:view`、Enterprise/Workspace membership、Task/Device 归属校验；Hub 按租户/资源分区；事件携带服务端确定的 scope；使用可靠的 app event loop/队列调度并记录失败；增加未认证、跨租户、撤销用户/设备和真实调度契约测试。
- **停止条件**：本审计只记录并升级 P0，不修改 WS 业务代码；在 P0 修复并验证前，不把实时日志标为安全或可靠。

### P1

#### F1 — Snapshot 时间线使用错误资源标识

- **复现**：Task 1568 的 `MASTER_PRODUCT_ID=249`，对应 `ENTERPRISE_PRODUCT_ID=237`。Web 请求 `249` 返回 0；请求 `237` 返回 Snapshot 410。
- **代码链**：`ProductList.vue`、`TaskTrace.vue`、`QuarantineList.vue` 使用 `master_product_id` 组装路由；`management_queries.list_snapshots` 在租户模式按 `ENTERPRISE_PRODUCT_ID=:resource_id` 查询。
- **影响**：Snapshot、Diff、Provenance 和普通 SKU JSON 被误显示为空；用户会误判采集未生成数据。
- **最低修复**：建立一个明确的 tenant-visible Product resource ID；列表、Trace、Quarantine DTO 返回并使用 `enterprise_product_id`；增加从 Task 1568 同型数据到 Snapshot 的契约测试。

#### F2 — draft 采集结果与“商品资料库”之间缺少可见语义

- **复现**：Task 1568 有 4 Product，但全部为 `draft`；默认商品 API 排除它们，带 `task_id` 的 API 返回 4 条。
- **影响**：用户在商品资料库看不到刚采集数据，空态没有解释或返回任务入口。
- **最低修复**：保持“人工保存后进入资料库”的现有产品语义，不自动入库；在 Task 详情始终展示“本次结果”区及计数，在商品资料库明确仅显示已入库并提供“查看待保存结果/返回任务”的导航。

#### F3 — Task 详情加载失败被耦合并静默

- **复现**：`load()` 以 `Promise.all(task detail, task products)` 绑定；组件没有 loading/error 状态，商品数组为空时整块 `v-if` 隐藏。
- **影响**：Product API 权限、网络或租户错误会让 Task 主体也无法更新，用户只看到空白或旧值；轮询会持续重复失败。
- **最低修复**：Task、Products、Logs/Result 分开管理 loading/error/last-updated；产品失败不阻断任务主体；零结果显示解释性空态。

#### F4 — Excel 的三个请求绕过统一租户 HTTP client

- **复现**：template、match、export-batch 使用 raw `axios`，`tokenHeaders()` 只添加 Authorization；服务端对应端点要求 tenant context。静态核对：raw axios=3、Excel tenant header refs=0。
- **影响**：已登录用户仍会收到缺少 `X-Enterprise-Id/X-Workspace-Id` 的 400，且错误处理与全局 client 不一致。
- **最低修复**：统一使用共享 client 或共享 tenant-aware blob client；增加请求头契约测试。

#### F5 — Task 无法下钻 accepted Raw 和 task-scoped Quality

- **复现**：Task 1568 有 Raw 518～521 和 Quality 474～477；Task/Trace 页面不展示 Raw ID/Quality Result，Quality API/UI 没有 `task_id/job_id` 参数。Raw 只在 Quarantine detail 中可见，而本任务 quarantine=0。
- **影响**：成功任务的证据和 warning 无法从 Web 追溯；用户只能查数据库或离线证据。
- **最低修复**：在 Task Trace 的 business result 中返回并显示 Raw、Quality、Snapshot 引用；Quality 增加 task/job 筛选或 Task scoped 摘要。仅展示 evidence reference/脱敏摘要，不暴露未脱敏 Raw。

#### F6 — 采集中的列表视图容易陈旧

- **复现**：TaskList、ProductList、Quality、Trace 均仅 mount/手动加载；只有 TaskDetail 5 秒、DeviceLive 8 秒、header summary 15 秒轮询。
- **影响**：用户停留在 Task 列表或商品页观察采集时，看不到状态和结果出现，形成“前端没有数据”的印象。
- **最低修复**：优先为 active Task 提供明确自动刷新/最后更新时间/手动刷新状态；不要全站无差别高频轮询。

#### F7 — 无 `device:view` 用户的权限回退目标不可靠

- **复现**：路由无权限时固定返回 `/devices`；`/devices` 本身要求 `device:view`。
- **影响**：拥有其他模块权限但没有 `device:view` 的角色可能无法得到可访问首页或明确 403 页面。
- **最低修复**：按用户首个可访问路由跳转，或提供无权限页；增加角色路由矩阵测试。

### P2

#### F8 — 页面状态处理不一致

Device、Account、Report、User、Role、Log、Settings、Profile 等页面缺少一致的 loading/error/empty/retry；多个页面把并行依赖绑定为一次 `Promise.all`。应在核心 P1 闭环完成后统一，不需要先建设大型设计系统。

#### F9 — 任务数量与数据状态文案容易误读

TaskList 显示 `${success}/${fail} / ${target}` 而无标签；Product 空态不区分“无已入库数据”“筛选无结果”“本次采集尚无结果”；Quality warning 不会在 Task 主流程突出显示。

### P3

#### F10 — Web bundle 较大

Production build 通过，但主 chunk 约 578 kB 并触发现有告警。该问题已在 `BL-210` 登记；没有真实首屏指标前不应抢占可见性 P1。

## 5. 端到端目标用户流程

### 当前流程

```text
创建并审核任务
→ TaskList（需手动刷新）
→ TaskDetail（5 秒轮询，正常时可见 draft 结果）
→ 手动“保存选中到商品资料库”
→ ProductList（仅 saved）
→ Snapshot Timeline（当前因 ID 错配为空）
→ Quality（只有 Workspace 聚合，不能按 Task 下钻）
→ accepted Raw（无入口）
```

### 最小合理流程

```text
创建并审核任务
→ Task 列表显示运行状态、最后更新时间
→ Task 详情分别显示任务进度 / 本次 draft 结果 / warning / 证据引用
→ 用户按现有规则决定是否保存入库
→ 商品资料库明确“仅已入库”，并能返回待保存 Task 结果
→ 使用 enterprise_product_id 打开正确 Snapshot/Diff/Provenance
→ 从 Task/Job 下钻 Raw reference 与 Quality；异常再进入 Quarantine
```

## 6. 最小必要整改任务排序

### 1. `BL-110-WS-TENANT-BOUNDARY` — 最高优先 P0

复用已有 `BL-110`，不要建立重复的全站 WebSocket 项目。本子任务只收敛实时日志 WS：

- 握手认证与 `device:view` 权限；
- Enterprise/Workspace、Task、Device 归属校验；
- Hub/事件按租户与资源分区；
- 同步 handler 到 app event loop 的可靠调度与可观察失败；
- 未认证、跨租户、撤销与调度契约测试。

### 2. `WEB-RESULT-VISIBILITY-001` — 后续 P1

一个垂直切片完成以下内容，避免拆成多个互相等待的小任务：

- 固定 `enterprise_product_id` 的 DTO/路由契约并修复三处时间线链接；
- Task 详情解耦加载、增加 loading/error/empty/last-updated；
- 明确 draft→人工保存→资料库的文案与导航，不改变自动入库语义；
- Task Trace 增加脱敏 Raw/Quality/Snapshot 引用和 task-scoped 质量摘要；
- 对 Task 1568 同型 fixture 增加 Web/API 契约和组件测试。

### 3. `WEB-CLIENT-CONTRACT-001` — 后续 P1

- Excel blob/upload/export 统一 tenant-aware HTTP client；
- 按权限选择首页/回退路由，提供无权限页；
- 覆盖 Authorization、Enterprise、Workspace 和角色路由矩阵。

### 4. `WEB-STATE-UX-001` — 后续 P2

- 只为仍缺失的页面补齐统一 loading/error/empty/retry；
- 统一成功/失败/目标计数与“已入库/待保存/警告”文案；
- 依据真实使用指标再决定刷新节奏和 bundle 优化。

不建议现在新建独立 Dashboard 重构、设计系统、Generic SKU 页面、Schema/migration 或重复的全站 WebSocket 项目。

## 7. 验证与限制

- Web production build：1673 modules，exit 0，PASS；保留既有 large-chunk warning。
- Web strict gate：`[PASS] web-build: exit=0`，exit 0。
- Oracle Task 1568 query + handler contract：exit 0；显式 `ROLLBACK`。
- 静态契约检查：raw axios=3、Excel tenant header refs=0、timeline master-id links=3、server enterprise-id lookup=1。
- WS 静态契约检查：global client set=1、server auth/tenant refs=0、client WS context refs=0、Task event tenant refs=0；P0 reproduced。
- 未执行需要新登录的浏览器会话；没有使用或记录真实账号、Token、密码或未脱敏 Raw。Oracle/API/Web 断点已通过真实持久化事实、现有 handler 和渲染源码交叉验证。
- 本报告不批准任何实现；`SKU-EVIDENCE-001` 保持 `REVIEW / SCHEMA REVIEW CANDIDATE`，不进入 Schema、Generic SKU runtime、P1/P2 或 Phase 6B。
