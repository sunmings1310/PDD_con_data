# 稳定数据采集系统 Backlog

> **Status: CURRENT TASK STATUS AUTHORITY（2026-08-25）**
> 本文是任务状态唯一账本。旧章节保留历史证据但不自动授权实施；当前实现见 [`CURRENT_STATE.md`](CURRENT_STATE.md)，开放缺口见 [`gaps/current.md`](gaps/current.md)，新任务使用 [`tasks/TEMPLATE.md`](tasks/TEMPLATE.md)。

## Completed governance baseline

| Task | 状态 | 范围 | 下一步 |
|---|---|---|---|
| REPO-GOV-ALIGN-001 | MERGED / ACCEPTED BASELINE | 从 Accepted Business Baseline 对齐治理文档、AGENTS、模板和 CI；PR #3 merge commit `713cd714902c728cc0e7b796bdde4972c78042c9` | 已完成并停止；等待 Product Owner 批准独立后续 Task |

## Accepted Business Baseline（2026-08-24 merged）

- [x] Phase 6A Collector Contract/PddAdapter 保持 Accepted。
- [x] 纳入 Raw Capture 基础保存、脱敏、hash、manifest、server persistence 与 offline replay。
- [x] 纳入 Product Consistency P0、Canonical Read/Edit DTO、稳定字段编辑白名单与动态事实不可编辑策略。
- [x] 默认 PDD 正常采集路径不打开 SKU Panel、不点击购买入口、不遍历 combinations，并有负向 JVM gate。
- [x] PR #2 以普通 merge commit `02234f2` 进入 `main`。
- Generic SKU runtime、SKU_PANEL 自动交互、正式 SKU Schema、P1 与 Phase 6B 均为 **NOT STARTED**；需独立证据、ADR 与 Product Owner 批准。

拆分清单与证据见 [`tasks/BASELINE-SPLIT-001.md`](tasks/BASELINE-SPLIT-001.md)。

> 2026-08-16 全面审计基线：[`../GAP.md`](../GAP.md)。本轮未实施业务重构或数据库迁移。
>
> 历史说明：Phase 1～Phase 6A 的当前验收状态已由后续工作更新，统一以 [`CURRENT_STATE.md`](CURRENT_STATE.md) 为准。本段以下早期 Phase 记录仅保留来源，不表示“等待进入 Phase 3”。

## Phase 1 执行记录（2026-08-16）

| 任务 | 状态 | 完成内容 | 验收 |
|---|---|---|---|
| T004 固定 fixture + 成功门禁 | DONE | 10 类脱敏离线样本；统一 `page_status/parse_status/quality_status`；Android 与服务端双重门禁；字段来源和规则版本持久化 | Python fixture/quality tests 通过；Android quality tests 通过；异常页不生成 outbox |
| T005 修复 Android 假完成 | DONE | Room v2 持久 outbox、稳定 idempotency key、指数重试、商品/图片/finish 明确 ack、Oracle receipt、finish manifest、App 重启补偿 | Python 协议、MockWebServer、Room migration/reopen/原子事务及真实 Oracle 并发/回滚/完成闭环通过 |
| T006 完整测试基线 | DONE | 固定 Python 3.10、Node 22.18、JDK 17.0.20、Gradle 8.4、SDK 34；统一 `scripts/test-baseline.ps1` 严格区分 PASS/FAIL/BLOCKED | Python 60、Oracle 8、Android JVM 36、Web build 全部 PASS；严格入口 exit=0 |
| Phase 1 数据契约 ADR | DONE | Product、ProductSnapshot、Task、Job、Attempt、商品/快照身份、幂等与完成不变量 | `docs/decisions/phase1-success-data-contract.md` |

> 制定日期：2026-08-13  
> 依据：`docs/gap-analysis.md` 与当前代码。  
> 排序规则：P0 → P1 → P2 → P3；同优先级按依赖顺序排列。每项都指向现有代码模块，不以“建设平台”“优化架构”等不可验收表述作为任务。

> 2026-08-13：已完成客户讨论材料 `docs/customer/enterprise-management-proposal.md`，用于确认企业层、三级账号体系、数据隔离、商品数据模式、分阶段能力与客户决策事项；不代表多企业功能已进入实施或成为既定需求。

## 使用规则

- 普通实施状态取值：`TODO`、`IN_PROGRESS`、`BLOCKED`、`DONE`；治理/集成流程可按 [`../WORKFLOW.md`](../WORKFLOW.md) 使用 `REVIEW`、`ACCEPTED`、`MERGED / ACCEPTED BASELINE`，以各任务条目状态为准。
- 完成任务时必须记录实际命令、输入、输出和测试结果；功能修改同时更新本文件状态。
- 涉及架构边界变化时更新 `docs/architecture.md`；重要技术选择写入 `docs/decisions/`。
- 未确认的业务决策不得由开发自行假设，相关任务保持 `BLOCKED/UNKNOWN`。

## P0：阻断与任务正确性

### BL-001 固定可重复工具链与构建命令

- **状态/里程碑**：DONE / M0（2026-08-13，T001）
- **代码模块**：`requirements.txt`、`web/package.json`、`web/package-lock.json`、`android_collector/gradle/wrapper/gradle-wrapper.properties`、`android_collector/build.gradle.kts`、`android_collector/app/build.gradle.kts`、`server/run.ps1`、`web/run-dev.ps1`。
- **任务**：确定并声明 Python、Node/npm、JDK 17、Android SDK、Gradle 的受支持版本；整理单一的安装、构建、测试命令。
- **验收**：干净环境中 Python 模块导入、`npm run build`、Android assemble/test 均执行；输出环境版本与真实结果。当前已知 Node v20.11.1 构建失败和缺 JDK必须得到明确解决或形成受支持版本约束。
- **依赖/风险**：无；工具链升级可能引发锁文件或 Android 插件变化，必须单变量验证。
- **验收记录**：已声明 Python 3.10.6、Node 22.18.x/npm 10.x、JDK 17、Gradle 8.4、AGP 8.1.4、Android SDK 34；Node 22.18.0 下 `npm ci` 与 `npm run build` 通过；JDK 17.0.20/Gradle 8.4/SDK 34 下 `assembleDebug --rerun-tasks` 通过。`testDebugUnitTest` 实际运行 15 项、3 项既有失败，归入测试修复任务，不阻断工具链基线建立。

### BL-002 补齐并验证 Python 依赖闭包

- **状态/里程碑**：DONE / M0（2026-08-13，T001）
- **代码模块**：`requirements.txt`；导入点 `server/auth_util.py`、`server/main.py`、根目录桌面模块。
- **任务**：依据实际 import 补齐 PyJWT 等运行依赖，区分服务端、桌面端和可选 OCR/Playwright 依赖，确定锁定方式。
- **验收**：新虚拟环境安装后 `import server.main`、`import jwt` 及桌面关键模块导入通过；不存在未声明的直接依赖。
- **依赖/风险**：BL-001；不得只在现有 `.venv` 中手工安装而不更新依赖清单。
- **验收记录**：在新建 `.venv-t001` 中按固定版本清单安装成功；`import jwt, server.main, PyQt6, playwright, pandas, oracledb, aiohttp, httpx, PIL, pytesseract` 通过，`pip check` 返回 `No broken requirements found.`。完整服务启动到 Uvicorn lifespan/Oracle 初始化阶段，因验收输入使用不可达的本地 Oracle 端点而按预期停止。

### T001 建立项目可重复构建环境

- **状态**：DONE
- **实际完成日期**：2026-08-13
- **最终验收日期**：2026-08-13
- **对应 Backlog**：BL-001、BL-002
- **最终验收结果**：项目负责人验收通过。Python 干净环境依赖安装及核心模块导入通过；Web 在 Node 22.18.0/npm 10.9.3 下 `npm ci` 和 production build 通过；Android 在 JDK 17.0.20、Gradle 8.4、SDK 34 下 debug assemble 通过；开发环境、工具链版本和各组件启动方式已文档化。
- **验收证据**：`docs/tasks/T001-result.md`、`docs/development-environment.md`。

### T001 遗留问题登记

| 编号 | 遗留问题 | 分类 | 后续归属/状态 |
|---|---|---|---|
| T001-F01 | 缺少隔离的 Oracle 测试环境。 | P0 / M0 阻塞项 | BL-010；DONE（2026-08-17，专用测试 Schema 已完成迁移和真实事务验收） |
| T001-F02 | Android `DetailReaderTest` 15 项中有 3 项既有失败。 | P0 / 最低测试门禁 | BL-011；TODO |
| T001-F03 | Gradle Wrapper 在干净环境首次下载 Gradle/Maven 依赖需要可用网络、组织镜像或预置缓存。 | P1 / 构建基础设施 | BL-113；TODO |
| T001-F04 | Android SDK command-line tools 与当前 AGP 产生 SDK XML 版本兼容警告，但 debug assemble 成功。 | P2 / 工具链兼容优化 | BL-209；TODO，可暂缓 |
| T001-F05 | Web production build 存在大于 500 kB 的 chunk 性能告警，但构建成功。 | P2 / 性能优化 | BL-210；TODO，需指标后处理 |

### BL-010 建立隔离的 Oracle 测试环境

- **状态/里程碑**：DONE / M0（2026-08-17）
- **来源**：T001-F01
- **代码模块**：`server/config.py`、`server/db.py`、`server/main.py` lifespan、`server/init_schema.py`、`server/init_rbac_schema.py`、`server/migrate.py`、待建测试环境配置/脚本。
- **任务**：提供与现有 Oracle 方言一致、与原项目数据隔离的测试 schema；为服务启动、readiness、schema 基线和迁移测试提供可重复的配置与初始化/清理方式。现有原项目 Oracle 仅允许继续做已批准的只读核对，不能作为破坏性迁移测试库。
- **验收**：使用专用测试凭据完成 `SELECT 1 FROM dual`；FastAPI lifespan 完整启动并关闭；初始化/迁移可在测试 schema 执行；测试数据可清理且不会访问原项目业务 schema；配置中无真实密码入库。
- **完成证据**：专用可写 Schema 通过 Oracle 19c 连接；`ensure_schema_patches()` 成功新增 progress/upload receipt、质量字段并使远程图片 `REL_PATH` 可空；8 项真实多连接/事务测试通过且测试标记数据残留为 0。凭据仅经环境变量注入。
- **依赖/风险**：完整 FastAPI lifespan/readiness 独立留在服务部署验收；BL-004 的版本化迁移链仍需后续建设。

### BL-011 修复 Android DetailReaderTest 既有失败

- **状态/里程碑**：DONE / M0-M2（2026-08-16）
- **来源**：T001-F02
- **代码模块**：`android_collector/app/src/test/java/com/collector/pdd/parser/DetailReaderTest.kt`、`android_collector/app/src/main/java/com/collector/pdd/parser/DetailReader.kt`、必要时 Android/JVM 测试依赖配置。
- **任务**：逐项判定 2 个 `JSONObject.put` 本地 JVM 问题属于测试环境缺口还是生产逻辑耦合，并确认“期望 63.5、实际 null”属于错误测试期望还是解析回归；只修复已证实根因，不为了绿测修改业务结果。
- **验收**：记录 3 个失败各自根因；`testDebugUnitTest` 15 项全部通过，或经业务确认删除/修改错误期望并保留证据；新增/修订样本能防止同类回归；Android debug assemble 仍通过。
- **完成证据**：JVM 使用真实 `org.json` 测试实现，未启用 `returnDefaultValues`；补贴价在免拼栏优先作为 group/display；新增 10 类 fixture 回放、质量门禁、MockWebServer、Room migration/outbox 重启和重试策略测试。`testDebugUnitTest` 36/36 通过。

### BL-003 外置秘密并增加配置启动校验

- **状态/里程碑**：DONE / M0（T002，2026-08-13）
- **代码模块**：`server/config.py`、`server/.env`/待建模板、`server/auth_util.py`、`android_collector/app/build.gradle.kts`、Android 发布脚本。
- **任务**：移除 Oracle/JWT/签名秘密的可用源码默认值；定义必填项、范围、环境覆盖顺序和生产启动校验；制定已有秘密轮换步骤。
- **验收**：缺少关键秘密时服务或 release build 明确失败；示例配置不含真实秘密；测试配置可启动；源码扫描不再发现可用生产秘密。
- **完成证据**：Oracle/JWT 无可用源码默认值；Pydantic 启动校验与 11 项配置测试通过；test 可纯环境变量注入；Android release signing 外置且缺配置明确失败；`assembleDebug`、Web production build 和 Python 核心导入通过。完整 FastAPI lifespan 因无隔离 Oracle 标记 `BLOCKED_BY_ENVIRONMENT`，由 BL-010 继续处理。
- **依赖/风险**：BL-001；现有部署的实际旧配置来源仍为 UNKNOWN，升级前必须按 `docs/tasks/T002-result.md` 迁移并轮换已暴露 Secret。

### BL-004 建立 Oracle schema 版本基线

- **状态/里程碑**：TODO / M0
- **代码模块**：`server/init_schema.py`、`server/init_rbac_schema.py`、`server/migrate.py`、`server/db.py`、`server/main.py`。
- **任务**：只读盘点实际 Oracle schema；把初始化与启动补丁整理为有版本、执行记录、checksum 和互斥控制的迁移链；明确 `T_GOODS_LIBRARY` 是表还是视图。
- **验收**：测试库可从基线升级到当前版本；重复执行无额外副作用；失败可恢复；服务多实例启动不会并发执行同一 DDL；实际 schema 差异清单归档。
- **依赖/风险**：BL-003、可用测试 Oracle；不得直接在未备份的现有库试迁移。

### BL-005 统一任务、任务项、设备和审核状态机

- **状态/里程碑**：DONE / M1（T003，2026-08-13）
- **代码模块**：`server/routers/tasks.py`、`server/routers/devices.py`、`server/schemas.py`、`server/services.py`、`android_collector/.../TaskEngine.kt`、`AgentCoordinator.kt`、根目录 `task_runner.py`。
- **任务**：定义服务端权威枚举、合法迁移、终态和不变量；明确 Android `finished/stopped`、桌面 `interrupted/paused` 的映射；将状态迁移从散落 SQL 收敛到可测试业务函数。
- **验收**：状态迁移表与实现一致；非法迁移被拒绝；任务/任务项/设备状态组合测试通过；Web 显示不再依赖猜测式映射。
- **完成证据**：新增集中状态定义与 Oracle 状态服务；task/progress/finish/cancel、device abort、OTA abort、product item 回填均使用统一迁移或运行态守卫；Python 25/25、T003 11/11、Android 状态映射 3/3、assembleDebug、Web build 通过。Android 全量单测仍仅有 T001 已登记的 `DetailReaderTest` 3 项既有失败。
- **依赖/风险**：BL-004；旧桌面端是否纳入服务端状态为 UNKNOWN，未决策前仅定义隔离边界。

### BL-006 增加执行 attempt、任务租约和超时回收

- **状态/里程碑**：DONE / M1（Phase 2，2026-08-17）
- **代码模块**：`server/routers/tasks.py` 的 `pull_task/progress/task_finish`、`server/routers/devices.py` heartbeat、Oracle 任务相关 schema、`AgentCoordinator.kt`、`ApiClient.kt`。
- **任务**：每次领取生成 `attempt_id`，记录租约截止与续租；用 Oracle 条件更新/锁防止重复领取；增加过期 attempt reconciliation。
- **验收**：两个 Agent 并发领取仅一个成功；Agent 断线后任务在规定时间恢复/重排；旧 attempt 的迟到进度和完成请求被拒绝；所有自动回收有审计记录。
- **完成证据**：`CollectionJob/Attempt/Lease/Checkpoint` schema、原子 `SKIP LOCKED` acquire、token hash fence、heartbeat、30 秒 reconciliation、真实 Oracle 并发/过期 lease/route 集成与 18 项故障注入通过。
- **依赖/风险**：BL-005；租约时长、续租周期和最大尝试次数需业务/运行数据确认。

### BL-007 实现上报幂等与单调进度

- **状态/里程碑**：PARTIAL / M1（Phase 1-2）
- **代码模块**：`server/routers/tasks.py`、`products.py`、Oracle 商品/图片/任务项 schema、`ApiClient.kt`、`AgentCoordinator.kt`、Room entities/DAO。
- **任务**：为 progress、product、image、anomaly、finish 定义幂等键；进度包含 attempt 与单调序号；商品和图片写入建立确定的重复语义。
- **验收**：同一请求重复 10 次不重复计数/终结/建商品/建图片；乱序进度不能回退状态；相同业务键冲突产生明确错误或既定合并结果。
- **完成证据**：product/image/checkpoint/complete 使用稳定 idempotency key；checkpoint 单调；ACK 丢失重放、旧 lease、重复 outbox 均通过。跨任务 `Product + ProductSnapshot` 业务去重仍留 Phase 3。
- **依赖/风险**：BL-006；商品业务唯一键当前 UNKNOWN，须先决策，不能以普通索引替代语义。

### BL-008 建立 Android 持久化 outbox 与失败闭环

- **状态/里程碑**：DONE / M1（Phase 1-2，2026-08-17）
- **代码模块**：`android_collector/.../data/AppDatabase.kt`、`Dao.kt`、`Entities.kt`、`net/AgentCoordinator.kt`、`net/ApiClient.kt`、服务端 progress/product/image/finish API。
- **任务**：本地持久化待上报操作；按错误分类做有限退避；成功确认后删除；超过策略进入 dead-letter/待人工状态。
- **验收**：上传中断、App 重启、服务端 5xx 后待办不丢失且可重放；永久错误不无限重试；重放与 BL-007 幂等测试组合通过。
- **完成证据**：Room v3 assignment/outbox、2→3 migration、有限退避、旧 lease 隔离、WorkManager/ForegroundService/Boot 恢复和 JVM migration/recovery tests 通过。
- **依赖/风险**：BL-007；Room schema migration 必须兼容已安装版本。

### BL-009 建立最低自动化门禁

- **状态/里程碑**：DONE / M0-M1（本地门禁，2026-08-17）
- **代码模块**：待建服务端测试目录、`android_collector/app/src/test`、`web/package.json` 测试脚本、构建脚本/CI 配置。
- **任务**：把构建、配置校验、schema migration、状态机、并发领取、重复上报和断线恢复纳入可重复脚本。
- **验收**：统一入口运行 Python、Web build、Android unit tests 和 M1 集成测试；失败返回非零状态并保留关键证据。
- **完成证据**：`scripts/test-baseline.ps1` 严格运行 Python、真实 Oracle Phase1/2、Android JVM、Web build；CI 托管自动化仍归 BL-112。
- **依赖/风险**：BL-001～BL-008 按内容逐步接入；Oracle 测试环境方案 UNKNOWN。

## P1：稳定运行闭环

### BL-101 定义商品数据契约与唯一键

- **状态/里程碑**：TODO / M2
- **代码模块**：`server/schemas.py`、`server/routers/products.py`、`android_collector/.../data/Entities.kt`、`DetailReader.kt`、根目录 `detail_parser.py`、`storage_exporter.py`。
- **任务**：定义字段类型、单位、空值、来源、必填、自然键、快照/当前记录和人工修订优先级。
- **验收**：字段字典经业务确认；FastAPI/Android/桌面字段映射可机械核对；唯一键用于 BL-007 幂等与去重。
- **依赖/风险**：BL-007；不得自行假设商品合并规则。

### BL-102 分离详情获取、解析、标准化和校验

- **状态/里程碑**：TODO / M2
- **代码模块**：`PddActions.kt`、`DetailReader.kt`、`detail_parser.py`、`list_parser.py`、`filter_handler.py`。
- **任务**：在不改变业务结果的前提下建立输入/输出边界，使解析可用固定文本/节点/JSON 离线测试；记录 parser/selector 版本。
- **验收**：核心字段解析无需启动真实页面即可测试；现有样本输出差异经审核；页面动作与纯解析测试分开。
- **依赖/风险**：BL-101、BL-009；大文件拆分必须小步，禁止无关重构。

### BL-103 建立数据质量校验与 quarantine

- **状态/里程碑**：TODO / M2
- **代码模块**：`server/routers/products.py`、`excel_match.py`、`image_filter.py`、Oracle 商品/异常 schema、Web 商品/任务详情页。
- **任务**：对价格、规格、批准文号、SKU、图片等执行字段规则；失败数据保留原因并进入待复核，而不是静默填默认值入库。
- **验收**：规则有版本；典型无效输入进入 quarantine；Web 可查询/处置；质量通过率可统计。
- **依赖/风险**：BL-101/102；阈值过严会误隔离，需样本校准。

### BL-104 建立解析与 Excel 固定样本库

- **状态/里程碑**：TODO / M2-M4
- **代码模块**：Android parser/matcher tests、待建 Python parser tests、`server/routers/excel_match.py` 测试、脱敏 fixtures。
- **任务**：收集典型、边界、改版、空结果、OCR 和 Excel round-trip 样本，定义期望字段和允许差异。
- **验收**：样本版本化且脱敏；Android/Python/Excel 回归可离线执行；解析变化输出字段差异报告。
- **依赖/风险**：BL-102；样本不得包含无必要的敏感页面内容。

### BL-105 建立数据库/文件一致性巡检与恢复

- **状态/里程碑**：TODO / M2
- **代码模块**：Oracle 商品/图片/任务表、`server/routers/products.py`、`server/config.py` 图片目录、`server/data/images`、待建巡检脚本。
- **任务**：检测重复商品、孤儿任务项/图片、缺失文件、计数漂移；制定 Oracle + 图片备份、恢复和保留清理流程。
- **验收**：巡检在测试副本运行并给出确定报告；备份恢复演练后引用完整性通过；自动修复操作有审计和 dry-run。
- **依赖/风险**：BL-004、BL-101；历史脏数据禁止未经确认自动删除。

### BL-106 统一错误分类与重试策略

- **状态/里程碑**：TODO / M1-M3
- **代码模块**：`task_runner.py`、`browser_client.py`、`AgentCoordinator.kt`、`ApiClient.kt`、`TaskEngine.kt`、FastAPI router 错误处理。
- **任务**：定义 `error_code/stage/retryable`，按网络、访问限制、解析、校验、永久业务错误设置退避、次数和总时限。
- **验收**：相同错误跨 Agent/API 使用一致分类；不可重试错误不重试；可重试错误有次数和最终状态；日志/指标可按分类聚合。
- **依赖/风险**：BL-005/008；宽泛捕获必须保留异常上下文。

### BL-107 引入全链路关联标识和结构化日志

- **状态/里程碑**：TODO / M3
- **代码模块**：`server/main.py` 中间件、`auth_util.py`、`services.py`、各 router、`utils.py`、`task_runner.py`、Android coordinator/engine。
- **任务**：贯通 `request_id/task_id/item_id/attempt_id/device_id`；结构化输出状态迁移、外部调用和异常；定义脱敏、轮转和保留。
- **验收**：以任一 `task_id` 可还原跨 API/Agent 的执行时间线；异常带堆栈；日志不含 token、密码、设备密钥；轮转策略验证通过。
- **依赖/风险**：BL-006、BL-106；避免记录完整页面/请求体导致敏感信息和高容量。

### BL-108 建立健康检查、指标与告警

- **状态/里程碑**：TODO / M3
- **代码模块**：`server/main.py` `/api/health`、`dashboard.py`、`devices.py`、`services.py`、`db.py`、Android heartbeat、Web dashboard/settings。
- **任务**：分离 liveness/readiness；增加服务、Oracle、任务、设备、采集、质量和磁盘指标；设置高信号告警和 runbook。
- **验收**：健康响应不暴露 DSN/路径；任务卡死、Oracle 不可用、设备大面积离线、质量下降、磁盘不足可告警；完成一次故障演练。
- **依赖/风险**：BL-006/103/107；SLO 和通知渠道 UNKNOWN，需负责人确认。

### BL-109 统一 API 响应、错误和版本化契约

- **状态/里程碑**：TODO / M4
- **代码模块**：`server/schemas.py`、所有 `server/routers/*.py`、`web/src/api/http.js`、`web/src/stores/user.js`、Android `ApiClient.kt`。
- **任务**：统一 HTTP 状态、业务错误、分页和枚举；以 OpenAPI/契约测试保护 Vue 和 Android；制定旧 Agent 兼容窗口。
- **验收**：不再依赖同时处理 HTTPException 与互相矛盾的 `ok:false` 语义；契约变更会让消费方测试失败；错误码可用于 BL-106。
- **依赖/风险**：BL-005/106；必须先兼容发布再启用强校验，避免旧 APK中断。

### BL-110 收紧管理端与 Agent 安全边界

- **状态/里程碑**：TODO / M3-M4
- **代码模块**：`server/main.py` CORS、`auth_util.py`、`routers/auth.py`、Agent API/WS 路由、Android `ServerPrefs.kt`/`ApiClient.kt`、上传/下载接口。
- **任务**：升级密码哈希；限制 CORS；定义设备身份轮换/撤销；验证 WS 授权、TLS、限流、上传大小和 URL 获取边界。
- **验收**：旧密码可安全迁移；允许 origin 明确；被撤销设备不能继续上报/投屏；上传和外部 URL 测试覆盖边界。
- **依赖/风险**：BL-003/109；需要现有账号和设备兼容迁移方案。

### BL-111 建立服务端/Web/Android 分层测试套件

- **状态/里程碑**：TODO / M4
- **代码模块**：服务端待建 tests、Web 待建 unit/E2E、Android `app/src/test`、`run_test.py` 的正式定位。
- **任务**：补状态机/服务/DB 集成、Vue 关键逻辑、Android parser/protocol、契约和一条模拟 Agent E2E。
- **验收**：创建→审核→领取→上报→完成→Web 查询全自动通过；测试失败保留 request/task/attempt 证据；flaky 项有责任人和期限。
- **依赖/风险**：BL-009、BL-104、BL-109；真实页面验收与快速门禁分层。

### BL-112 建立 CI 构建、测试和制品追溯

- **状态/里程碑**：TODO / M4
- **代码模块**：待建 CI 配置、构建脚本、`web/dist`、Android APK/OTA metadata、版本文件。
- **任务**：按快速/集成/E2E/Android 分层运行；制品记录源码版本、schema、依赖和测试结果；发布失败可回滚。
- **验收**：主分支/发布制品均有可查询构建记录；任一门禁失败不生成可发布制品；当前 `web/dist`/APK 对应关系得到替换或归档。
- **依赖/风险**：BL-001/004/111；当前版本控制/CI 托管位置 UNKNOWN。

### BL-113 保障 Gradle Wrapper 首次依赖获取

- **状态/里程碑**：TODO / M4
- **来源**：T001-F03
- **代码模块**：`android_collector/gradle/wrapper/gradle-wrapper.properties`、`android_collector/settings.gradle.kts`、`android_collector/build.gradle.kts`、开发环境文档和 CI 缓存配置。
- **任务**：在“官方源可达、组织镜像、预置并校验缓存”中选择可审计方案，保证全新 runner 能通过 Wrapper 获取 Gradle/Maven 依赖；保留分发包校验与缓存失效规则。
- **验收**：无本机既有 Gradle 分发/依赖缓存的测试环境中，仓库 Wrapper 完成 `assembleDebug testDebugUnitTest`；失败信息能区分网络、镜像和校验问题；方案不依赖其他项目目录。
- **依赖/风险**：依赖组织网络/镜像策略和 BL-112 CI 环境；不得把未经校验的二进制直接提交为 workaround。

## P2：扩展性与性能

### BL-201 用指标确定缓存候选并实现缓存接口

- **状态/里程碑**：TODO / M5
- **代码模块**：`platforms.py`/`routers/platforms.py`、`auth_util.py` 权限查询、`dashboard.py`/`reports.py`、`server/config.py`。
- **任务**：用 BL-108 指标选择读多写少热点；定义 key、TTL、版本、失效、容量、降级和命中率；不得缓存任务权威状态。
- **验收**：基准证明收益；缓存关闭/失效时结果正确；权限/字典变更能按规则失效；命中率和错误可监控。
- **依赖/风险**：BL-108/111；无热点证据则任务结论应为“不引入缓存”。

### BL-202 将 Excel/OCR/图片长任务移出同步请求

- **状态/里程碑**：TODO / M5
- **代码模块**：`server/routers/excel_match.py`、`products.py` 图片清理、`image_filter.py`、Web Excel/settings 页面。
- **任务**：把解析、导出、OCR 批处理和清理变为可持久化后台作业，复用 M1 状态/重试原则。
- **验收**：API 快速返回作业 ID；可查询进度、取消、重试和死信；服务重启后作业不丢失；大文件不会长期占用请求线程。
- **依赖/风险**：BL-005～008、BL-111；避免建立第二套不兼容状态机。

### BL-203 多实例共享实时状态方案

- **状态/里程碑**：TODO / M5
- **代码模块**：`server/ws_hub.py`、`cast_state.py`、`routers/cast.py`、Web `DeviceCast.vue`/`DeviceLive.vue`、Android `ScreenCastService.kt`。
- **任务**：按部署规模选择单实例约束、sticky session、共享 broker 或独立实时网关；处理重连和服务切换。
- **验收**：目标部署拓扑下实时通知/投屏连接行为可预测；实例重启和切换测试通过；无多实例需求则明确保留单实例约束。
- **依赖/风险**：BL-108/111；投屏高带宽，不能未经容量测试引入共享 broker。

### BL-204 收敛 FastAPI router 中的业务和 SQL

- **状态/里程碑**：TODO / M5
- **代码模块**：`server/routers/tasks.py`、`products.py`、`excel_match.py`、`devices.py`、`server/services.py`、待建 repository/service。
- **任务**：按任务、商品、设备领域逐个把状态/事务下沉 service，把 SQL 下沉 repository；不改变 API 契约。
- **验收**：router 只做协议适配和权限；状态机/事务可单测；API/Oracle 集成回归全部通过；每次拆分单一领域。
- **依赖/风险**：BL-111；禁止一次性全量重写。

### BL-205 拆分 Android 采集大模块

- **状态/里程碑**：TODO / M5
- **代码模块**：`PddActions.kt`、`TaskEngine.kt`、`A11yHelper.kt`、`DetailReader.kt`。
- **任务**：按平台动作、页面导航、节点提取、纯解析、质量校验、上报边界渐进拆分；保持时序与对外行为。
- **验收**：固定样本与真机验收无非预期差异；各边界可单测；故障/日志仍带 attempt 和 stage。
- **依赖/风险**：BL-102/104/111；无测试保护不开始。

### BL-206 完善 Room schema migration

- **状态/里程碑**：TODO / M2-M5
- **代码模块**：`AppDatabase.kt`、`Entities.kt`、`Dao.kt`、Android Gradle Room 配置。
- **任务**：开启 schema 导出，为 outbox/质量字段和未来版本提供逐版本 migration 与升级测试。
- **验收**：从所有受支持已发布版本升级保持任务/商品/待上报数据；失败有明确处置而非静默清库。
- **依赖/风险**：BL-008；真实设备当前数据库版本分布 UNKNOWN。

### BL-207 建立容量、并发和长期稳定性测试

- **状态/里程碑**：TODO / M5
- **代码模块**：任务 API、Oracle pool、Agent 模拟器、WS、Excel/OCR 作业、指标系统。
- **任务**：定义设备数、任务吞吐、P95/P99、存储增长目标并进行负载/耐久测试。
- **验收**：报告瓶颈、资源预算和安全容量；优化前后有数据对比；达到业务批准的目标。
- **依赖/风险**：BL-108/111；容量目标当前 UNKNOWN。

### BL-208 建立存储归档和清理作业

- **状态/里程碑**：TODO / M5
- **代码模块**：Oracle 任务/日志/异常/商品表、`server/data/images`、APK 元数据、`server/config.py`、Web settings。
- **任务**：按确认的保留期归档/删除日志、异常、原始证据、图片和旧 APK；带 dry-run、审计和恢复窗口。
- **验收**：测试数据上只处理符合规则记录；DB/文件引用一致；磁盘水位可监控；回滚窗口内可恢复。
- **依赖/风险**：BL-105/108；保留期 UNKNOWN，未确认前不得删除。

### BL-209 消除 Android SDK XML 工具链兼容警告

- **状态/里程碑**：TODO / M5
- **来源**：T001-F04
- **代码模块**：Android SDK command-line tools 安装版本、`android_collector/build.gradle.kts`、`settings.gradle.kts`、`gradle-wrapper.properties`、`docs/development-environment.md`。
- **任务**：在保持 AGP 8.1.4/Gradle 8.4 构建兼容的前提下，对齐 command-line tools 与 SDK metadata 版本；若升级 AGP/Gradle，单独记录兼容矩阵和回归结果。
- **验收**：干净 Android 构建不再输出 SDK XML 版本警告；assemble 与 unit tests 通过；工具链版本文档同步更新。
- **依赖/风险**：依赖 BL-011/BL-112；当前警告不阻断构建，禁止为消警告进行未经测试的大版本升级。

### BL-210 评估并优化 Web 大 chunk

- **状态/里程碑**：TODO / M5
- **来源**：T001-F05
- **代码模块**：`web/vite.config.js`、`web/src/router/index.js`、`web/src/main.js`、Element Plus/icon 引入、构建分析配置。
- **任务**：先记录 production bundle 构成、首屏加载和缓存指标，再决定路由懒加载、按需引入或 `manualChunks`；不以隐藏 `chunkSizeWarningLimit` 作为修复。
- **验收**：有优化前后 bundle/首屏指标对比；目标 chunk 或加载指标达到批准阈值；页面路由和 Web 自动测试通过。若指标证明无实际影响，可用“评估后不实施”关闭并保留数据。
- **依赖/风险**：依赖 BL-108 指标和 BL-111 Web 回归；当前仅为构建警告，不得抢占 P0/P1。

## Phase 3 数据质量交付（2026-08-17）

- **DONE / BL-101**：新增 `SJZQ_PRODUCT_MASTER`，数据库唯一键 `(PLATFORM_CODE, PLATFORM_PRODUCT_ID)`；新采集不重复创建业务 Product identity。
- **DONE / BL-105, BL-106**：动态事实进入不可变 `SJZQ_PRODUCT_SNAPSHOT`；价格、销量、SKU、可用状态、标题、店铺差异写入 `SJZQ_SNAPSHOT_DIFF`。
- **DONE / BL-107**：服务端 `QualityGate phase3-1` 是 strict upload 唯一质量入口；关键字段 provenance 写入 `SJZQ_FIELD_PROVENANCE`；拒绝观察进入 `SJZQ_DATA_QUARANTINE`。
- **DONE / BL-111（Phase 3 范围）**：固定离线质量矩阵、真实 Oracle Product/Snapshot/Quarantine 测试以及 Phase 1/2 回归进入统一测试入口。
- **DONE / BL-004（最小框架）**：新增 `SJZQ_SCHEMA_MIGRATION` 与可重入 `P3_001_DATA_QUALITY`；后续迁移仍需逐个纳入版本框架。
- **DEFERRED**：历史 `SJZQ_PRODUCT` 去重/回填需要数据合并决策；稳定 `platform_sku_id` 未具备前，不创建 SKU 主档；Quarantine 管理 UI 留给 Phase 4。

## P3：长期演进

### BL-301 决定旧桌面采集链路去留并执行

- **状态/里程碑**：TODO / M5
- **代码模块**：根目录 `main.py`、`ui_window.py`、`task_runner.py`、`detail_parser.py`、`storage_exporter.py`、README。
- **任务**：依据真实使用情况选择正式保留、冻结维护或退役；定义数据迁移、功能替代和回滚窗口。
- **验收**：形成决策记录；不存在两套未定义的默认主链；保留则有独立测试/发布，退役则数据和文档迁移完成。
- **依赖/风险**：业务确认 UNKNOWN；不能仅因代码旧而删除。

### BL-302 建立平台 adapter 后再实现新平台

- **状态/里程碑**：Phase 6A DONE；Phase 6B/第二平台 NOT STARTED / M5
- **代码模块**：`server/platforms.py`、`routers/platforms.py`、Android engine/parser、桌面搜索/详情模块、平台测试 fixtures。
- **任务**：Phase 6A 已冻结最小 Collector/Registry/Capability/System Error 契约，并使拼多多经 Adapter 通过兼容回归。后续只在独立 Phase 6B 接入一个第二平台验证契约，不在 6A 接入 JD、淘宝或 1688。
- **验收**：新平台有独立 adapter、字段契约、样本、E2E、指标和发布开关；仅常量/种子不算完成。
- **依赖/风险**：BL-101/102/111/205；多平台优先级 UNKNOWN。

### BL-303 完善失败工作台和运维操作

- **状态/里程碑**：TODO / M5
- **代码模块**：Web `TaskDetail.vue`、`TaskList.vue`、`DeviceList.vue`、settings/logs 页面；服务端 task anomaly/dead-letter/reconciliation API。
- **任务**：集中展示卡死、死信、质量隔离和巡检问题，提供受权限控制的重试、忽略、修复和审计入口。
- **验收**：运营无需查数据库即可处理定义内失败；每个操作有权限、确认、幂等和操作日志。
- **依赖/风险**：BL-008/103/107/110；不得提供绕过状态机的任意更新入口。

### BL-304 完善 OTA 灰度、兼容和回滚

- **状态/里程碑**：TODO / M5
- **代码模块**：`server/routers/ota.py`、`ota_meta.py`、Android `ApkUpdater.kt`、`MainActivity.kt`、构建/发布脚本。
- **任务**：制品签名/校验、设备分组灰度、最低兼容版本、升级确认、失败回滚与版本指标。
- **验收**：测试设备完成灰度→扩大→回滚演练；服务端拒绝不兼容协议版本；OTA 状态可监控和审计。
- **依赖/风险**：BL-003/109/112；Android 包安装限制和设备厂商差异需真机验证。

### BL-305 文档与运行手册收口

- **状态/里程碑**：TODO / M0-M5
- **代码模块**：根/Android/Web README、`docs/architecture.md`、`docs/CURRENT_STATE.md`、`docs/issues.md`、`docs/decisions/`、待建 runbook。
- **任务**：随每阶段更新架构、配置、部署、schema、状态机、告警、故障处理和回滚文档；处理 mojibake 需有正确原文证据。
- **验收**：新成员可按文档构建/启动；值班人员可按 runbook 处理已定义告警；README 与当前入口/版本一致。
- **依赖/风险**：贯穿全程；没有正确语义来源时乱码保持 UNKNOWN，不猜测修复。

## 优先级出口规则

- **P0 出口**：BL-001～BL-009 完成；否则不得把系统声明为稳定，也不得进入缓存/多平台工作。
- **P1 出口**：BL-101～BL-112 完成；系统具备可靠任务、数据质量、可观测和自动化门禁闭环。
- **P2 出口**：每项必须有 M3 指标证明必要性；没有收益可用“评估后不实施”关闭。
- **P3 出口**：由业务价值驱动，不得挤占尚未关闭的 P0/P1。
# Phase 4 管理与可观测性（2026-08-17）

- [x] Quarantine 服务端分页、筛选、详情与 Raw/Quality/执行链关联。
- [x] Product Master Snapshot 时间线、Diff 与字段来源展示。
- [x] 服务端真实质量聚合、版本表现、错误集中度与基础异常提示。
- [x] Task → Job → Attempt → Event/Device/Error 分页轨迹。
- [x] Tasks、Products、Jobs、Attempts、Snapshots、Quarantine 的服务端真实分页。
- [x] 管理页面 loading/error/empty 状态与对象跳转。
- [ ] Quarantine 人工修复/重放流程（非 Phase 4 优先目标）。
- [x] Attempt Event、Quarantine、Snapshot、Task/Product 分页关键复合索引（`P4_001_MANAGEMENT_INDEXES`）。
- [ ] JSON 虚拟列/search index（以真实容量和执行计划决定）。
# Phase 5 企业化完成记录（2026-08-17）

- [x] Enterprise、Workspace、Enterprise/Workspace membership 与租户 Role 边界
- [x] 全局最小 Product identity + Enterprise 私有 Product/Snapshot/Quarantine
- [x] Task/Job/Attempt/Lease/Checkpoint/Event 租户归属与设备租户领取边界
- [x] Dashboard、Task、Product、Quality、Quarantine、Trace、日志查询租户谓词
- [x] 管理端企业/Workspace 选择器与请求头上下文
- [x] Workspace/User/Active Task/Daily Snapshot/Storage 配额基础表；Workspace 创建执行配额
- [x] `P5_001`、`P5_002`、`P5_003` Oracle 可重入 migration
- [x] 离线租户契约、真实 Oracle 跨租户 ID、分页与 migration 测试

Phase 5 验收见 `docs/tasks/phase5-acceptance.md`。本阶段停止，不进入 Phase 6。

# Phase 5.5 企业化硬化完成记录（2026-08-18）

- [x] Device enrollment 一次性 token、hash 存储、轮换、设备 key 轮换和 revoke
- [x] 被撤销设备统一 Agent/OTA/投屏发布门禁，撤销时终止活动执行权
- [x] 账号养护、设备管理、OTA、投屏 viewer/媒体、Excel TenantContext 收敛
- [x] Active Task、Daily Snapshot、Storage usage/reservation/ledger 与迁移回填
- [x] 跨租户、撤销设备、配额并发、媒体/Excel 旁路离线专项测试
- [x] legacy/default 最终移除条件 ADR
- [x] 隔离 Oracle Phase 1～5.5 真实迁移、两租户、设备 revoke、媒体与 quota 两会话并发回归

验收见 `docs/tasks/phase55-acceptance.md`。Phase 5.5 已 ACCEPTED；后续 Phase 6A 已进入 Accepted Business Baseline，Phase 6B 仍 NOT STARTED。

# Phase 6A Collector Abstraction 完成记录（2026-08-19）

- [x] Collector Contract ADR、Registry、Capability、Identity 与 System Error
- [x] PddCollector/PddAdapter 结构迁移；核心 TaskEngine/Quality 层移除 PDD 实现依赖
- [x] Android/Python before-after compatibility
- [x] PDD accepted/rejected 真实 Oracle compatibility
- [x] Phase 1～6A 最终 Oracle strict `46/46 PASS`（PR #2 Review fixes 后）；全量适用门禁通过
- [x] 未接入 JD、淘宝、1688；未进入 Phase 6B

验收见 `docs/tasks/phase6a-acceptance.md`。Phase 6A 已 ACCEPTED；Phase 6B 为 NOT STARTED，仍需 Product Owner 明确批准。
