# 稳定数据采集系统里程碑

> 制定日期：2026-08-13  
> 任务来源：`docs/backlog.md`。里程碑按依赖推进，但每个里程碑内部仍按 P0 → P1 → P2 → P3 执行。  
> 本文只定义范围和门禁，不承诺未经估算的日历日期。

## 总览

| 里程碑 | 核心范围 | Backlog | 前置 | 完成后的系统状态 |
|---|---|---|---|---|
| M0 基础恢复 | 工具链、依赖、配置秘密、隔离 Oracle、schema 基线、既有测试修复、最低门禁 | BL-001～004、BL-009～011、BL-305（M0 文档） | 无 | 当前源码可重复构建、完整启动和执行最低测试 |
| M1 任务可靠性 | 状态机、attempt/租约、幂等、outbox、错误分类 | BL-005～008、BL-106、BL-009（可靠性部分） | M0 | 任务可恢复且重复请求安全 |
| M2 数据质量 | 数据契约、解析边界、质量隔离、样本、一致性、Room migration | BL-101～105、BL-206（基础部分） | M1 | 数据可追溯、校验、去重和恢复 |
| M3 可观测性 | 结构化日志、关联 ID、健康、指标、告警、安全基线 | BL-107、BL-108、BL-110（运行安全部分） | M1；接入 M2 质量指标 | 故障可发现、定位和处置 |
| M4 自动化测试 | API 契约、分层测试、E2E、CI/制品追溯 | BL-104（体系化）、BL-109、BL-111、BL-112、BL-110（测试部分） | M2 + M3 | 关键变更受自动门禁保护 |
| M5 扩展优化 | 缓存、后台作业、多实例、模块化、容量、归档、桌面/多平台/OTA | BL-201～208、BL-301～305 | M4 | 按测量结果扩容和演进 |

## M0 基础恢复

> **状态：IN_PROGRESS（更新于 2026-08-13）**  
> T001 已验收 DONE：BL-001、BL-002 已完成。Python 干净安装/导入、Web 干净安装/build、Android debug assemble 和环境文档已通过。剩余 BL-003、BL-010、BL-004、BL-011、BL-009 基础部分，因此 M0 不关闭。

### 范围

- BL-001：固定工具链与命令。
- BL-002：Python 依赖闭包。
- BL-003：秘密外置与配置校验。
- BL-010：隔离 Oracle 测试环境。
- BL-004：Oracle schema 版本基线。
- BL-011：修复 `DetailReaderTest` 3 项既有失败。
- BL-009：先接入 import/build/migration smoke。
- BL-305：更新构建、配置和启动文档。

### 明确代码落点

`requirements.txt`、`server/config.py`、`server/main.py`、`server/db.py`、`server/init_schema.py`、`server/init_rbac_schema.py`、`server/migrate.py`、`web/package*.json`、`web/vite.config.js`、Android Gradle/wrapper/发布脚本。

### 前置决策

- Python/Node/JDK/SDK 受支持版本。
- Oracle 测试 schema 获取方式。
- 秘密注入与轮换方式。
- 当前 `web/dist`、APK 和源码的版本对应关系。

### 退出门禁

1. 干净 Python 环境安装后服务端和桌面关键模块导入通过。
2. 规定 Node 版本下 Web production build 通过。
3. 规定 JDK/SDK 下 Android assemble 与现有 unit tests 执行并记录结果。
4. 测试配置可启动 FastAPI；liveness/readiness 基础行为可验证。
5. 测试 Oracle 可从定义基线迁移到当前版本，重复执行安全。
6. 源码不提供可用生产秘密默认值，缺配置时明确失败。
7. 上述检查由统一命令或初始 CI 执行。

### 当前状态与下一任务

- **已完成**：T001 / BL-001 / BL-002。
- **遗留分流**：测试 Oracle→P0 BL-010；DetailReader 测试失败→P0 BL-011；Gradle 首次依赖获取→P1 BL-113；SDK XML 警告→P2 BL-209；Web 大 chunk→P2 BL-210。
- **下一个任务**：T002 / BL-003“外置秘密并增加配置启动校验”。它不依赖尚未提供的测试 Oracle，是 BL-010/BL-004 使用安全测试配置的前置，并直接关闭当前源码中数据库、JWT 和 Android release 签名秘密默认值的 P0 风险。

### 不属于 M0

- 不拆分 `PddActions.kt`/`tasks.py`。
- 不引入缓存、消息队列或新平台。
- 不批量修复无可靠原文的 mojibake。

## M1 任务可靠性

### 范围

- BL-005：统一状态机。
- BL-006：attempt、租约、续租和超时回收。
- BL-007：进度/商品/图片/完成幂等。
- BL-008：Android outbox 与 dead-letter。
- BL-106：错误分类和重试策略。
- BL-009：并发、重复、断线和恢复测试。

### 明确代码落点

`server/routers/tasks.py`、`devices.py`、`products.py`、`server/schemas.py`、`services.py`、Oracle 任务 schema；Android `AgentCoordinator.kt`、`ApiClient.kt`、`TaskEngine.kt`、Room entities/DAO；桌面 `task_runner.py` 仅做状态映射/隔离。

### 前置决策

- 投递语义（建议以业务幂等支撑 at-least-once，最终由负责人确认）。
- 租约时长、续租频率、任务超时和最大尝试次数。
- 商品/图片上报幂等键。
- 旧 Android 版本兼容窗口与 OTA 顺序。

### 退出门禁

1. 状态机和合法迁移由自动测试覆盖。
2. 并发领取仅产生一个有效 attempt。
3. 重复/乱序/迟到上报不破坏状态和计数。
4. Agent 断线、App 重启、服务重启、Oracle 短暂失败后任务进入确定状态。
5. 租约过期可自动回收，reconciliation 修复有审计。
6. Android 待上报数据跨进程重启不丢失，永久错误进入 dead-letter。
7. Web 可准确显示 attempt、重试、超时和最终状态。

### 不属于 M1

- 不以 Redis/队列替代尚未定义的数据库状态机。
- 不优化报表或前端视觉。
- 不实现新平台。

## M2 数据质量

### 范围

- BL-101：商品数据契约与唯一键。
- BL-102：详情获取/解析/标准化/校验边界。
- BL-103：字段校验与 quarantine。
- BL-104：解析与 Excel 样本库。
- BL-105：DB/文件一致性、备份恢复。
- BL-206：Room schema 导出与迁移基础。

### 明确代码落点

Android `PddActions.kt`、`DetailReader.kt`、`ProductTargetMatcher.kt`、Room；桌面 `detail_parser.py`、`list_parser.py`、`excel_target.py`、`storage_exporter.py`；服务端 `products.py`、`excel_match.py`、`image_filter.py`、`reports.py` 和商品/图片 schema。

### 前置决策

- 商品业务唯一键与合并规则。
- 核心字段必填/范围/单位/空值规则。
- 人工修改与新采集值的优先级。
- 原始证据、图片和历史快照保留期。
- `T_GOODS_LIBRARY` 的实际形态和同步责任。

### 退出门禁

1. 字段契约和唯一键经业务确认并映射到三端模型。
2. 正式商品可追溯 task/item/attempt/端版本/parser 版本。
3. 固定样本覆盖主要字段、边界和异常，达到批准阈值。
4. 校验失败进入 quarantine，不静默污染正式库。
5. 重复、孤儿、缺图和计数漂移巡检可重复执行。
6. Oracle/文件备份恢复演练后完整性检查通过。
7. Room 升级测试保持已支持版本数据。

### 不属于 M2

- 不因潜在性能问题提前缓存商品查询。
- 不在无样本保护下全量重写解析器。

## M3 可观测性

### 范围

- BL-107：关联标识和结构化日志。
- BL-108：健康、指标、告警和 runbook。
- BL-110：与运行直接相关的 CORS、设备/WS 身份、TLS 和脱敏收口。
- 将 BL-103 的质量结果接入指标。

### 明确代码落点

`server/main.py`、`auth_util.py`、`services.py`、`db.py`、所有 router、`ws_hub.py`、`cast_state.py`；Android coordinator/engine/API；桌面 `utils.py`/`task_runner.py`；Web dashboard、task/device/settings/logs 页面。

### 前置决策

- SLI/SLO 与告警阈值。
- 日志/指标后端和通知渠道。
- 日志、异常、截图和页面文本保留/脱敏规则。
- 单实例或多实例当前部署事实。

### 退出门禁

1. `task_id` 可关联 request/item/attempt/device 并还原时间线。
2. 结构化日志保留异常堆栈并通过敏感信息扫描。
3. liveness/readiness 分离且不泄露 DSN/内部路径。
4. 服务、Oracle、调度、设备、采集、质量、存储指标可查询。
5. 服务不可用、任务卡死、设备离线、质量下降、磁盘不足有告警与 runbook。
6. 至少一次故障演练完成“触发→定位→处置→恢复”。
7. 遥测后端故障不阻断采集主链。

### 不属于 M3

- 不以 dashboard 页面数量代替指标和告警。
- 不直接为了“可观测”记录完整敏感请求/页面。

## M4 自动化测试

### 范围

- BL-104：把样本回归纳入统一测试体系。
- BL-109：API/错误/枚举契约。
- BL-110：密码迁移、Agent/WS/上传边界安全测试。
- BL-111：服务端、Web、Android、契约和 E2E 套件。
- BL-112：CI 与制品追溯。

### 明确代码落点

待建服务端 tests；Web 测试配置及 `src/api`、stores、关键 views；Android `app/src/test` 与 Room migration tests；Oracle 测试 schema；模拟 Agent；CI/构建脚本。

### 前置决策

- Oracle 自动测试环境方案。
- 快速、集成、E2E、真机测试的运行频率和责任人。
- 覆盖阈值、flaky 上限和发布门禁。
- CI/制品存储位置。

### 退出门禁

1. 统一入口运行 Python、Web、Android 和契约测试。
2. 自动 E2E 覆盖创建→审核→领取→上报→完成→Web 查询。
3. M1 故障场景、M2 质量样本、schema/Room migration 全部进入门禁。
4. API 字段/枚举/错误不兼容会在消费方测试中失败。
5. 关键 Web 权限和失败处置流程被覆盖。
6. 发布制品关联源码、依赖、schema 和测试结果；门禁失败不发布。
7. flaky/skip 有明确负责人、原因和截止日期。

### 不属于 M4

- 不用大量真实页面 E2E 取代快速单元/集成测试。
- 不以单一行覆盖率数字作为完成结论。

## M5 扩展优化

### 范围

- P2：BL-201～208。
- P3：BL-301～305。
- 每个优化必须引用 M3 指标和 M4 回归结果。

### 明确代码落点

缓存候选 `platforms/auth/dashboard/reports`；后台作业 `excel_match/image_filter/products`；实时多实例 `ws_hub/cast_state/cast`；服务端 routers/services/repository；Android 大模块；Room；根目录桌面端；平台与 OTA 模块。

### 前置决策

- 目标设备数、任务吞吐、延迟和资源预算。
- 是否需要多实例、共享存储、缓存和后台队列。
- 旧桌面端去留。
- 新平台业务优先级。
- 数据归档/删除保留期。

### 退出门禁

1. 容量测试达到批准目标，优化前后差异可证明。
2. 缓存仅用于已证明热点，关闭/失效时正确，任务权威状态不依赖普通缓存。
3. Excel/OCR/图片长任务可持久化、恢复、取消和重试。
4. 如采用多实例，任务、WS/投屏和文件访问故障切换测试通过；否则记录单实例约束。
5. 大模块拆分保持 API/样本/真机回归，无一次性全量重写。
6. 旧桌面端有正式保留、冻结或退役结论。
7. 新平台具备 adapter、字段契约、样本、E2E、监控和发布开关后才算完成。
8. OTA 灰度与回滚演练通过，文档/运行手册与当前实现一致。

## 里程碑变更规则

- 新任务必须先加入 `docs/backlog.md`，标明优先级、模块、依赖和验收，再映射到本文件。
- P0/P1 未关闭时，P2/P3 只能做只读调研，不得进入实现占用主线。
- 里程碑门禁未满足时不得用“主体完成”“基本可用”关闭阶段；无法验证项保持 UNKNOWN/BLOCKED。
- 每个里程碑完成时更新 `docs/backlog.md` 状态、`docs/architecture.md`（若架构变化）和对应 `docs/decisions/`。
