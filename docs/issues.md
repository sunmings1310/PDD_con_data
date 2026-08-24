# 当前问题、潜在 Bug 与技术债务

> **Status: HISTORICAL / SUPERSEDED AS CURRENT AUTHORITY（2026-08-25）**
> 本文保留早期审计问题及其历史证据，部分问题已由后续阶段关闭。当前开放缺口以 [`gaps/current.md`](gaps/current.md) 为准，当前实现以 [`CURRENT_STATE.md`](CURRENT_STATE.md) 为准；不能仅凭本文旧条目实施。

> 分级：P0 阻断/数据或凭据高风险；P1 高优先级；P2 中优先级；P3 低优先级。  
> “潜在”表示静态证据明确但尚未完成对应运行场景复现；无法确认的信息标为 **UNKNOWN**。

## P0

### 1. 源码中存在默认数据库凭据、JWT secret 和 Android 签名口令

- `server/config.py` 提供 Oracle host/user/password 和固定 JWT secret 默认值。
- `android_collector/app/build.gradle.kts` 写入 release keystore 路径及 store/key password。
- 风险：源码泄漏即可伪造 Token、尝试数据库连接或签名 APK；环境变量缺失时服务会直接采用默认值。
- 当前 `.env` 是否覆盖、这些值是否仍有效、keystore 是否在仓库外均为 **UNKNOWN**。

### 2. 密码哈希算法不适合保存用户密码

- `server/auth_util.py` 和 `server/init_rbac_schema.py` 使用固定 salt + 单次 SHA-256。
- 无每用户随机 salt，无慢哈希成本；数据库泄漏后容易离线爆破。
- 建议目标：Argon2id/bcrypt/scrypt，并设计兼容登录迁移。

## P1

### 3. 服务端运行依赖缺失：`jwt` 未在 `requirements.txt` 声明

- `server/auth_util.py` 直接 `import jwt`。
- 本次 `python -c "import jwt"` 复现 `ModuleNotFoundError`。
- 当前 requirements 无 `PyJWT`，全新环境按文档安装后服务端导入会失败。

### 4. 前端在当前 Node 环境无法构建，且项目未声明 Node 版本

- 本次 Node v20.11.1 执行 `npm run build` 失败：依赖从 `node:util` 导入当前 Node 不提供的 `styleText`。
- `package.json` 没有 `engines`，README 也没有 Node 版本要求。
- 已存在的 `web/dist` 来源、是否对应当前源码、最后成功构建环境为 **UNKNOWN**。

### 5. 大量源码/README/用户可见字符串已出现 mojibake

- 根 README、Android README、Python docstring、服务端消息、前端错误消息和部分 Kotlin 字符串均可见 `骞冲彴...`、`Æ½Ì¨...` 等乱码。
- 这不是当前 PowerShell 单独显示问题：按 UTF-8 读取文件得到的内容本身已是 mojibake。
- 潜在影响：UI 文案不可读、错误判断依赖文案时失效、解析关键词/默认测试词错误、文档不可用。
- 原始正确编码和可恢复源为 **UNKNOWN**；修复前需要逐文件备份和语义核对。

### 6. 服务端启动时自动执行 DDL，迁移机制不可审计且可能阻断启动

- lifespan 在建立连接池后直接执行 `ensure_schema_patches()`。
- 迁移以查询字典 + 即时 DDL 实现，没有版本表、迁移编号、checksum、回滚或部署锁。
- 每次启动还执行 `ALTER TABLE SJZQ_TASK MODIFY ...`。
- 多实例并发启动、部分 DDL 成功后的恢复行为和所需 Oracle 权限为 **UNKNOWN**。

### 7. 数据库没有外键，删除/状态更新容易产生孤儿和不一致

- 初始化 DDL 只有主键/唯一键/索引，没有任务-任务项、商品-图片、用户-角色等外键。
- 应用代码承担全部关联完整性；异常中断或未来脚本直写可能留下孤儿记录。
- 当前 Oracle 中是否另有人工添加的约束为 **UNKNOWN**。

### 8. Agent API/WS 的设备认证强度不足或不一致

- Agent 主要以 `device_key` 注册、心跳、拉取和上报，未见标准 Token 轮换机制。
- 投屏发布 WS 也使用设备键；Android Manifest 允许明文流量。
- 如果服务经 HTTP 暴露，设备键可能被窃取并用于伪造设备/上报；实际 TLS/反代部署为 **UNKNOWN**。

### 9. CORS 配置过宽

- `server/main.py` 配置 `allow_origins=["*"]`、所有方法/头，同时 `allow_credentials=True`。
- 与 Bearer/localStorage 组合会扩大跨站调用面；具体 Starlette 对通配 origin + credentials 的响应细节需运行验证，但配置意图本身过宽。

### 10. Android 测试当前环境不可运行

- 本次 `gradlew.bat testDebugUnitTest` 在执行 Gradle 前即失败：未设置 `JAVA_HOME` 且 PATH 无 Java。
- 因此 3 个 JUnit 类的当前通过状态为 **UNKNOWN**。

## P2

### 11. 服务端和 Web 基本没有自动化测试

- 未发现 pytest 配置或服务端测试；未发现 Vitest/Jest/Cypress/Playwright 前端测试。
- 任务领取、审核、幂等、权限、Oracle 事务、Excel 回填、OTA、投屏等关键路径缺少回归保护。
- `run_test.py` 是依赖真实 BitBrowser 和页面的手工脚本，不能替代单元/集成测试。

### 12. 关键模块过大、职责集中

- `android/.../PddActions.kt` 约 114 KB。
- `detail_parser.py` 约 1,400 行；`tasks.py` 约 831 行；`excel_match.py` 约 647 行；`TaskEngine.kt`、`A11yHelper.kt` 也很大。
- 页面选择器、流程控制、解析、重试、持久化/上报相互交织，修改回归面大。

### 13. API 路由直接包含大量 SQL 和领域逻辑

- 多个 router 直接执行长 SQL、更新状态、写日志、转换响应。
- 缺少 repository/service 边界，Oracle 方言散布在 HTTP 层，不利于测试和事务边界审计。

### 14. API 响应/错误模型不统一

- 有的业务失败返回 HTTPException，有的返回 `ApiOk(ok=False)`；前端 Axios 拦截器会对 `ok:false` 主动 reject。
- Web 页面部分再次检查 `if (!res.ok)`，这段分支在统一拦截器下通常不可达。
- WebSocket not-found/fallback 又返回普通对象，客户端错误处理语义不一致。

### 15. 前后端/Agent 没有共享的版本化契约

- Pydantic schema 只覆盖部分 API；Android 手工用 `JSONObject` 拼字段，Vue 手工写 URL/请求体。
- 字段重命名、空值语义和枚举状态容易漂移；没有 OpenAPI client 生成或契约测试。

### 16. 数据库 schema 存在两套初始化来源和运行时漂移

- `init_schema.py`/`init_rbac_schema.py` 建基线，`migrate.py` 再补表/列/视图/权限。
- 仅运行服务不能从空 Oracle 完整创建基线表；仅运行 init 又不能得到最新 schema。
- 新环境的规范安装顺序未写入 README，实际当前 schema 为 **UNKNOWN**。

### 17. `T_GOODS_LIBRARY` 兼容视图存在行为分叉

- 若同名正式表存在，迁移直接返回；否则创建映射 `SJZQ_PRODUCT` 的视图。
- 两种部署下的数据写入/读取语义可能不同，代码没有显式适配层。
- 哪种形态是当前目标生产形态为 **UNKNOWN**。

### 18. 日志缺少集中配置、轮转和关联 ID

- FastAPI 仅依赖 Uvicorn/外部重定向；业务日志分散在 Oracle 表、文本文件和 Android/UI。
- 未见 request/task/device 统一 correlation id、结构化日志、保留/轮转配置或敏感字段清洗。
- 现有 `server/data/*.log` 已进入工作树运行目录。

### 19. WebSocket/投屏状态只在单进程内存

- `ws_hub` 和 `cast_state` 保存内存连接/房间。
- 多 worker/多实例无法共享状态，服务重启会断开并遗失会话；当前部署是否单实例为 **UNKNOWN**。

### 20. 同步阻塞工作位于 FastAPI 请求路径

- Oracle 驱动使用同步连接，Excel 解析/生成、图片读取/下载、OCR 也多为同步操作。
- 大文件或慢 OCR 可能占用服务线程；并发容量、请求体限制和超时策略为 **UNKNOWN**。

### 21. 图片/Excel 外部 URL 获取需要更严格边界

- Excel 导出路径可按商品图片 URL 下载内容，代码使用标准 URL 请求。
- 需要确认是否限制 scheme、目标网段、响应大小、重定向和超时，避免 SSRF/内存或磁盘压力。
- 本次未做网络攻击性验证；实际可利用性为 **UNKNOWN**。

### 22. Android Room 没有 migration 策略

- schema version 固定为 1，`exportSchema=false`，未注册 migration。
- 未来实体字段变化会造成升级失败；当前已发布 APK 本地数据库版本均为 1 可由代码推断，但设备真实状态为 **UNKNOWN**。

### 23. 任务/商品上报的幂等性需要专项验证

- Agent 网络重试可能重复调用商品/图片/进度/完成接口。
- 数据库没有明显覆盖所有上报路径的幂等 key/唯一约束；`PLATFORM_CODE, ITEM_ID` 只有普通索引。
- 断网重连是否产生重复商品、重复图片、计数多加需端到端验证，当前为 **UNKNOWN**。

### 24. 桌面链路与新调度链路重复实现同一领域

- Python 与 Kotlin 分别实现列表/详情解析、拟人节奏、目标匹配、数据模型。
- 两套输出 schema、修复和平台规则可能漂移；根 README 仍只介绍旧链路。
- 旧桌面端是否仍在生产使用为 **UNKNOWN**。

## P3

### 25. README 严重滞后

- 根 README 未提 server/web/Android/Oracle。
- Web README 是 Vite 模板。
- Android README 未覆盖联机调度、OTA、投屏；其 AGP 版本描述与实际不一致。

### 26. 生成物和运行数据混在项目目录

- 当前目录可见 `node_modules`、`web/dist`、Android `.gradle`/`build`、多个 APK、`__pycache__`、服务日志、图片和 latest APK。
- `.gitignore` 虽覆盖多数路径，但当前目录不是可由 `git` 命令识别的仓库，哪些文件实际受版本控制为 **UNKNOWN**。
- 大量生成物增加审查、备份和发布混淆风险。

### 27. Android 版本字段不直观

- `versionCode=70`，`versionName=1.0.69`；`dist` 中最高可见命名 `1.0.69`。
- 可能是有意让 code 领先，也可能是发布脚本偏移；预期规则 **UNKNOWN**。

### 28. Android release 配置注释与可维护性较差

- 构建脚本含已乱码的历史性说明，签名/混淆策略直接写在模块脚本。
- 建议将秘密移到本机/CI secret，并把发布版本、产物命名和 OTA metadata 生成统一为可审计脚本。

### 29. 平台扩展目前主要是占位

- 服务端种子/常量有天猫、京东、抖音，但默认禁用；Android 自动化实现和桌面搜索模板只确认拼多多。
- 其他平台的路由/解析/测试均未发现完整实现，应视为未完成占位，而不是已支持能力。

### 30. 异常捕获和降级过宽

- DB 行转换、健康检查、OCR、自动化解析和 Android `runCatching` 中存在宽泛捕获。
- 部分路径返回 `None`/false 或只记录短消息，可能隐藏根因；需按关键数据流补充异常类型、上下文和可观察性。

## 未完成或临时代码清单

- 多平台：天猫/京东/抖音仅字典/种子预留，完整实现未发现。
- `T_GOODS_LIBRARY`：注释明确为“现阶段映射”的兼容视图；正式表接入状态 **UNKNOWN**。
- `server/static`：作为未 build 时的 legacy 回退，与 Vue 管理端并存。
- 根目录旧桌面端与 Android/服务端新架构并存，迁移/退役计划 **UNKNOWN**。
- 未发现显式 `TODO`/`FIXME` 标记；这不代表上述占位或迁移工作已完成。

## 建议验证顺序（不涉及本次代码修改）

1. 建立受支持工具链清单：Python、Node、JDK、Android SDK、Oracle client/模式版本。
2. 从干净环境按文档安装，先复现服务导入、Web 构建、Android 单测。
3. 对 Oracle 做只读 schema 对账，确认基线/补丁、约束、索引和 `T_GOODS_LIBRARY` 实际类型。
4. 用测试 Oracle + 模拟 Agent 覆盖任务创建→审核→领取→上报→完成，以及重复请求/断网重连。
5. 用真机/固定 App 版本跑 Android 解析测试，记录页面版本、输入和产物。
6. 确认旧桌面端是否仍需维护，再决定共享规则、冻结或退役策略。

