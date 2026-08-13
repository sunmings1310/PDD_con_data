# T001 执行结果

> 日期：2026-08-13  
> Status: DONE  
> 最终验收：项目负责人于 2026-08-13 验收通过  
> 范围：依赖、工具链、构建、启动与开发环境文档；未修改业务逻辑、采集逻辑、数据库结构、API 行为或页面功能。

## 最终验收依据

- Python 干净环境依赖安装通过。
- Python 核心模块导入通过。
- Web 干净安装通过。
- Web production build 通过。
- Android debug assemble 通过。
- 开发环境及工具链版本已经文档化。

## 1. 修改文件

- `.python-version`：声明 Python 3.10.6 基线。
- `.nvmrc`：声明 Node 22.18.0 基线。
- `.gitignore`：排除临时验证环境和本地工具目录。
- `requirements.txt`：固定直接依赖版本并补充 PyJWT。
- `web/package.json`、`web/package-lock.json`：声明 Node 22.18.x/npm 10.x。
- `android_collector/build-apk.ps1`：改用标准环境变量和仓库 Wrapper，移除对其他项目目录、磁盘扫描和桌面复制的依赖。
- `android_collector/local.properties.example`、`android_collector/README.md`：明确 JDK/Gradle/SDK 和本机路径规则。
- `README.md`：统一安装、构建、启动入口。
- `docs/development-environment.md`：新增完整开发/首次部署说明。
- `docs/backlog.md`：记录 BL-001、BL-002 的实际验收状态。
- `docs/tasks/T001-result.md`：记录本结果。

## 2. 环境基线

- Python：3.10.6（3.10.x）
- Node.js：22.18.x；验收为 22.18.0
- npm：10.x；验收为 10.9.3
- JDK：17；验收为 Microsoft OpenJDK 17.0.20
- Gradle：8.4
- Android：AGP 8.1.4、Kotlin 1.9.22、SDK Platform 34、Build Tools 34.0.0、minSdk 26、targetSdk 33

## 3. 实际验证

### Python 依赖安装：PASS

```powershell
python -m venv .venv-t001
.\.venv-t001\Scripts\python.exe -m pip --isolated install -r requirements.txt
```

结果：退出状态 0；固定依赖全部安装成功。

### Python 核心导入：PASS

```powershell
.\.venv-t001\Scripts\python.exe -c "import jwt, server.main, PyQt6, playwright, pandas, oracledb, aiohttp, httpx, PIL, pytesseract; print('PYTHON_IMPORTS_OK')"
.\.venv-t001\Scripts\python.exe -m pip check
```

结果：`PYTHON_IMPORTS_OK`；`No broken requirements found.`；退出状态均为 0。

### Python 服务启动：PASS（合理检查阶段）

```powershell
$env:ORACLE_HOST='127.0.0.1'; $env:ORACLE_PORT='1'
.\.venv-t001\Scripts\python.exe -m server.main
```

结果：Uvicorn 输出 `Started server process`、`Waiting for application startup`，随后在现有 lifespan 的 Oracle 初始化阶段返回 `DPY-6005`/连接拒绝。证明服务可由干净依赖启动到外部数据库检查边界；没有可用测试 Oracle，因此未声称完整就绪。

### Web 依赖安装：PASS

```powershell
# Node v22.18.0 / npm 10.9.3
cd web
npm ci
```

结果：`added 127 packages`，退出状态 0，无 `EBADENGINE`。

### Web build：PASS

```powershell
cd web
npm run build
```

结果：Vite 8.2.1 转换 1665 modules，`built in 5.70s`，退出状态 0。仅有大 chunk 性能告警，不影响构建。

### Android build：PASS

```powershell
# JDK 17.0.20 / Gradle 8.4 / Android SDK 34
gradle.bat assembleDebug --no-daemon --console=plain --rerun-tasks
```

结果：退出状态 0，debug APK 重新构建成功。Wrapper 首次分发下载在当前网络中超时；使用同版本已安装 Gradle 完成验证。

### Android 单元测试：FAIL（既有测试）

```powershell
gradle.bat testDebugUnitTest --no-daemon --console=plain
```

结果：共 15 项，12 通过、3 失败。失败均在 `DetailReaderTest`：2 项为本地 JVM 未 mock `org.json.JSONObject.put`，1 项为期望 `63.5` 实际 `null`。本任务不修改采集/解析逻辑，因此如实保留。

## 4. 遗留问题

1. **必须后续解决**：缺少隔离的测试 Oracle，尚未在测试环境验证服务完成 lifespan/readiness；现有原项目 Oracle 已通过只读连接和 `SELECT 1 FROM dual`。
2. **必须后续解决**：Android `DetailReaderTest` 有 3 项既有失败，需要独立测试/解析任务处理。
3. **环境问题**：当前网络下 Gradle Wrapper 首次分发下载超时；全新隔离环境需可访问 Gradle/Maven 依赖、组织镜像或预置缓存。
4. **工程优化，可暂缓**：Android SDK command-line tools 与 AGP 产生 SDK XML 版本兼容警告，但本次 assemble 成功。
5. **可暂缓**：Web 产物存在单 chunk 超过 500 kB 的性能告警，不属于 T001 构建阻断；待性能指标证明需要后处理。

## 5. 完成判断

**Status: DONE**。项目负责人已于 2026-08-13 验收通过：Python 干净安装和核心导入、Web 干净安装和 production build、Android debug assemble 均已实际执行；版本约束、启动方式和开发环境文档已建立。遗留问题已登记到 `docs/backlog.md`，不在 T001 中继续处理。
