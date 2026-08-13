# 开发与构建环境

本文定义 T001 建立的可重复开发、构建和启动基线。所有示例均从仓库根目录开始，使用 PowerShell；尖括号内容必须替换为本机或测试环境值，禁止提交密码、Token 和本机绝对路径。

## 1. 受支持工具链

| 组件 | 基线 | 约束来源 |
|---|---|---|
| Python | 3.10.6；支持 3.10.x | `.python-version` |
| pip | Python 3.10 自带版本可用 | `requirements.txt` |
| Node.js | 22.18.x | `.nvmrc`、`web/package.json` |
| npm | 10.x | `web/package.json` |
| JDK | 17 | Android Gradle 配置与构建脚本 |
| Gradle | 8.4 | `android_collector/gradle/wrapper/gradle-wrapper.properties` |
| Android Gradle Plugin | 8.1.4 | `android_collector/build.gradle.kts` |
| Kotlin/KSP | 1.9.22 / 1.9.22-1.0.17 | `android_collector/build.gradle.kts` |
| Android SDK | Platform 34、Build Tools 34.0.0、Platform Tools | `android_collector/app/build.gradle.kts` |

Web 当前锁定 Vite 8.2.1，要求 Node `^20.19.0 || >=22.12.0`；锁文件中的 Babel 8 依赖要求 Node `^22.18.0 || >=24.11.0`。为满足完整依赖闭包且避免 `EBADENGINE`，本项目选择 Node 22.18.x。

## 2. Python 环境

### 2.1 安装

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` 固定所有项目直接依赖版本，涵盖桌面端、服务端及当前 OCR 能力。`PyJWT` 是服务端直接依赖，必须显式安装。

备用 Playwright 浏览器不随 Python 包自动安装：

```powershell
playwright install chromium
```

正式桌面采集主要通过 BitBrowser CDP 接管；安装 Chromium 不替代 BitBrowser。

### 2.2 模块 smoke

```powershell
.\.venv\Scripts\python.exe -c "import jwt, server.main, PyQt6, playwright, pandas, oracledb; print('Python imports OK')"
```

该命令不连接 Oracle、不打开 GUI、不访问真实采集页面。

### 2.3 启动

桌面端：

```powershell
.\.venv\Scripts\python.exe main.py
```

服务端（development 可用本机 `.env`；test/production 推荐完全使用环境变量）：

```powershell
Copy-Item server\.env.example server\.env
# 替换所有占位符后：
.\server\run.ps1
```

加载优先级为进程环境变量 > `server/.env`；源码不提供 Oracle/JWT 可用
Secret。配置在导入/启动阶段 fail fast，错误只包含字段名和原因。

服务端启动会初始化 Oracle 连接池并执行现有迁移补丁。无测试 Oracle 时，模块导入可验证 Python 安装，但完整服务启动应记录为 BLOCKED，而不是 PASS。

## 3. Web 环境

### 3.1 安装和构建

使用版本管理器读取根目录 `.nvmrc`，或自行安装 Node 22.18.x：

```powershell
node --version
npm --version
cd web
npm ci
npm run build
```

`npm ci` 严格按 `package-lock.json` 安装并重建 `node_modules`；不要用已有 `node_modules` 代替干净安装验证。输出目录为 `web/dist`。

### 3.2 启动

```powershell
cd web
npm run dev
```

默认开发地址 `http://127.0.0.1:5173`。Vite 将 `/api`、`/media`、`/ws` 代理到 `http://127.0.0.1:8080`。生产式本地运行应先 build，再启动 FastAPI 由其托管 `web/dist`。

## 4. Android 环境

### 4.1 SDK 和环境变量

安装 JDK 17，并通过 Android Studio SDK Manager 或 `sdkmanager` 安装：

- Android SDK Platform 34
- Android SDK Build Tools 34.0.0
- Android SDK Platform Tools

当前 PowerShell 会话设置：

```powershell
$env:JAVA_HOME = '<JDK 17 目录>'
$env:ANDROID_SDK_ROOT = '<Android SDK 目录>'
$env:ANDROID_HOME = $env:ANDROID_SDK_ROOT  # 兼容部分旧工具，可选
$env:Path = "$env:JAVA_HOME\bin;$env:ANDROID_SDK_ROOT\platform-tools;$env:Path"
```

复制本机 SDK 配置：

```powershell
cd android_collector
Copy-Item local.properties.example local.properties
```

编辑 `local.properties` 的 `sdk.dir`。该文件已被忽略，不能提交。

### 4.2 构建和测试

```powershell
cd android_collector
.\gradlew.bat --version
.\gradlew.bat assembleDebug testDebugUnitTest --no-daemon
```

或：

```powershell
.\build-apk.ps1
```

脚本只读取标准环境变量并使用仓库 Gradle Wrapper，不扫描磁盘，也不依赖其他项目目录。APK 副本写入 `android_collector/dist/PddCollector-debug.apk`。

首次运行 Wrapper 会下载 Gradle 8.4，Gradle 随后会从配置的插件和 Maven 仓库下载依赖。隔离网络必须预置 Gradle 分发及依赖缓存，或配置组织批准的镜像。

## 5. 外部依赖与环境变量

### 5.1 FastAPI / Oracle

`server/config.py` 按环境变量优先、`server/.env` 次之的顺序读取配置。开发时从 `server/.env.example` 创建本机文件。

| 变量 | 用途 |
|---|---|
| `ORACLE_HOST` | Oracle 主机 |
| `ORACLE_PORT` | Oracle 监听端口 |
| `ORACLE_SERVICE` | Oracle service name |
| `ORACLE_USER` | 数据库用户 |
| `ORACLE_PASSWORD` | 数据库密码 |
| `APP_ENV` | `development`、`test` 或 `production` |
| `HOST` / `PORT` | FastAPI 监听地址和端口 |
| `PUBLIC_BASE_URL` | 对外访问前缀，可留空 |
| `HEARTBEAT_TIMEOUT_SEC` | 设备离线判定秒数 |
| `JWT_SECRET` | JWT 签名秘密 |
| `JWT_ALGORITHM` | 允许值当前仅为 `HS256` |
| `JWT_EXPIRE_SEC` | Token 有效期，60～604800 秒 |
| `IMAGE_DIR` | 图片存储目录，可选 |

Oracle port/HTTP port 必须为 1～65535；Oracle host/service/user/password 和
JWT secret 必填且不得为空。production 的 JWT secret 至少 32 字符、至少包含
三类字符，并拒绝占位符和已暴露旧值。实际密码和 JWT secret 必须通过本机或
部署环境提供；test 可使用 `_env_file=None`/纯环境变量进行隔离测试。

全新数据库首次执行 `python -m server.init_rbac_schema` 且尚无超级管理员时，
还必须通过环境变量提供 `INITIAL_ADMIN_USERNAME` 和至少 12 字符的
`INITIAL_ADMIN_PASSWORD`。脚本不提供默认账号、不输出密码；凭据由部署负责人
通过安全渠道交付。已有超级管理员的部署不读取这两个变量。用户创建和密码重置
同样要求管理员显式输入至少 12 字符的临时密码，不再使用公共固定密码。

### 5.2 Android Release Signing

Release 使用 Gradle properties `RELEASE_STORE_FILE`、
`RELEASE_STORE_PASSWORD`、`RELEASE_KEY_ALIAS`、`RELEASE_KEY_PASSWORD`，或对应
环境变量 `ANDROID_RELEASE_STORE_FILE`、`ANDROID_RELEASE_STORE_PASSWORD`、
`ANDROID_RELEASE_KEY_ALIAS`、`ANDROID_RELEASE_KEY_PASSWORD`。不得把值写入公共
`gradle.properties`、示例或文档。只有 release 任务要求这些配置；debug 不依赖。

### 5.3 桌面采集

- BitBrowser 本地 API 默认地址来自 `config.json`。
- 正式运行需要 BitBrowser 已启动、至少一个浏览器环境可用，并具有目标站点登录状态。
- 输出目录使用项目相对路径；不要把个人绝对路径写入公共配置。

### 5.4 OCR

`pytesseract` 只是 Python 绑定。启用 OCR 还需安装 Tesseract 可执行文件及所需语言数据，并确保程序可从 `PATH` 或明确配置找到它。OCR 不可用不应被误报为 Python 依赖安装失败。

## 6. 首次部署步骤

1. 获取干净源码目录，不复制旧 `.venv`、`node_modules`、`dist`、Android `.gradle` 或 `build`。
2. 安装 Python 3.10.x，创建 `.venv`，执行 `pip install -r requirements.txt` 和模块 smoke。
3. 安装 Node 22.18.x/npm 10.x，在 `web/` 执行 `npm ci`、`npm run build`。
4. development 从 `server/.env.example` 创建 `server/.env`；test/production 通过部署环境注入完整配置。
5. 确认 Oracle 可达且 schema 已按现有项目要求准备，再运行 `server/run.ps1`。
6. 若交付桌面端，安装并配置 BitBrowser；仅在需要备用浏览器时安装 Playwright Chromium。
7. 若交付 Android，安装 JDK 17 和 Android SDK 34，创建 `local.properties`，执行 Wrapper assemble 和单测。
8. 保存工具版本、命令退出状态和构建产物校验值，禁止用旧 `web/dist` 或 APK 代替本次构建结果。

## 7. 常见环境问题

### Web 报 `node:util` 没有 `styleText`

Node 版本低于当前依赖闭包要求。切换到 Node 22.18.x，删除旧安装状态后重新执行 `npm ci`，不要修改页面代码绕过。

### `ModuleNotFoundError: jwt`

确认使用项目 `.venv`，并重新执行 `python -m pip install -r requirements.txt`。依赖发行包名是 `PyJWT`，导入名是 `jwt`。

### Python 包下载出现 SSL/代理错误

检查组织代理、CA 证书和 pip 源配置。不要关闭 TLS 校验作为长期方案；在隔离环境中使用组织批准的内部镜像或离线 wheelhouse。

如果本机用户级 pip 配置残留了已失效代理，可先用 `python -m pip config debug` 定位；修正用户配置后重试。临时验收可使用 `python -m pip --isolated install -r requirements.txt` 忽略用户配置，但部署基线应修复代理来源。

### FastAPI 导入成功但启动失败

完整启动需要 Oracle。检查 `server/.env`、DNS/网络、监听端口、账号权限和现有 schema；不要把数据库不可达误判为 Python 安装失败。

### Gradle Wrapper 下载失败

首次运行需要 Gradle 8.4 分发。如果网络受限，预置与 Wrapper URL 对应的分发缓存，或使用组织镜像；不要改用未记录的全局 Gradle 版本。

### Android 找不到 SDK 或 JDK

检查 `JAVA_HOME` 指向 JDK 17，`ANDROID_SDK_ROOT` 指向 SDK 根目录，且 `platforms/android-34`、`build-tools/34.0.0` 存在。`local.properties` 的 `sdk.dir` 必须是本机实际路径。
