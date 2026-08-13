# T001：建立项目可重复构建环境——现状分析

> 项目：稳定数据采集系统升级项目  
> 阶段：第一阶段，仅分析，不实施修改  
> 分析日期：2026-08-13

## 1. 结论摘要

当前仓库包含三套可独立运行或构建的工程：根目录 Python 桌面采集端、`server/` FastAPI 服务端、`web/` Vue 管理端，以及 `android_collector/` Android Agent。仓库已有部分依赖清单、锁文件和 Gradle Wrapper，但尚未形成从干净环境可重复安装、构建、启动的统一基线。

主要阻断如下：

1. Python 仅有一个范围版本形式的 `requirements.txt`，桌面端、服务端和可选 OCR 能力混在一起；代码直接导入 `jwt`，但清单未声明 `PyJWT`。
2. Web 有 `package-lock.json`，但未声明 Node/npm 版本。锁定的 Vite 8.2.1 和 `@vitejs/plugin-vue` 6.0.8 要求 Node `^20.19.0 || >=22.12.0`，当前 Node 20.11.1 无法构建。
3. Android 源码已约束 Java 17、Gradle 8.4、compile SDK 34，但构建脚本依赖另一个仓库中的私有工具目录，并在找不到时扫描 `D:\`；环境说明和实际插件版本也有偏差。
4. 启动方式分散在根 README、`server/run.ps1`、`web/run-dev.ps1`、Android Studio 说明和 `build-apk.ps1` 中，缺少统一的环境检查、安装、构建和 smoke 命令。
5. 当前已存在的 `.venv`、`web/node_modules`、`web/dist`、Android `.gradle`/`dist` 等缓存或产物不能作为干净构建证据。

因此，T001 第二阶段应只收敛工具链、依赖和文档，不触碰业务逻辑、采集流程、数据库结构或架构分层。

## 2. 当前项目目录结构

排除 `.venv`、`node_modules`、构建缓存和运行数据后，主要结构如下：

```text
PDD_con_data/
├─ main.py                    # PyQt6 桌面端入口
├─ requirements.txt           # 当前唯一 Python 依赖清单
├─ config.json                # 桌面端运行配置
├─ *.py                       # 桌面采集、解析、导出模块
├─ server/
│  ├─ main.py                 # FastAPI 服务入口
│  ├─ config.py               # Pydantic Settings；读取 server/.env
│  ├─ run.ps1                 # 服务启动脚本
│  ├─ routers/                # API 路由
│  ├─ static/                 # 旧版静态管理页
│  └─ data/                   # 运行数据，已由 .gitignore 排除
├─ web/
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ vite.config.js
│  ├─ run-dev.ps1
│  └─ src/                    # Vue 管理端源码
├─ android_collector/
│  ├─ build.gradle.kts
│  ├─ settings.gradle.kts
│  ├─ gradle.properties
│  ├─ gradlew.bat
│  ├─ gradle/wrapper/         # Wrapper 8.4
│  ├─ app/build.gradle.kts
│  ├─ local.properties.example
│  └─ build-apk.ps1
└─ docs/                      # 现状、差距、路线图、backlog 等文档
```

观察结果：

- 根目录不是可识别的 Git 工作树；本次无法用 `git status` 或提交记录判断当前文件和已有构建产物的来源关系。
- `.gitignore` 排除了根 `.venv`、`server/.env`、`server/data`，Web 自身也排除了 `node_modules` 和 `dist`；Android 排除了 `.gradle`、`local.properties` 和各级 `build`。
- 工作目录中仍实际存在 `.venv`、`web/node_modules`、`web/dist`、Android `.gradle`、`local.properties` 和 `dist`。它们只代表本机残留状态，不能证明清单完整或干净构建可行。
- `server/static` 是旧管理页；FastAPI 优先托管 `web/dist`，不存在时回退到旧页面。

## 3. Python 项目依赖管理方式

### 3.1 当前方式

- 使用根目录 `requirements.txt` 和 `pip`。
- README 指导创建根目录 `.venv`，激活后执行 `pip install -r requirements.txt`。
- 没有 `pyproject.toml`、`Pipfile`、Poetry 锁文件、constraints 文件或 `.python-version`。
- 当前清单全部使用 `>=` 下界，没有精确锁定关键版本，也没有区分桌面、服务、测试和可选功能。
- 当前本机虚拟环境为 Python 3.10.6，但仓库没有声明受支持的 Python 版本。

### 3.2 直接依赖核对

代码中可确认的第三方直接导入包括：

| 范围 | 直接依赖 |
|---|---|
| 桌面端 | PyQt6、Playwright、pandas、Loguru、httpx、openpyxl/xlrd（Excel 链路） |
| 服务端 | FastAPI、Uvicorn、oracledb、pydantic-settings、PyJWT、python-multipart、aiofiles、Pillow、pytesseract、openpyxl |
| 清单中存在但当前静态导入未证实 | aiohttp |

明确缺口：

- `server/auth_util.py` 直接执行 `import jwt`，对应发行包 `PyJWT`，但 `requirements.txt` 未声明。
- 当前 `.venv` 中已人工存在 `PyJWT==2.13.0`，这恰好说明现有环境依赖了清单之外的状态。
- 当前 `.venv` 并未安装 PyQt6、Playwright、pandas、aiohttp、httpx；因此它只能导入服务端主要模块，无法验证桌面端依赖闭包。
- 单一清单把 GUI、浏览器自动化、服务端和 OCR 混合安装，增加干净环境安装成本，也不利于说明哪些依赖是必需、可选或仅运行时需要。
- `>=` 会随时间解析到不同版本，无法保证未来重建结果一致。

### 3.3 Python 外部运行时依赖

- 桌面采集正式链路依赖 BitBrowser、本地 API（默认 `127.0.0.1:54345`）、已创建的浏览器环境和可访问的目标页面。
- Playwright Chromium 在 README 中标记为备用；若要使用，需另执行 `playwright install chromium`。Python 包安装本身不会提供浏览器二进制。
- OCR 依赖 `pytesseract` Python 包之外的 Tesseract 可执行文件及语言数据；仓库没有安装路径和版本要求。
- Oracle 使用 `python-oracledb`。当前代码可使用 thin 模式，但实际数据库网络、账号、服务名和 schema 是启动期外部依赖；仓库未提供可离线替代的启动配置。
- PyQt6 在无桌面会话或 CI 环境中的 GUI 启动需要额外处理；T001 至少应把“模块导入 smoke”和“真实 GUI/采集验收”分开。

## 4. Web 项目依赖和 Node 版本

### 4.1 当前依赖管理

- 包管理器为 npm，存在 lockfile v3 的 `package-lock.json`，可使用 `npm ci` 做确定性安装。
- `package.json` 未提供 `engines.node`、`engines.npm`，也没有 `.nvmrc` 或 `.node-version`。
- 运行脚本只有 `dev`、`build`、`preview`，尚无 lint/test 脚本。
- 主要依赖为 Vue、Vue Router、Pinia、Element Plus、Axios、Day.js；构建工具为 Vite 和 `@vitejs/plugin-vue`。

### 4.2 实际版本约束与构建结果

锁文件当前解析到：

- Vite 8.2.1
- `@vitejs/plugin-vue` 6.0.8
- 两者声明的 Node 要求均为 `^20.19.0 || >=22.12.0`

本机版本：

- Node v20.11.1
- npm 10.2.4

实际执行 `npm run build` 失败，关键错误为：

```text
import { formatWithOptions, styleText } from "node:util";
                            ^^^^^^^^^
SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'
Node.js v20.11.1
```

结论：这是已锁定构建工具与当前 Node 版本不兼容，不是 Vue 业务代码错误。第二阶段应先选择并声明满足锁文件要求的 Node LTS 版本，再用干净的 `npm ci && npm run build` 验证；不应通过修改业务页面绕过。

### 4.3 Web 运行关系

- 开发模式：`web/run-dev.ps1` 执行 `npm run dev`，Vite 监听 5173。
- Vite 将 `/api`、`/media`、`/ws` 代理到 `127.0.0.1:8080` 的服务端。
- 发布/集成模式：`npm run build` 生成 `web/dist`，FastAPI 从该目录托管 SPA。
- 当前 `web/dist` 已存在，但与当前源码和 lockfile 的对应关系为 UNKNOWN；不能用它替代重建验证。

## 5. Android Gradle 配置

### 5.1 已声明版本

| 项目 | 当前配置 |
|---|---|
| Android Gradle Plugin | 8.1.4 |
| Kotlin Plugin | 1.9.22 |
| KSP | 1.9.22-1.0.17 |
| Gradle Wrapper | 8.4 |
| Java 源/目标与 Kotlin JVM target | 17 |
| compileSdk | 34 |
| targetSdk | 33 |
| minSdk | 26 |

依赖版本均直接写在 `app/build.gradle.kts`，没有 version catalog。对于当前规模这不是阻断，但版本矩阵必须在环境文档中准确列出。

### 5.2 本机观察

- 系统 `PATH` 中没有 `java`，`JAVA_HOME`、`ANDROID_HOME`、`ANDROID_SDK_ROOT` 均为空。
- 另一个工作区 `D:\work\pda-picking\tools` 中实际存在 Microsoft OpenJDK 17.0.20、Android platform 34、Build Tools 33.0.1/34.0.0、Platform Tools 37.0.1 和独立 Gradle 8.4。
- 使用上述本地 JDK 和独立 Gradle 执行版本检查成功。
- 直接执行仓库 `gradlew.bat --version` 时，Wrapper 尝试联网下载 Gradle 8.4；当前受限网络返回 `java.net.SocketException: Permission denied: getsockopt`。这说明全新环境首次构建需要网络或预置 Gradle 分发缓存。
- `android_collector/local.properties` 指向另一个仓库的 SDK 路径；该文件已被忽略，不能作为可移植配置。

### 5.3 配置和脚本问题

- `android_collector/README.md` 写“Android Studio Hedgehog+（或兼容 AGP 8.5）”，但实际插件为 AGP 8.1.4，文档与构建配置不一致。
- `build-apk.ps1` 不以标准 `JAVA_HOME`/`ANDROID_HOME` 为首选，而是自动寻找 `pda-picking/tools`，必要时扫描 `D:\`。这使构建依赖特定机器目录布局。
- 脚本使用另一个仓库中的独立 `gradle.bat`，而不是优先使用本仓库 Wrapper；干净环境行为与普通 `gradlew.bat` 不一致。
- 脚本会把 APK 复制到用户桌面，并包含联网下载/解压逻辑，不适合作为最小、可预测的构建基线。
- 仓库有 `gradle-wrapper.jar`，但 Gradle 8.4 分发包和 Maven/Google 依赖仍需网络或受控缓存。
- debug 构建不需要 release 签名；release 签名配置和口令属于后续秘密管理范围，不应在 T001 中通过业务或签名逻辑修改解决。T001 的最低基线应以 `assembleDebug` 和 `testDebugUnitTest` 为主。

## 6. 当前启动方式

### 6.1 Python 桌面端

当前 README 流程：创建/激活 `.venv` → `pip install -r requirements.txt` → 可选安装 Playwright Chromium → `python main.py`。

问题：

- README 的 `cd "D:\代码库\平台数据采集"` 是失效的机器绝对路径。
- `config.json` 中还保留 `_output_dir_abs = D:\代码库\平台数据采集\output_data`，虽然可能只是派生/历史字段，但应在第二阶段确认是否被运行时使用后再决定仅文档说明还是环境化处理，不能自行改业务语义。
- 启动前没有依赖/配置检查；BitBrowser 不可用时只能在运行链路中暴露问题。

### 6.2 FastAPI 服务端

`server/run.ps1` 固定调用根目录 `.venv\Scripts\python.exe -m server.main`。`server.main` 内部通过 Uvicorn 监听配置的 host/port，默认端口 8080。

问题：

- 脚本只适用于 Windows PowerShell 且假定虚拟环境名称和位置固定。
- 启动 lifespan 会初始化 Oracle 连接池并执行 schema patch；没有可用 Oracle 时，不能完成完整服务启动验证。
- 服务读取 `server/.env` 或环境变量，但 `.env.example` 仍使用具体地址/账号形式，且缺少部分配置项说明。
- 服务端与数据库迁移目前耦合；T001 不应修改迁移或数据库结构，只能记录其为启动验证的外部前置条件。

### 6.3 Web

- 开发：先启动服务端，再进入 `web/` 执行 `npm run dev` 或 `run-dev.ps1`。
- 构建：进入 `web/` 执行 `npm run build`。
- 集成访问：构建完成后由 FastAPI 根路由托管 `web/dist`。

### 6.4 Android

- 文档路径：Android Studio 打开 `android_collector/` 后 Sync、Run 或 Build APK。
- 命令路径：设置 JDK/SDK 后运行 `gradlew.bat assembleDebug`、`gradlew.bat testDebugUnitTest`。
- 现有自动脚本：`build-apk.ps1` 依赖邻近项目工具目录，构建 debug APK 并复制到桌面和 `android_collector/dist`。

## 7. 缺失或未明确的环境依赖

| 类别 | 缺失/未明确项 | 影响 |
|---|---|---|
| Python | 受支持 Python 版本；PyJWT 声明；直接/可选依赖分组；关键版本锁定策略 | 干净安装结果不可预测，服务端可能缺包 |
| Python 外部运行时 | BitBrowser 版本/API；Playwright 浏览器；Tesseract 与语言包；Oracle 可达性和测试配置 | 包安装成功不等于功能可启动 |
| Web | Node/npm 支持版本；版本管理文件；干净 `npm ci` 验证 | 当前 Node 20.11.1 构建失败 |
| Android | JDK 17 发行版/最低补丁；Android SDK Platform 34、Build Tools、Platform Tools；标准 SDK 路径配置 | 当前依赖另一个仓库和本机路径 |
| Android 下载 | Gradle 8.4 分发、Google/Maven/插件仓库网络或离线缓存策略 | Wrapper 首次下载在受限网络失败 |
| 服务配置 | 配置项全集、覆盖优先级、开发/测试示例、Oracle 启动前置条件 | 运行依赖人工填写和历史 `.env` |
| 操作系统/工具 | 当前脚本以 Windows PowerShell 为主；未声明是否支持其他 OS；Git 状态不可用 | 新成员难以选择正确命令和 shell |
| 验证 | 统一的版本输出、安装、构建、模块导入和 smoke 命令 | 无法形成一次性可审计构建证据 |

## 8. 第一阶段实测记录

本阶段没有修改业务代码、采集流程、数据库结构或构建配置。只执行只读检查与现有命令探测。

| 检查 | 输入/命令 | 结果 |
|---|---|---|
| Python 版本 | `python --version` | `Python 3.10.6` |
| Node/npm 版本 | `node --version` / `npm --version` | `v20.11.1` / `10.2.4` |
| Web 构建 | `cd web; npm run build` | 失败，Node 20.11.1 缺少 `node:util.styleText` 导出 |
| 服务端导入 | `.venv\\Scripts\\python.exe -c "import jwt, server.main"` | 成功 |
| 桌面依赖导入 | 分别导入 PyQt6、Playwright、pandas、aiohttp、httpx | 当前 `.venv` 均失败，包未安装 |
| Android 工具版本 | 本地 JDK + 独立 Gradle 8.4 执行 `gradle --version` | 成功：JVM 17.0.20，Gradle 8.4 |
| Gradle Wrapper | 设置本地 JDK/SDK 后执行 `gradlew.bat --version` | 首次下载 Gradle 分发时网络受限失败 |
| Android 完整构建/单测 | 未执行 | 当前阶段只分析；Wrapper 分发下载是前置阻断 |

说明：当前 `.venv` 和 `node_modules` 不是干净安装结果，因此上述成功或失败只用于定位现状，不能作为第二阶段验收证据。

## 9. 第二阶段建议实施边界

待确认后，建议按以下顺序实施：

1. 明确并记录支持矩阵：Python、Node/npm、JDK、Gradle、Android SDK/Build Tools。
2. 补齐 Python 直接依赖并采用可复现的关键版本约束；明确桌面、服务端及 OCR/Playwright 外部依赖边界。
3. 为 Web 声明 Node/npm 要求，在符合要求的干净环境执行 `npm ci` 和 `npm run build`；仅修复构建兼容问题，不改页面业务。
4. 让 Android 标准构建优先使用环境变量、`local.properties` 和仓库 Wrapper，消除对 `pda-picking/tools` 目录布局的强依赖；验证 debug assemble 和单元测试。
5. 新增 `docs/development-environment.md`，统一记录安装、配置、构建、启动、验证和已知外部依赖。
6. 更新根 README，使桌面端、服务端、Web 和 Android 的入口与文档互相一致。
7. 完成后再更新 `docs/backlog.md` 的 T001/对应 BL-001、BL-002 状态和真实验证结果。

## 10. 待确认事项

以下事项会影响第二阶段方案，实施时应以最小变更和实测为准：

1. Python 版本建议以当前已运行的 3.10 系列为基线，还是升级到更新版本后再锁定。
2. Web 是采用满足当前 Vite 8 的 Node 20.19+ / 22.12+，还是降级 Vite 以兼容现有 Node 20.11.1。基于锁文件现状，优先建议升级 Node 并保持前端依赖不变。
3. Android 构建是否必须支持完全离线；若是，需要明确 Gradle 分发和 Maven 依赖缓存/镜像的交付方式。
4. 旧 PyQt6 桌面端是否属于 T001 必须完整安装和 smoke 的正式交付物。未确认前建议保留并验证关键模块导入，不删除或降级其依赖。
5. Tesseract OCR 是必需能力还是可选能力；这决定环境文档的强制前置项和 smoke 范围。
6. 服务启动验收是否有可用的 Oracle 测试环境。没有测试库时，只能完成模块导入和配置检查，不能把完整 FastAPI lifespan 启动标记为通过。

---

**阶段结论：** 第一阶段分析已完成。下一步应等待确认后进入依赖、工具链和文档修改；本阶段不修改任何业务实现。
