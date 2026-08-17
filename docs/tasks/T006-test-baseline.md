# T006：统一测试基线

## 单一入口

从仓库根目录运行：

```powershell
.\scripts\test-baseline.ps1
```

该命令分别报告 `PASS`、`FAIL`、`BLOCKED`：`FAIL` 返回 `1`；默认模式中
环境依赖缺失仅报告 `BLOCKED` 并返回 `0`；加 `-Strict` 时任一 `BLOCKED`
返回 `2`，可用于 Phase 1 验收和 CI。

```powershell
.\scripts\test-baseline.ps1 -Strict
.\scripts\test-baseline.ps1 -Suite python
.\scripts\test-baseline.ps1 -Suite oracle -Strict
.\scripts\inspect-test-env.ps1
```

入口执行四个互相独立的验证：

| 套件 | 实际命令 | 通过定义 |
|---|---|---|
| Python | `python scripts/run_python_unit_tests.py` | 所有离线单元/API/状态机测试通过；不将 Oracle 集成测试的 skip 误当通过 |
| Oracle | `python -m unittest -v tests/test_task_state_r2_oracle.py` | 8 项真实 Oracle 事务测试执行且通过（含 receipt 并发、业务去重、finish manifest、最小成功闭环） |
| Android | 固定 JDK 直接运行 Gradle Wrapper Main：`testDebugUnitTest --no-daemon` | JDK 17、SDK 34 下 JVM 测试通过；避免 Windows wrapper 丢失失败退出码 |
| Web | `npm run build` | 使用仓库 `.tools` 的 Node 22.18.0/npm 10.x 构建通过 |

## 固定工具链

- Python：优先 `PDD_PYTHON`，其次首个包含项目依赖的 `.venv\Scripts\python.exe`、`.venv-t001\Scripts\python.exe`；必须是 3.10.x。
- Node：` .tools\node-v22.18.0-win-x64`，版本为 Node 22.18.0/npm 10.9.3。
- JDK：脚本优先 `JAVA_HOME`，其次 `.tools\jdk-17.0.20+8`。若缺失，执行：

  ```powershell
  .\scripts\bootstrap-jdk17.ps1
  ```

  该脚本下载固定 Temurin 17.0.20+8 归档，并校验 SHA-256
  `418497BE5CF585BDD2203D6486A565D66D3F5E992D5630D45104CB873FAB8122`。
- Android SDK：优先 `ANDROID_SDK_ROOT`/`ANDROID_HOME`，其次
  `android_collector/local.properties` 的 `sdk.dir`。必须包含 Platform 34 和
  Build Tools 34.0.0。

## Oracle 真实测试

Oracle 不是可选的“HTTP 200 smoke”：只有实际运行全部 8 项并通过，Oracle 套件
才为 `PASS`。连接参数从当前进程环境读取且测试入口不打印 DSN、用户名或密码。

```powershell
$env:APP_ENV = 'test'
$env:T003_ORACLE_TEST_ENABLED = '1'
$env:T003_ORACLE_DSN = '127.0.0.1:11521/FREEPDB1'
$env:T003_ORACLE_USER = 'T003_TEST'
$env:T003_ORACLE_PASSWORD = '<test-only password>'
.\scripts\test-baseline.ps1 -Suite oracle -Strict
```

隔离 Schema 的启动、初始化、探测和清理命令见
[`T003 Oracle 测试环境`](T003-oracle-test-env.md)。未提供这些变量时，入口返回
`BLOCKED`，严格模式返回 `2`；不会回退到业务 Oracle 或 mock。

## 本机调查结果（T006 实施时）

- Python 3.10.6 与项目 `.venv` 可用。
- 仓库已有 Node 22.18.0/npm 10.9.3。
- 原环境未发现可用 `java`；现由固定 Temurin JDK 17.0.20+8 bootstrap 提供。
- `android_collector/local.properties` 指向的 SDK 已包含所需 SDK 组件。
- 未发现 `docker.exe` 或可启用的 T003 Oracle 环境；真实 Oracle 套件保持
  `BLOCKED`，直到按隔离环境文档启动并注入测试专用变量。Phase 1 最终验收已使用专用 Oracle 19c Schema 注入这些变量。

## Phase 1 当前验收结果

- Python：60 tests，`PASS`，exit `0`。
- Android JVM：36 tests，`PASS`，exit `0`。
- Web：1665 modules transformed，`PASS`，exit `0`。
- Oracle：8 tests，`PASS`，exit `0`；覆盖多连接竞态、回滚、幂等、业务去重、finish manifest 与最小成功闭环。

最终统一严格入口：`SUMMARY PASS=4 FAIL=0 BLOCKED=0 STRICT=True`，exit `0`。
