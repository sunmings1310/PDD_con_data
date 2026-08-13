# 当前代码库状态

> 检查日期：2026-08-13  
> 检查范围：`D:\work\PDD_con_data`（排除第三方依赖、编译缓存和图片内容的逐文件审阅）  
> 原则：仅记录静态代码、现有运行日志和本次可复现检查所能确认的事实；不能确认处标为 **UNKNOWN**。

## 1. 总览

该仓库实际包含三套可独立启动、又可协同工作的应用，以及一套仍保留的旧桌面采集链路：

1. **旧桌面端采集器**：根目录 Python + PyQt6 + Playwright/BitBrowser + SQLite/Excel。
2. **调度服务端**：`server/`，FastAPI + Oracle，提供管理 API、Android Agent API、WebSocket、静态资源和 OTA。
3. **管理前端**：`web/`，Vue 3 + Vite + Element Plus。
4. **Android 采集端**：`android_collector/`，Kotlin + AccessibilityService + Room + OkHttp。

源代码规模（本次统计）：Python 41 文件/约 8,989 行，Kotlin 33 文件/约 7,847 行，前端 JS/Vue 22 文件/约 2,485 行。仓库中还存在 `node_modules/`、Android `.gradle/`/`build/`、`web/dist/`、APK、服务日志、采集图片和 `__pycache__/` 等生成物或运行数据。

## 2. 目录结构

```text
D:\work\PDD_con_data\
├─ main.py                         # 旧 PyQt6 桌面端入口
├─ ui_window.py                    # 桌面 UI
├─ task_runner.py                  # 桌面采集任务编排
├─ browser_client.py               # BitBrowser API/CDP 接入
├─ list_parser.py                  # 搜索列表解析
├─ search_sort.py                  # 搜索、排序、候选选择
├─ detail_parser.py                # 商品详情/规格/价格解析
├─ excel_target.py                 # Excel 目标读取和匹配
├─ storage_exporter.py             # SQLite 持久化、Excel/CSV 导出
├─ config_manager.py / config.json # 桌面配置
├─ run_test.py                     # 依赖真实浏览器环境的手工端到端脚本
├─ requirements.txt                # Python 依赖
├─ server/
│  ├─ main.py                      # FastAPI 入口
│  ├─ config.py / .env             # 服务配置（.env 存在但内容未写入本文）
│  ├─ db.py                        # Oracle 连接池与行转换
│  ├─ schemas.py                   # Pydantic 输入/输出模型
│  ├─ services.py                  # 设备、平台、任务日志公共服务
│  ├─ auth_util.py                 # JWT、密码哈希、RBAC、操作日志
│  ├─ migrate.py                   # 启动时增量 schema 补丁
│  ├─ init_schema.py               # 核心业务表初始化
│  ├─ init_rbac_schema.py          # RBAC 表及种子初始化
│  ├─ routers/                     # 12 个 API/WS 路由模块
│  ├─ static/                      # 旧管理页回退资源
│  └─ data/                        # 日志、图片、APK 等运行数据
├─ web/
│  ├─ src/router/                  # Vue Router 与权限元数据
│  ├─ src/stores/                  # Pinia 用户状态
│  ├─ src/api/http.js              # Axios 拦截器
│  ├─ src/views/                   # 设备、任务、商品、Excel、账号、报表、RBAC 页面
│  ├─ vite.config.js               # 开发代理到 127.0.0.1:8080
│  ├─ package.json / package-lock.json
│  └─ dist/                        # 已存在的构建产物
└─ android_collector/
   ├─ app/src/main/java/com/collector/pdd/
   │  ├─ ui/                       # Activity 与 UI 状态
   │  ├─ service/                  # 无障碍服务、节点操作、粘贴浮层
   │  ├─ engine/                   # 任务引擎、平台动作、匹配、拟人行为
   │  ├─ parser/                   # 详情解析
   │  ├─ data/                     # Room 实体、DAO、数据库
   │  ├─ net/                      # Agent 协调、HTTP、OTA、服务端偏好
   │  ├─ cast/                     # MediaProjection 投屏
   │  └─ export/                   # CSV 导出
   ├─ app/src/test/                # 3 个 JUnit 测试类
   ├─ build.gradle.kts             # AGP/Kotlin/KSP 版本
   └─ dist/                        # 多个历史 APK
```

## 3. 启动入口

| 子系统 | 入口 | 启动方式 | 本次确认结果 |
|---|---|---|---|
| 桌面端 | `main.py` | `python main.py` | 静态编译通过；GUI/BitBrowser 真实运行未执行，**UNKNOWN** |
| 服务端 | `server/main.py` | `python -m server.main` 或 `server/run.ps1` | 静态编译通过；已有日志证明曾在 `0.0.0.0:8080` 启动并处理请求；本次未连接 Oracle启动 |
| 前端开发 | `web/src/main.js` | `cd web; npm run dev` | 未启动 |
| 前端构建 | `web/package.json` | `cd web; npm run build` | 失败，详见验证和 `issues.md` |
| Android | Manifest 中 `.ui.MainActivity` | Android Studio 或 `gradlew.bat` | 本次测试因没有 JDK/JAVA_HOME 而未开始 |

服务端启动生命周期会创建图片目录、建立 Oracle 连接池、执行 `ensure_schema_patches()`，退出时关闭连接池。若 `web/dist/index.html` 存在，FastAPI 同时托管 SPA；否则回退到 `server/static/index.html`。

## 4. 核心模块

### 4.1 桌面端

- `ui_window.py`：读取/编辑配置、控制任务启停、展示日志和历史任务。
- `task_runner.py`：在线程中管理任务状态，连接 BitBrowser，执行关键词或 Excel 目标任务，调用解析器并持久化结果。
- `browser_client.py`：调用 BitBrowser 本地 API并通过 Playwright CDP 接管页面。
- `list_parser.py`、`search_sort.py`：构造搜索 URL、列表提取、排序与候选选择。
- `detail_parser.py`：详情页、SKU、价格、批准文号等解析；单文件约 1,400 行。
- `storage_exporter.py`：SQLite `workbench.db` 和 Excel/CSV 输出。
- `human_behavior.py`：延迟、鼠标、滚动等节奏控制。

### 4.2 服务端

- `server/main.py`：应用装配和静态资源托管。
- `server/routers/tasks.py`：任务创建、查询、失败项重排、异常上传、审核、Agent 拉取、进度、完成；约 831 行。
- `server/routers/products.py`：商品上传、图片上传/过滤、查询、编辑、软删除、入库。
- `server/routers/devices.py`：Agent 注册、心跳、绑定、终止任务、设备任务列表。
- `server/routers/excel_match.py`：Excel 解析、匹配、导出和未匹配项转任务；约 647 行。
- `server/auth_util.py` + `routers/auth.py`/`users.py`：JWT、用户、角色、权限和操作日志。
- `server/ws_hub.py`、`cast_state.py`、`routers/cast.py`：管理端事件推送和设备投屏中继。
- `server/ota_meta.py`、`routers/ota.py`：APK 元信息、上传、推送和确认。
- `server/image_filter.py`：Pillow + Tesseract 的图片文字过滤。

### 4.3 Web 管理端

- `router/index.js`：设备、任务、商品、Excel、账号、报表、人员、角色、日志、设置、个人中心路由；路由元数据声明权限。
- `stores/user.js`：Token 用户态、权限和仪表盘数据。
- `api/http.js`：Bearer Token 注入、统一 API 响应和 401 跳转。
- 各 `views/` 页面直接调用对应 REST/WS 接口；没有单独的领域 service 层。

### 4.4 Android Agent

- `CollectA11yService` + `A11yHelper`：无障碍节点访问与点击/滑动。
- `TaskEngine`：任务状态机和单目标采集流程。
- `PddActions`：拼多多页面操作，约 114 KB，是 Android 侧最大热点文件。
- `DetailReader`：详情文本/价格/规格解析。
- `AgentCoordinator`：注册、心跳、拉取任务，桥接 `TaskEngine` 与 `ApiClient`，上报进度、商品、图片、异常和完成状态。
- `ApiClient`：同步 HTTP 调用服务端 Agent API。
- `AppDatabase`/DAO：本地 Room 数据库 `pdd_collector.db`，保存任务和商品。
- `ScreenCastService`：MediaProjection 投屏；`ApkUpdater`：OTA 下载/安装。

## 5. 配置文件

| 文件 | 作用 | 观察 |
|---|---|---|
| `config.json` | 旧桌面端浏览器、节奏、过滤、输出、平台配置 | 含已失效/乱码的绝对路径 `_output_dir_abs`；运行时处理方式见 `ConfigManager` |
| `server/config.py` | Oracle、HTTP、JWT、图片目录默认值 | 可由 `server/.env`/环境变量覆盖；源代码含可用默认凭据和 JWT secret |
| `server/.env` | 服务端覆盖配置 | 文件存在；为避免在文档复制秘密，具体值未列出；是否为生产实际配置 **UNKNOWN** |
| `web/vite.config.js` | alias、5173 端口、API/media/WS 开发代理 | 代理目标固定为 `127.0.0.1:8080` |
| `web/package*.json` | 前端版本与脚本 | 没有 `engines` 字段约束 Node 版本 |
| Android Gradle 文件 | SDK、依赖、签名、版本 | compileSdk 34、minSdk 26、targetSdk 33、versionCode 70、versionName 1.0.69 |
| `AndroidManifest.xml` | 权限、Activity、Service、Provider | 允许明文流量并声明安装 APK、投屏、媒体读取等权限 |
| `ServerPrefs.kt` | Agent 服务地址、设备键等本地偏好 | 实际设备当前值 **UNKNOWN** |

## 6. 数据库相关代码

### 6.1 桌面 SQLite

`storage_exporter.py` 管理 `workbench.db`，核心表包括任务日志、商品、Excel 任务/checkpoint 行。写入使用 `sqlite3`，导出使用 pandas/openpyxl。`run_test.py` 会直接读取 `product_table`。

### 6.2 Android Room

数据库名 `pdd_collector.db`，schema version 1：

- `task_log` ← `TaskEntity`
- `product_table` ← `ProductEntity`

DAO 提供任务 insert/update/get/list，以及商品 insert/list/count。未设置 migration；未来 schema 升级策略 **UNKNOWN**。

### 6.3 服务端 Oracle

`server/db.py` 创建连接池（min=1、max=8），`get_conn()` 正常提交、异常回滚。表/视图来自初始化与启动补丁：

- 核心：`SJZQ_PLATFORM`、`SJZQ_DEVICE`、`SJZQ_TASK`、`SJZQ_TASK_ITEM`、`SJZQ_TASK_LOG`、`SJZQ_PRODUCT`、`SJZQ_PRODUCT_IMAGE`。
- RBAC：`SJZQ_ROLE`、`SJZQ_ROLE_PERM`、`SJZQ_USER`、`SJZQ_OP_LOG`、`SJZQ_SYS_CONFIG`。
- 增量：`SJZQ_PLATFORM_ACCOUNT`、`SJZQ_ALERT`、`SJZQ_PRODUCT_CHANGE`、`SJZQ_TASK_ANOMALY`。
- 兼容视图：`T_GOODS_LIBRARY`（当同名正式表不存在时创建）。

代码未声明外键约束；一致性主要由应用逻辑维护。Oracle 当前真实 schema、数据量、索引状态、版本与备份策略均为 **UNKNOWN**。

## 7. 外部依赖

### Python

PyQt6、Playwright、pandas、loguru、aiohttp、httpx、openpyxl、xlrd、oracledb、FastAPI、Uvicorn、python-multipart、aiofiles、pydantic-settings、Pillow、pytesseract。代码还直接导入 `jwt`，但 `requirements.txt` 未声明 PyJWT。

### Web

Vue 3、Vue Router、Pinia、Axios、Element Plus、dayjs、Vite、`@vitejs/plugin-vue`。版本使用 caret 范围，锁文件存在。

### Android

AGP 8.1.4、Kotlin 1.9.22、KSP 1.9.22-1.0.17、AndroidX、Material、Room 2.5.2、Coroutines 1.7.3、OkHttp 4.12.0、JUnit 4.13.2。构建还依赖 JDK 17、Android SDK 和 Gradle 下载源。

### 运行时外部系统

- BitBrowser 本地 API（桌面端）。
- 拼多多 Web/App 页面结构（解析和自动化强耦合）。
- Oracle 服务。
- Tesseract OCR 可执行程序。
- Android 无障碍服务、MediaProjection 和包安装器。
- 网络/服务端实际可达性与版本兼容性 **UNKNOWN**。

## 8. 日志机制

- 桌面端：`utils.setup_logging()` 配置 Loguru，输出控制台与 `logs/app.log`；任务还通过回调写 UI。
- 服务端业务：任务运行日志写 `SJZQ_TASK_LOG`；后台管理操作写 `SJZQ_OP_LOG`；异常写 `SJZQ_TASK_ANOMALY`。
- 服务端进程：现有 `server/data/server.log`、`server/data/server.err.log`、`server/local-deploy.*.log` 表明 Uvicorn stdout/stderr 曾被外层脚本重定向。代码内没有集中式 Python logging 配置。
- Android：任务引擎通过回调在 UI/协调器中传播，并将部分消息上报服务端；完整保留周期、轮转和脱敏策略 **UNKNOWN**。

## 9. 异常处理

- Oracle `get_conn()` 保证异常回滚。
- FastAPI 多数业务错误使用 `HTTPException` 或 `{ok:false}`；统一全局异常处理器不存在。
- 桌面解析器/自动化代码包含大量局部降级和重试；真实页面失败表现依赖 BitBrowser/页面版本，**UNKNOWN**。
- Android 协调器大量使用 `runCatching`，网络层抛出异常后由轮询/任务控制层处理；离线重试的端到端一致性仅能部分从代码确认。
- 一些宽泛捕获会吞掉上下文或返回 `None`，详见 `issues.md`。

## 10. 测试与本次验证

仓库现有测试：

- `run_test.py`：真实 BitBrowser/页面依赖的手工端到端脚本，不是隔离单元测试。
- Android JUnit：`AccessGuardTest`、`ProductTargetMatcherTest`、`DetailReaderTest`。
- 服务端和 Web 没有发现项目自有自动化测试。

本次执行结果：

```text
命令: python -m py_compile <根目录、server、server/routers 下全部 Python 文件>
结果: PY_EXIT=0

命令: cd web; npm run build
环境: Node.js v20.11.1, npm 10.2.4
结果: WEB_EXIT=1
关键错误: SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'

命令: cd android_collector; .\gradlew.bat testDebugUnitTest --no-daemon
结果: ANDROID_EXIT=1
关键错误: JAVA_HOME is not set and no 'java' command could be found in your PATH.

命令: python -c "import jwt"
结果: exit 1, ModuleNotFoundError: No module named 'jwt'
```

因此：Python 语法可编译；前端当前环境不可构建；Android 测试未实际运行；服务端启动、Oracle 集成、桌面采集端到端行为和设备真机行为本次均为 **UNKNOWN**。

## 11. README 与代码一致性

- 根 `README.md` 只描述旧桌面采集器，未描述已存在的 FastAPI、Vue、Oracle、RBAC、Android Agent、OTA 和投屏，明显过期。
- 根 README 所列桌面主模块仍存在，`python main.py` 入口也一致；但示例磁盘路径与当前仓库路径不一致。
- `android_collector/README.md` 的无障碍采集、Room、CSV 和目录说明与主结构大体一致，但未覆盖联机 Agent、服务端调度、投屏、OTA 和大量后续功能。
- Android README 写 AGP 8.5，而实际插件为 AGP 8.1.4；写“独立包名”的描述与实际 `applicationId=com.linkdesk.tool` 需要产品语义确认。
- `web/README.md` 仍是 Vite 模板说明，没有项目启动、后端依赖、权限和构建环境说明。
- 多个 README、源码注释和用户可见字符串存在明显 mojibake；原始编码/迁移历史 **UNKNOWN**。

