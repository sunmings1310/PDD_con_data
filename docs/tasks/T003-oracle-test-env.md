# T003 独立 Oracle 真实事务测试环境方案

> 范围：只建立 T003 的独立 Oracle 测试环境与可重复执行流程；本方案不安装软件、不启动数据库、不修改 T003 业务逻辑或业务代码。
>
> 目标测试：`tests/test_task_state_r2_oracle.py` 中 8 项真实 Oracle 多连接/多事务测试。

## 1. 推荐本地部署方式

推荐使用 **Docker Desktop（或兼容的 Podman）+ Oracle 官方 Database Free Lite 容器**，并在默认 PDB 内创建专用 Schema：

- 容器：`t003-oracle`，只服务 T003 测试，不与生产、预生产或业务开发数据库复用。
- 镜像：`container-registry.oracle.com/database/free:latest-lite`；首次拉取后记录 `RepoDigest`，后续固定到同一 digest，避免标签漂移。
- CDB/PDB：镜像默认 `FREE/FREEPDB1`；应用与测试只连接 `FREEPDB1`。
- 端口：仅绑定 `127.0.0.1:11521 -> 1521`，不向局域网开放，也避免与常见本机 1521 冲突。
- 数据卷：`t003-oradata`，只保存该测试实例数据；需要绝对干净基线时删除容器和该卷后重建。
- Schema：`T003_TEST`，对象 owner 与测试连接用户相同；管理员账号只负责首次建 Schema。
- 运行模式：初始化、迁移和测试进程都显式设置 `APP_ENV=test`。

Oracle 官方文档说明了 Free Lite 镜像、`ORACLE_PWD`、数据卷、`FREEPDB1` 和就绪标志 `DATABASE IS READY TO USE!`：

- [Oracle：Run Oracle AI Database Locally](https://docs.oracle.com/en/database/oracle/agent-memory/26.4/agmea/run-locally.html)
- [Oracle：Get Started with Oracle Database Free](https://docs.oracle.com/en/learn/ol-db-free/)

不推荐直接在 Windows 安装 Oracle 服务，因为清理成本更高，且容易与既有监听、服务和数据目录混用。若组织策略禁止容器，可改用专用 Oracle 19c/23ai 测试虚拟机，但仍须采用独立 PDB、独立 Schema 和本方案的环境变量边界。

### 1.1 计划中的容器命令（本任务不执行）

密码值只在执行会话中注入，不写入脚本或仓库：

```powershell
$env:T003_ORACLE_ADMIN_PASSWORD = '<TEST_ONLY_ADMIN_PASSWORD>'
$OracleImage = 'container-registry.oracle.com/database/free:latest-lite'

docker pull $OracleImage
docker image inspect $OracleImage --format '{{index .RepoDigests 0}}'
docker volume create t003-oradata
docker run -d --name t003-oracle `
  -p 127.0.0.1:11521:1521 `
  -e ORACLE_PWD="$env:T003_ORACLE_ADMIN_PASSWORD" `
  -v t003-oradata:/opt/oracle/oradata `
  $OracleImage

docker logs -f t003-oracle
# 仅当日志出现 DATABASE IS READY TO USE! 后继续。
```

首次验证通过后，将 `docker image inspect` 输出的 `name@sha256:...` 记录在本机运行说明或 CI Variable 中，后续以该 digest 启动。不得提交管理员密码、Schema 密码或包含密码的输出。

## 2. Oracle 版本要求

| 项目 | 要求 |
|---|---|
| 项目测试基线 | Oracle Database 19c 或更高 |
| 推荐本地版本 | Oracle Database Free 23ai Lite，固定镜像 digest |
| PDB | 可读写，状态为 `READ WRITE`；推荐默认 `FREEPDB1` |
| 字符集 | `AL32UTF8` |
| Python 驱动 | 仓库锁定的 `oracledb==2.5.1`，默认 Thin 模式 |
| Oracle 客户端 | Thin 模式无需 Instant Client；Schema 管理使用容器自带 SQL*Plus |

测试会使用序列、CLOB、`SYSTIMESTAMP`、`SELECT ... FOR UPDATE`、唯一约束竞争和多连接事务。虽然 python-oracledb Thin 可连接更早版本，本方案把 19c 设为测试下限，避免把老版本差异引入 T003 验收。版本兼容说明见 [python-oracledb 官方文档](https://python-oracledb.readthedocs.io/en/stable/user_guide/installation.html#supported-oracle-database-versions)。

## 3. 测试 Schema 设计

```text
Oracle Free container: t003-oracle
└─ PDB: FREEPDB1
   └─ Schema owner: T003_TEST
      ├─ 核心对象: SJZQ_DEVICE / TASK / TASK_ITEM / TASK_LOG
      ├─ 幂等对象: SJZQ_PROGRESS_RECEIPT
      ├─ 商品对象: SJZQ_PRODUCT / SJZQ_PRODUCT_IMAGE
      ├─ 操作日志: SJZQ_OP_LOG
      ├─ RBAC 对象: SJZQ_USER / ROLE / ROLE_PERM / SYS_CONFIG
      └─ 对应 SJZQ_SEQ_* 序列、索引和兼容视图
```

设计约束：

1. `T003_TEST` 同时是对象 owner 和测试连接用户，避免跨 Schema grant 干扰事务语义。
2. Schema 只存在于专用 `FREEPDB1`，不创建 database link，不授予其他业务 Schema 权限。
3. 测试池最多 8 个连接；每个并发 worker 获取独立 connection 和 transaction。
4. 测试数据用 `T003R2-<uuid>` 或 `receipt-<uuid>` 标识，便于重复执行和中断清理。
5. 数据库管理员、测试 Schema owner、应用测试管理员与业务开发账号完全分离。

## 4. 测试账号权限

由专用测试数据库管理员连接 `FREEPDB1` 后创建用户。真实密码来自当前进程环境变量；SQL 中的值只是占位符：

```sql
CREATE USER T003_TEST IDENTIFIED BY "<T003_ORACLE_PASSWORD>"
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  QUOTA 256M ON USERS;

GRANT CREATE SESSION TO T003_TEST;
GRANT CREATE TABLE TO T003_TEST;
GRANT CREATE SEQUENCE TO T003_TEST;
GRANT CREATE VIEW TO T003_TEST;
GRANT SELECT ON V_$VERSION TO T003_TEST;
```

`V_$VERSION` 权限供现有 `server.init_schema` 读取数据库版本。对象 owner 可管理自身表、索引、序列和视图，不需要跨 Schema 权限。

禁止授予：`DBA`、`SYSDBA`、`CREATE ANY TABLE`、`DROP ANY TABLE`、`SELECT ANY TABLE`，以及任何生产/开发业务 Schema 的对象权限。

实际执行时可从环境变量生成一次性 SQL，经 stdin 送入 SQL*Plus；真实密码不进入文件或命令历史：

```powershell
$env:T003_ORACLE_ADMIN_PASSWORD = '<TEST_ONLY_ADMIN_PASSWORD>'
$env:T003_ORACLE_PASSWORD = '<TEST_ONLY_SCHEMA_PASSWORD>'

$sql = @"
WHENEVER SQLERROR EXIT SQL.SQLCODE
CONNECT SYSTEM/"$env:T003_ORACLE_ADMIN_PASSWORD"@FREEPDB1
CREATE USER T003_TEST IDENTIFIED BY "$env:T003_ORACLE_PASSWORD"
  DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP QUOTA 256M ON USERS;
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE VIEW TO T003_TEST;
GRANT SELECT ON V_`$VERSION TO T003_TEST;
EXIT
"@
$sql | docker exec -i t003-oracle sqlplus -L /nolog
```

## 5. 环境变量

### 5.1 强制变量

```powershell
$env:APP_ENV = 'test'

# Schema 初始化/迁移使用。
$env:ORACLE_HOST = '127.0.0.1'
$env:ORACLE_PORT = '11521'
$env:ORACLE_SERVICE = 'FREEPDB1'
$env:ORACLE_USER = 'T003_TEST'
$env:T003_ORACLE_PASSWORD = '<TEST_ONLY_SCHEMA_PASSWORD>'
$env:ORACLE_PASSWORD = $env:T003_ORACLE_PASSWORD

# 8 项真实事务测试使用。
$env:T003_ORACLE_TEST_ENABLED = '1'
$env:T003_ORACLE_DSN = '127.0.0.1:11521/FREEPDB1'
$env:T003_ORACLE_USER = 'T003_TEST'

# 初始化脚本使用的测试专用值。
$env:JWT_SECRET = '<TEST_ONLY_JWT_SECRET_AT_LEAST_32_CHARS>'
$env:INITIAL_ADMIN_USERNAME = 't003_test_admin'
$env:INITIAL_ADMIN_PASSWORD = '<TEST_ONLY_APP_ADMIN_PASSWORD_12_PLUS_CHARS>'
```

| 变量 | 用途 | 约束 |
|---|---|---|
| `APP_ENV` | 应用模式 | 必须严格为 `test` |
| `ORACLE_HOST/PORT/SERVICE/USER/PASSWORD` | Schema 初始化与迁移 | 必须指向本机专用 `FREEPDB1/T003_TEST` |
| `T003_ORACLE_TEST_ENABLED` | 真实测试保护开关 | 必须严格为 `1`；缺失时测试保持 `BLOCKED_BY_ENVIRONMENT` |
| `T003_ORACLE_DSN/USER/PASSWORD` | 8 项测试连接池 | 必须与专用 Schema 一致 |
| `T003_ORACLE_ADMIN_PASSWORD` | 容器管理员/首次建 Schema | 不传给测试进程 |
| `JWT_SECRET`、`INITIAL_ADMIN_*` | RBAC 初始化 | 只能使用测试专用值 |

所有 Oracle 连接信息均通过环境变量注入。不得把真实值写入 `server/.env`、源码、测试文件、Markdown、Git tracked 文件或日志。

执行结束后清除当前 PowerShell 会话变量：

```powershell
'T003_ORACLE_ADMIN_PASSWORD','T003_ORACLE_PASSWORD','T003_ORACLE_TEST_ENABLED',
'T003_ORACLE_DSN','T003_ORACLE_USER','ORACLE_HOST','ORACLE_PORT','ORACLE_SERVICE',
'ORACLE_USER','ORACLE_PASSWORD','JWT_SECRET','INITIAL_ADMIN_USERNAME',
'INITIAL_ADMIN_PASSWORD','APP_ENV' |
  ForEach-Object { Remove-Item "Env:$_" -ErrorAction SilentlyContinue }
```

## 6. Schema 初始化步骤

前置条件：容器日志已出现 `DATABASE IS READY TO USE!`，`T003_TEST` 已创建，第 5 节变量已注入当前 PowerShell 会话。

从仓库根目录按顺序执行：

```powershell
if ($env:APP_ENV -ne 'test') { throw 'APP_ENV must be test' }
if ($env:T003_ORACLE_DSN -ne '127.0.0.1:11521/FREEPDB1') {
  throw 'Unexpected T003 Oracle DSN'
}

.\.venv-t001\Scripts\python.exe -m server.init_schema --drop
.\.venv-t001\Scripts\python.exe -m server.init_rbac_schema
.\.venv-t001\Scripts\python.exe -c "from server.migrate import ensure_schema_patches; ensure_schema_patches()"
```

`server.init_schema --drop` 重建核心表和序列，但不清空所有 RBAC/操作日志对象；“完全从零”的权威方式是删除专用容器和 `t003-oradata` 卷后重建。日常重复执行使用第 9 节清理。

初始化后校验连接、PDB、字符集和关键对象：

```powershell
$check = @"
import os, oracledb
conn = oracledb.connect(user=os.environ['T003_ORACLE_USER'], password=os.environ['T003_ORACLE_PASSWORD'], dsn=os.environ['T003_ORACLE_DSN'])
cur = conn.cursor()
cur.execute("select sys_context('USERENV','CON_NAME') from dual")
assert cur.fetchone()[0] == 'FREEPDB1'
cur.execute("select value from nls_database_parameters where parameter='NLS_CHARACTERSET'")
assert cur.fetchone()[0] == 'AL32UTF8'
for name in ('SJZQ_DEVICE','SJZQ_TASK','SJZQ_TASK_ITEM','SJZQ_TASK_LOG','SJZQ_PROGRESS_RECEIPT','SJZQ_PRODUCT','SJZQ_PRODUCT_IMAGE','SJZQ_OP_LOG'):
    cur.execute("select count(*) from user_objects where object_name=:n", {'n': name})
    assert cur.fetchone()[0] > 0, name
print('T003_ORACLE_SCHEMA_READY')
conn.close()
"@
$check | .\.venv-t001\Scripts\python.exe -
```

验收输出必须为 `T003_ORACLE_SCHEMA_READY`，退出状态为 0。

## 7. 测试数据初始化

8 项测试自行 seed，不需要人工插入业务数据：

- Device：`DEVICE_KEY/DEVICE_NAME = T003R2-<uuid>`。
- Task：使用 `SJZQ_SEQ_TASK`，按场景初始化为 `pending` 或 `running`。
- Task Item：使用 `SJZQ_SEQ_TASK_ITEM`，初始为 `pending`。
- Receipt：使用 `receipt-<uuid>`，由两个真实事务竞争同一主键。
- Product/Image：走真实产品上传数据库路径，在 item 状态迁移失败时验证整笔事务回滚。

每次执行前确认没有上次中断残留：

```sql
SELECT 'DEVICE' object_type, COUNT(*) count_value
  FROM SJZQ_DEVICE WHERE DEVICE_KEY LIKE 'T003R2-%'
UNION ALL
SELECT 'TASK', COUNT(*) FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%'
UNION ALL
SELECT 'OP_LOG', COUNT(*) FROM SJZQ_OP_LOG WHERE USERNAME = 't003-r2';
```

三个计数都应为 0；非 0 时先执行第 9 节清理。

## 8. 八项真实事务测试执行方式

共同前置：`APP_ENV=test`、保护开关为 1、Schema 校验成功，输出不得出现 `skipped` 或 `BLOCKED_BY_ENVIRONMENT`。

### 8.1 同一设备并发 Pull

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_concurrent_pull_same_device_claims_at_most_one_task
```

两个线程、两个独立连接同时 Pull 同一设备；验收为只有一个请求取得任务，设备 `CURRENT_TASK_ID` 与唯一 `running` 任务一致。

### 8.2 Complete 与 Cancel 并发

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_complete_cancel_race_twenty_times_without_deadlock
```

每轮两个独立事务并发 Complete/Cancel，共 20 轮；15 秒内完成、无死锁，Task/Item 进入允许终态，设备占用被清除。

### 8.3 重复 receipt 唯一约束竞争

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_duplicate_receipt_two_transactions_increment_once
```

两个事务竞争同一 `PROGRESS_ID`；一个 claim 成功、一个失败，Receipt 仅一行，`SUCCESS_COUNT` 仅增加一次。

### 8.4 Product Upload 失败后的真实事务回滚

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_product_upload_api_failure_rolls_back_real_writes
```

产品写入后强制 item 状态迁移失败；API 返回失败，`SJZQ_PRODUCT` 无 marker 记录，Item 保持 `pending`，Task 成功/失败计数均为 0。

### 8.5 Phase 1 相同 key 并发商品上传

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_phase1_concurrent_same_product_receipt_persists_once
```

两个连接并发提交相同 product idempotency key；验收为两个请求得到同一 `product_id`，商品、receipt、成功计数均只写一次。

### 8.6 Phase 1 不同 key 的任务内业务去重

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_phase1_new_keys_same_task_item_are_business_deduplicated
```

同一 Task、平台和 item_id 使用两个请求 key；验收为两个 receipt 指向同一业务商品，`SUCCESS_COUNT` 只增加一次。

### 8.7 Phase 1 finish manifest 门禁

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_phase1_finish_manifest_requires_all_receipts
```

期望商品 receipt 尚未确认时提交 Complete；验收为 `FINISH_INCOMPLETE` 且任务保持 `running`。

### 8.8 Phase 1 最小成功闭环

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle.OracleConcurrencyTest.test_phase1_minimum_success_loop_is_server_confirmed
```

真实执行 Task 创建、审核、Agent pull、严格商品上传、服务端持久化确认和 finish confirmation；验收为商品及两个 receipt 持久化、任务 `succeeded`、设备占用释放。

### 8.9 一次执行全部八项

```powershell
.\.venv-t001\Scripts\python.exe -m unittest -v tests.test_task_state_r2_oracle
```

验收标准：

- 输出包含 `Ran 8 tests` 和 `OK`，退出状态为 0。
- 不包含 `FAILED`、`ERROR`、`skipped`、`BLOCKED_BY_ENVIRONMENT`。
- Oracle 会话来自明确批准的专用可写测试 Schema，而不是生产或共享业务 Schema。

真实测试若暴露 Bug，先保存失败用例、Oracle 错误码、最终行状态和最小复现，再另起修复任务。本阶段不修改 T003 业务逻辑。

## 9. 测试清理方式

### 9.1 正常清理

现有测试 `tearDown` 会删除 Task Log、Receipt、Product Image、Product、Task Item、Task 和 Device。Complete/Cancel 测试还可能留下 `USERNAME='t003-r2'` 的操作日志，因此每轮测试套件结束后补充执行第 9.2 节 SQL。

### 9.2 中断或残留数据清理

以 `T003_TEST` 执行，先删子表，再删父表：

```sql
DELETE FROM SJZQ_OP_LOG WHERE USERNAME = 't003-r2';

DELETE FROM SJZQ_TASK_LOG
 WHERE TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%');

DELETE FROM SJZQ_PROGRESS_RECEIPT
 WHERE TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%');

DELETE FROM SJZQ_PRODUCT_IMAGE
 WHERE PRODUCT_ID IN (
   SELECT PRODUCT_ID FROM SJZQ_PRODUCT
    WHERE TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%')
 );

DELETE FROM SJZQ_PRODUCT
 WHERE TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%');

DELETE FROM SJZQ_TASK_ITEM
 WHERE TASK_ID IN (SELECT TASK_ID FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%');

DELETE FROM SJZQ_TASK WHERE TASK_NAME LIKE 'T003R2-%';
DELETE FROM SJZQ_DEVICE WHERE DEVICE_KEY LIKE 'T003R2-%';
COMMIT;
```

清理后重新执行第 7 节计数查询，全部必须为 0。

### 9.3 完全重置

当迁移失败、对象结构不可信或需要证明干净基线时，删除 **专用** 容器与卷，再按第 1、4、6 节重建：

```powershell
docker stop t003-oracle
docker rm t003-oracle
docker volume rm t003-oradata
```

这些命令只适用于本方案命名的 T003 专用容器和卷，不触碰其他数据库或 volume。

## 10. 建立顺序与停止点

1. 安装 Docker Desktop/Podman，拉取 Oracle 官方 Free Lite 镜像并记录 digest。
2. 创建 `t003-oracle` 与 `t003-oradata`，等待数据库就绪。
3. 验证 `FREEPDB1` 为 `READ WRITE`，创建最小权限 `T003_TEST`。
4. 设置 `APP_ENV=test` 及两组 Oracle 环境变量。
5. 执行 Schema 初始化、RBAC 初始化、迁移和对象校验。
6. 确认残留计数为 0，依次运行 8 项测试，再运行完整 8 项套件。
7. 清理残留并复查计数为 0，清除 PowerShell 敏感环境变量。

环境准备完成后由统一严格入口执行 8 项事务测试；测试过程只连接命名的隔离 Schema。
