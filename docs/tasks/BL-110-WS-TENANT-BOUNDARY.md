# BL-110-WS-TENANT-BOUNDARY：实时日志 WebSocket 租户与调度边界

- **Task ID**：BL-110-WS-TENANT-BOUNDARY
- **Title**：实时日志 WebSocket 握手认证、租户/资源分区与可靠调度
- **Status**：PR #5 / DRAFT / FIXED-HEAD GATES PENDING
- **Approved base**：`main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- **Current PR base**：`main@b3a7e2c493f44f4cb0bde7645d2c79340d019d65`
- **Branch / worktree**：`codex/bl-110-ws-tenant-boundary` / `D:\work\PDD_con_data_ws_tenant`

## Goal

关闭 `/ws/realtime` 的未认证全局广播 P0：由服务端依据登录身份和目标 Device/Task 的 Oracle 归属确定 Enterprise/Workspace scope，按租户和资源隔离订阅与投递，并把同步 handler 到 FastAPI app event loop 的调度变为可靠、可测试、失败可观察。

## Context

当前所有实时日志连接进入同一全局集合，握手没有认证、权限、membership、设备撤销或资源归属校验；Task 日志不带服务端 scope；`notify_sync()` 依赖线程本地 event loop 并吞掉异常。Product Owner 已批准本 P0 为 Web 队列第 1 项，后续任务必须等待本项 merge 后再从 main 开始。

## Scope

### Allowed

- `/ws/realtime` 握手认证与 `device:view`；
- 从服务端 JWT identity + Oracle Device/Task ownership 推导 scope；
- Enterprise/Workspace membership、Workspace membership、用户/设备撤销与资源错配门禁；
- Hub 按 Enterprise/Workspace/Device 资源分区；
- Task 日志事件的服务端权威 scope 与 Task/Device 一致性；
- FastAPI lifespan 绑定 app event loop，线程安全调度与失败计数/日志；
- Web `DeviceLive` 携带 token 与 device resource id，但不提交或决定 tenant scope；
- 离线单元/契约测试、隔离 Oracle 资源归属测试、Web build 和全量回归；
- 本 Task、backlog、roadmap、CURRENT_STATE 和验证制品随状态更新。

### Forbidden

- 修改 Schema/migration、业务数据、Task/Product 成功语义；
- 扩大到投屏、OTA、全站 WebSocket broker、多实例或 CORS/密码哈希等 BL-110 其他范围；
- 信任客户端提交的 Enterprise/Workspace；
- 启动后续 Web 队列项、Generic SKU、SKU Schema/P1 数据模型、Phase 6B；
- merge、release；PR #5 的证据刷新已由 Product Owner 批准。

## Non-goals

- 不建设跨实例消息 broker；保持当前单实例实时通知约束；
- 不以 WebSocket 代替 Oracle 权威状态或 8 秒 HTTP 恢复轮询；
- 不修改投屏 publisher/viewer 协议；
- 不处理 WEB-AUDIT-001 的其他 P1/P2 finding。

## Dependencies

- `main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- 已 Accepted 的 Enterprise/Workspace membership、设备 revoke 和 Task/Device tenant columns
- 现有 JWT 与 `device:view` permission
- 隔离、可写、可清理 Oracle 测试 Schema

## Affected Modules

- `server/ws_hub.py`
- `server/main.py`
- `server/routers/tasks.py`
- `web/src/views/devices/DeviceLive.vue`
- `tests/test_realtime_ws_tenant.py`
- `tests/test_realtime_ws_tenant_oracle.py`
- `docs/backlog.md`、`docs/roadmap.md`、本 Task、验收状态与验证制品

## ADR

不新增长期多实例 ADR；本 Task 只落实现有 Product tenant 不变量与 BL-110 最小边界。多实例方案仍归 BL-203。

## Acceptance Criteria

- [x] 缺 token、无效 token、disabled user 均以 WS policy violation 拒绝；
- [x] 缺 `device:view`、非 Enterprise/Workspace member、Workspace membership 不匹配均拒绝；
- [x] revoked/missing Device、跨租户 Device/Task、Task/Device 资源错配均拒绝或不投递；
- [x] 客户端不提交 Enterprise/Workspace，scope 只由服务端 identity 与资源归属确定；
- [x] 同 Enterprise/Workspace 且同 Device 的已授权连接收到正确 Task 日志；其他租户、Workspace 或 Device 不收到；
- [x] 握手后 token expiry、用户/Membership/权限或 Device 撤销会在下一次投递前重验，1008 断开且不投递；
- [x] app loop 绑定、线程安全调度、未绑定/关闭 loop、投递异常都有确定结果、日志和计数；不吞异常；
- [x] scope mismatch 在 progress receipt claim 前拒绝，不消费幂等 ID；Oracle commit 后才调度通知；
- [x] HTTP 轮询继续作为恢复路径，WS 不成为业务完成或状态真相；
- [x] targeted、Python full、Web build、适用 Oracle Gate、Independent Review 全部完成；
- [ ] 从 `main@b3a7e2c` 更新并固定 clean PR Head；重跑本地 Oracle strict、提交 manifest、Hosted evidence gate 通过后停止。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted | `python -m unittest -v tests.test_realtime_ws_tenant tests.test_task_state_r1` | dummy config；fake WebSocket/DB/loop | 认证、权限、跨租户、撤销、资源、分区、receipt 与调度矩阵通过 | `Ran 32 tests ... OK` | 0 | PASS |
| Oracle targeted | `python -m unittest -v tests.test_realtime_ws_tenant_oracle` | 批准的隔离 Oracle；opt-in env | 真实 membership/permission/tenant/workspace/device/task 矩阵通过并 rollback | `Ran 1 test ... OK` | 0 | PASS |
| Module | `python scripts/run_python_unit_tests.py` | Python 3.10.6；Oracle opt-in off | 全量 offline Python 通过 | `Ran 213 tests ... OK (skipped=24)` | 0 | PASS |
| Web | `npm ci`; `npm run build` | Node 22.18.0/npm 10.9.3 | Web production build 通过 | `1673 modules transformed`；built successfully | 0 | PASS |
| Full regression | `scripts/test-baseline.ps1 -Strict` | 固定 Python/JDK/Android/Node；批准的 Phase 1～6A Oracle env | 全量适用门禁通过 | `PASS=4 FAIL=0 BLOCKED=0 STRICT=True` | 0 | PASS |
| Diff | `git diff --check`、验证/rollback artifact | 完整 Task delta | 无 whitespace error，可恢复 | 无输出；rollback 恢复 baseline probe | 0 | PASS |

## Oracle Gate

- Required：Yes
- Reason：权限、Membership、撤销和 Task/Device tenant ownership 必须在真实 Oracle 方言/约束下验证。
- Environment：隔离、可写、可清理测试 Schema；测试记录均在事务中并 rollback。
- Command / result / exit：`python -m unittest -v tests.test_realtime_ws_tenant_oracle`；`Ran 1 test in 3.972s / OK`；exit 0。数据在测试事务 `finally` rollback。

## Real-device Gate

- Required：No
- Device/scenario：本 Task 不改变 Android 或真实 App 行为；WebSocket browser/ASGI 与 Oracle contract 可离线验证。
- Command or steps / result：SKIPPED（差异不涉及真机）。

## Rollback

- Code rollback：按提交逆序 revert；恢复旧 `/ws/realtime` 客户端与 server 文件仅用于紧急代码回退，回退后 P0 重新开放，不能作为安全运行状态。
- Configuration rollback：无配置/secret 变更。
- Data recovery：测试事务 rollback；无业务数据迁移。
- Irreversible items：无。

## Human Decision Points

- PR、merge、release 需 Product Owner 明确批准；
- 若需要多实例 broker、token transport 产品方案变化或扩大到 cast/OTA，停止并拆分 Task；
- 若无法在现有 JWT/membership/device resource 模型内建立服务端权威 scope，停止升级。

## Stop Condition

Independent Review `ACCEPT` 已保持；从 `main@b3a7e2c` 更新后，在固定 PR Head 重新生成本地 Oracle strict manifest 并让 Hosted offline/evidence CI 通过，然后停止。不得 merge、release；不得启动队列第 2 项，因为其必须从本项 merge 后的 main 开始。

## Evidence

- Original evidence：`server/ws_hub.py` 未认证全局 client set；`DeviceLive.vue` 无 token/resource scope；Task progress event 无 tenant；`notify_sync` 吞异常。
- Derived artifacts：`docs/tasks/BL-110-WS-TENANT-BOUNDARY-verification/`（MODIFIED_FILE、DIFF_FILE、VERIFICATION、ROLLBACK）。
- Review findings：首轮 `CHANGES REQUIRED` 发现握手后撤销未重验（P0）、scope mismatch 可能先消费 progress receipt（P1）、Oracle 两条隔离轴不足（P2）；均在 `dc268b275411968c067cdacdcd9c00031198471b` 修复。独立 re-review：`ACCEPT`，无阻断 finding。
- Commit / PR：实现 Review Head `dc268b275411968c067cdacdcd9c00031198471b`；Draft PR [#5](https://github.com/sunmings1310/PDD_con_data/pull/5)；最终证据以远端 `codex/bl-110-ws-tenant-boundary` 固定 Head 与 PR body manifest 为准。
