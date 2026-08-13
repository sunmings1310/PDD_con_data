# 平台数据采集工作台

本仓库包含四个交付组件：PyQt6 桌面采集端、FastAPI 中控服务、Vue 管理端和 Android 采集 Agent。完整工具链、外部依赖和首次部署说明见 [`docs/development-environment.md`](docs/development-environment.md)。

## 环境基线

| 组件 | 支持版本 |
|---|---|
| Python | 3.10.6（3.10.x 基线） |
| Node.js | 22.18.x |
| npm | 10.x |
| JDK | 17 |
| Gradle | 8.4 Wrapper |
| Android | AGP 8.1.4；SDK Platform 34；Build Tools 34.0.0 |

版本文件：根目录 `.python-version`、`.nvmrc`，Web 的 `package.json`/`package-lock.json`，Android 的 Gradle Kotlin DSL 和 Wrapper 配置。

## Python 安装

```powershell
python --version  # 应为 Python 3.10.x
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "import jwt, server.main, PyQt6, playwright, pandas, oracledb; print('Python imports OK')"
```

Playwright 自带浏览器仅作为备用，使用前另执行：

```powershell
playwright install chromium
```

### 桌面端

正式采集还需要安装并启动 BitBrowser、开启本地 API，并至少创建一个浏览器环境。

```powershell
.\.venv\Scripts\python.exe main.py
```

### FastAPI 服务端

服务端对 Oracle 与 JWT 配置执行启动校验。development 可复制
`server/.env.example` 为 `server/.env` 并替换所有占位符；test/production
建议完全通过环境变量注入。环境变量优先于 `.env`，不要提交密码或 Token。

```powershell
Copy-Item server\.env.example server\.env
# 编辑 server/.env
.\server\run.ps1
```

必填变量：`APP_ENV`（`development`/`test`/`production`）、
`ORACLE_HOST`、`ORACLE_PORT`、`ORACLE_SERVICE`、`ORACLE_USER`、
`ORACLE_PASSWORD`、`JWT_SECRET`。JWT 默认使用 `HS256`、12 小时有效期，
也可通过 `JWT_ALGORITHM=HS256`、`JWT_EXPIRE_SEC` 显式设置；production
会拒绝弱、已暴露或占位 JWT Secret。错误仅报告字段和原因，不回显 Secret。

全新数据库首次初始化超级管理员时，另通过环境变量提供
`INITIAL_ADMIN_USERNAME` 和至少 12 字符的 `INITIAL_ADMIN_PASSWORD`。系统不再
提供固定默认管理员密码，初始化脚本不会输出密码；由部署负责人通过安全渠道交付。

默认地址为 `http://127.0.0.1:8080`。服务启动会连接 Oracle 并执行现有 schema patch，因此完整启动验证需要可用的测试 Oracle。

## Web 管理端

Node 20.11 不能构建当前已锁定的 Vite 8；锁文件中的 Babel 8 依赖还要求 Node 22.18+，因此基线固定为 22.18.x。

```powershell
cd web
node --version  # 应为 v22.18.x
npm ci
npm run build
```

开发模式先启动 FastAPI，再运行：

```powershell
cd web
npm run dev
```

Vite 默认监听 5173，并将 API、媒体和 WebSocket 请求代理到 8080。正式 build 写入 `web/dist`，由 FastAPI 托管。

## Android Agent

需要 JDK 17、Android SDK Platform 34、Build Tools 34.0.0。首次构建需要访问 Gradle 和 Maven 仓库，或预先准备对应缓存。

```powershell
cd android_collector
$env:JAVA_HOME = '<JDK 17 目录>'
$env:ANDROID_SDK_ROOT = '<Android SDK 目录>'
Copy-Item local.properties.example local.properties
# 编辑 local.properties 中的 sdk.dir
.\gradlew.bat assembleDebug testDebugUnitTest --no-daemon
```

也可在环境变量设置完成后执行 `.\build-apk.ps1`。更多信息见 [`android_collector/README.md`](android_collector/README.md)。

Release 构建另需通过 Gradle project property 或环境变量提供
`RELEASE_STORE_FILE`/`ANDROID_RELEASE_STORE_FILE`、store password、key alias
和 key password。缺少任一项时 release 明确失败；debug 不读取这些 Secret。

## 外部运行依赖

- Oracle：FastAPI 的完整启动和数据接口需要可用数据库及正确 schema。
- BitBrowser：桌面正式采集链路需要其本地 API和已登录环境。
- Tesseract OCR：图片文字过滤需要系统安装 Tesseract 及所需语言数据；不可用时 OCR 能力降级。
- Android/Gradle/Maven 仓库：Android 首次构建需要下载 Gradle 分发和依赖。

## 功能概览

- BitBrowser + Playwright 桌面采集
- SQLite 增量落库及 Excel/CSV 导出
- FastAPI 调度、设备、任务和商品接口
- Vue 管理端
- Android 无障碍采集 Agent

环境问题排查、配置变量和完整部署顺序见 [`docs/development-environment.md`](docs/development-environment.md)。
