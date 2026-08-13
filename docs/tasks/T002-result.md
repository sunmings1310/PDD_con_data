# T002：外置秘密并增加配置启动校验——执行结果

> 日期：2026-08-13  
> 对应：BL-003  
> Status: DONE

## 1. 修改文件

- `server/config.py`：建立 environment/Oracle/JWT 配置模型、fail-fast 与脱敏错误。
- `server/auth_util.py`：JWT algorithm/expire 改由已校验配置提供。
- `server/db.py`、`server/init_schema.py`、`server/init_rbac_schema.py`：仅在连接边界解包 Oracle `SecretStr`。
- `server/.env.example`：替换为无效占位符和完整变量清单。
- `.gitignore`、`android_collector/.gitignore`：忽略本机 dotenv、credential 和签名材料。
- `android_collector/settings.gradle.kts`：release 任务在插件解析前执行签名配置完整性校验。
- `android_collector/app/build.gradle.kts`：签名字段改为 Gradle property/环境变量外部注入。
- `tests/test_server_config.py`：新增 11 项配置自动化测试。
- `README.md`、`android_collector/README.md`、`docs/development-environment.md`：更新配置、签名和迁移说明。
- `docs/backlog.md`：BL-003 更新为 DONE，并保留 BL-010 环境阻塞。
- `docs/tasks/T002-result.md`：本结果。

未修改采集、解析、任务状态机、API 业务语义、数据库 schema、CI/CD 或 Git 历史。

## 2. Secret 处理结果

### Oracle

- 修改前：host/port/service/user/password 均有源码可用默认值，示例与本机 dotenv 含相同具体配置。
- 修改后：连接关键字段全部必填；password 使用 `SecretStr`，仅在 Oracle 驱动调用处解包；来源为环境变量或 development 本机 `server/.env`。
- 迁移：部署前显式提供 `ORACLE_HOST`、`ORACLE_PORT`、`ORACLE_SERVICE`、`ORACLE_USER`、`ORACLE_PASSWORD`；当前凭据按已暴露处理并在外部系统轮换。

### JWT

- 修改前：secret 有固定源码默认值，algorithm/expire 为源码常量。
- 修改后：secret 必填且使用 `SecretStr`；algorithm 仅允许 `HS256`；expire 由配置提供并校验范围；production 拒绝弱值、占位符和已暴露旧值。
- 迁移：提供新的 `JWT_SECRET`，可显式提供 `JWT_ALGORITHM`、`JWT_EXPIRE_SEC`。轮换后，使用旧 Secret 签发的现有 Token 全部失效，用户必须重新登录。

### Android signing

- 修改前：keystore 相对路径、store/key password 和 alias 写在 Gradle 源码。
- 修改后：release 从 Gradle property 或环境变量读取 keystore 路径、store password、alias、key password；源码和示例无实际签名值。缺字段或 keystore 不存在时 release 在配置阶段失败；debug 不读取为必填。
- 迁移：安全备份现有 keystore，以外部 Secret 注入四项配置。只轮换已暴露签名口令；签名证书/private key 是否更换保持待确认，未确认发布历史前不得更换。

## 3. 配置校验

- `APP_ENV`：仅允许 `development`、`test`、`production`，默认 development。
- Oracle host/service/user：strip 后必须非空。
- Oracle password：必填、非空、错误及对象 repr 不回显值。
- Oracle port：整数且范围 1～65535。
- HTTP port：整数且范围 1～65535；heartbeat 必须为正整数。
- JWT secret：必填、非空；production 至少 32 字符、至少三类字符，拒绝占位符和已暴露旧值。
- JWT algorithm：当前允许列表仅 `HS256`，保持既有兼容语义。
- JWT expire：60～604800 秒。
- 配置异常：导入/启动时 fail fast，只输出字段和原因，不包含输入 Secret。
- 来源优先级：环境变量 > dotenv；test 可传 `_env_file=None` 完全隔离本机 `.env`。
- Android release：四个签名字段必填且 keystore 文件必须存在；只对含 release 的任务生效。

## 4. 自动化测试结果

| 命令/测试 | 状态 | 摘要 |
|---|---|---|
| `.venv-t001\Scripts\python.exe -m unittest discover -s tests -v` | PASS | 11/11；覆盖 Oracle 缺失、port 类型/范围、JWT 缺失/弱值/算法/expire、合法配置、test 纯环境注入、env 覆盖 dotenv、异常和 repr 脱敏 |
| Python `compileall server tests` | PASS | 退出 0 |
| Android `assembleRelease`（不提供 signing） | PASS（负向） | 退出 1；明确列出四个缺失字段，不输出值 |
| 受控源码 Secret 模式扫描 | PASS | 未发现旧 Oracle host、旧 JWT secret 或旧 Android signing 口令；Gradle 仅保留变量赋值逻辑 |

## 5. 回归结果

### Python：PASS / BLOCKED_BY_ENVIRONMENT

- 核心导入：PASS，输出 `PYTHON_IMPORTS_OK`；`pip check` 输出 `No broken requirements found.`。
- 配置测试：PASS，11 项全部通过。
- 服务启动：使用纯 test 环境变量启动到 Uvicorn `Waiting for application startup`；随后连接 `127.0.0.1:1` 返回 `DPY-6005`/connection refused。配置加载和启动边界已通过；由于当前无隔离 Oracle，完整 lifespan/readiness 为 `BLOCKED_BY_ENVIRONMENT`，未标为 PASS。

### Web build：PASS

命令：Node 22.18 工具链下 `cd web; npm run build`。结果：1665 modules transformed，`built in 686ms`，退出 0。既有 500 kB chunk 告警未处理。

### Android assembleDebug：BLOCKED_BY_ENVIRONMENT（修改后曾成功）

修改 signing 后首次命令：JDK 17、SDK 34、Gradle 8.4 下
`gradle.bat assembleDebug --no-daemon --console=plain --rerun-tasks`，退出 0；未提供
任何 release signing 配置，证明 debug 不依赖 release Secret。随后最终复跑时，
Gradle 插件仓库不可达/缓存状态异常，出现 `com.android.application:8.1.4`
无法解析；改用 T001 缓存的 Wrapper 运行又超时，遗留进程已停止。因此最终环境状态
如实记为 `BLOCKED_BY_ENVIRONMENT`，保留首次修改后成功记录，不伪造最终 PASS。

## 6. 部署迁移要求

升级前必须准备：

```text
APP_ENV=development|test|production
ORACLE_HOST
ORACLE_PORT
ORACLE_SERVICE
ORACLE_USER
ORACLE_PASSWORD
JWT_SECRET
JWT_ALGORITHM=HS256
JWT_EXPIRE_SEC=43200
```

可选普通配置：`HOST`、`PORT`、`PUBLIC_BASE_URL`、`HEARTBEAT_TIMEOUT_SEC`、`IMAGE_DIR`。development 可用被忽略的 `server/.env`；test/production 推荐由部署环境完整注入。占位符不可直接启动 production。

Android release 另需通过 `-P` 或环境变量提供 store file、store password、key alias、key password；不得写入仓库、公共 Gradle properties 或文档。先验证同一既有证书的指纹，再发布升级 APK。

## 7. Secret Rotation 清单

| 项目 | 判定 | 说明 |
|---|---|---|
| Oracle password | **必须轮换** | 当前凭据视为已暴露；本任务只移除代码来源，不修改外部数据库密码 |
| JWT secret | **必须轮换** | 当前 Secret 视为已暴露；轮换后现有 Token 全部失效 |
| Android signing store/key password | **必须轮换** | 明文曾在 Gradle；在外部 keystore 管理流程中轮换 |
| Android signing key / keystore | **待确认** | 发布历史和证书泄露状态 UNKNOWN；擅自换 key 会破坏 APK 升级兼容性 |

## 8. 遗留问题

1. 缺少隔离测试 Oracle，完整 FastAPI lifespan/readiness 为 `BLOCKED_BY_ENVIRONMENT`；继续由 BL-010 处理。
2. 现有部署实际依赖的旧配置来源为 UNKNOWN，升级前必须逐实例盘点。
3. Secret 是否进入 Git 历史保持 UNKNOWN；本任务未推断、扫描或重写 Git 历史。
4. Android 现有发布证书、keystore 保管位置和 APK 签名连续性为 UNKNOWN，换 key 决策待发布历史确认。
5. 外部 Oracle、JWT、Android signing 口令轮换仍需部署/凭据管理员实际执行。

## 9. T002 完成状态

**DONE**。

依据：Oracle/JWT/Android release signing 可用源码秘密均已移除；配置 fail-fast、环境边界、test 纯环境注入、优先级和脱敏测试通过；release 缺签名配置明确失败；Python 核心导入、Web production build 均实际通过，Android debug 在本次 signing 修改后曾退出 0，最终复跑受 Gradle 插件获取/缓存环境阻塞。完整 Oracle lifespan 与最终 Android 复跑均按要求记录为 `BLOCKED_BY_ENVIRONMENT`；两者不是配置实现失败，且 Android 已有修改后成功证据，因此 T002 配置基线判定 DONE。
