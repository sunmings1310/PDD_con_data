# SKU-EVIDENCE-VALIDATION-001：真实 SKU 证据验证

- **Task ID**：SKU-EVIDENCE-VALIDATION-001
- **Title**：验证输入商品的真实 SKU_PANEL 证据链
- **Status**：PARTIAL / HUMAN_GATE BLOCKED（本地服务已恢复；本机 ADB 仍未枚举到已批准真机）
- **Approved base**：`main@f7d037cd612df09059dcea83189e63f99097042d`
- **Branch / worktree**：`codex/sku-evidence-validation-001` / `D:\work\PDD_con_data_sku_evidence_validation`
- **Approved input**：`C:\Users\Eden\Desktop\123.xlsx`，SHA-256 `bb5f02ca3d4995619f179ae1a58ccd889c0576bbb1b27af0c73d453f365cd557`

## Goal

只验证真实 SKU 证据是否足以支持后续独立 ADR/Schema 讨论。证据链必须从详情点击前开始，经过购买入口与 `SKU_PANEL`，记录动态维度、选项、实际组合、组合价格/可选状态/平台 SKU ID observation，随后退出面板。不得由 Excel 规格、标题、参数或主商品价格推断 SKU。

## Context

- Accepted main 只保留 `SKU_PANEL` Raw source 表达与 replay 能力；默认 PDD 路径明确不打开购买入口、不遍历组合。
- 历史未合并分支 `codex/sku-evidence-001` 曾观察 7 个样本，但最多确认二维；disabled、SKU media 与 direct platform SKU ID 均为 `NOT_OBSERVED`，且已证明 `available=false` 不能直接等价为无效组合。该历史证据只作约束，不替代本 Task 针对给定 Excel 的新证据。
- 输入工作表 `导入模板!A1:D6` 有 5 行，其中 4 行为国药准字、1 行为 `湘械注准` 医疗器械注册号；1 个名称以 `●` 开头。

## Scope

### Allowed

1. 保留原 Excel 不变，在本机隔离输入目录复制并核验 hash；
2. 离线运行当前 Excel parse、required-field validation、Task draft normalization/dedupe 与 empty-catalog match branch；
3. 从 5 行中经真实搜索选择确认存在多规格的最小样本，默认 1 个、最多 2 个；
4. 在已批准真机和现有受控登录会话中低频串行打开详情、点击购买/拼单入口、只读取 SKU 面板并退出；
5. 保存点击前后 Raw、hash、manifest、identity，生成脱敏 fixture/report；
6. 验证 Raw → Replay → DTO，记录 parser/quality versions 与 observation status；
7. 输出证据充分性和独立 ADR/Schema Review 建议。

### Forbidden

- 确认订单、提交订单、支付、加入购物车；
- 高频或全量组合遍历、后台长时间采集；
- 绕过验证码、风控、登录异常或平台限制；
- 回显或提交账号、cookie、token、设备标识、个人信息、未脱敏截图/网络包；
- 实施 Generic SKU runtime、P1 Schema/migration、历史回填/清洗或 Phase 6B；
- 把 `规格`、标题、参数或主商品价格直接变成 SKU 维度、组合、价格或 ID；
- 伪造 `platform_sku_id`、库存、图片、选项、组合或 availability。

## Offline Input Matrix

详见 [`SKU-EVIDENCE-VALIDATION-001-offline-matrix.md`](SKU-EVIDENCE-VALIDATION-001-offline-matrix.md)。当前结果：

- 5/5 行解析且必填字段完整；
- 4 个 drug approval、1 个 medical-device registration 均保留；
- `●` 在原始品名和 draft name 中保留，搜索词仅按现有 `_search_keyword` 规则去掉前导符号；
- duplicate=0、invalid=0、ready=5；
- 离线 empty-catalog branch 返回 `unmatched` 仅用于执行分支覆盖，不是实际资料库匹配结论；实际 catalog match 记为 `NOT_EXECUTED_OFFLINE_NO_TENANT_CATALOG`；
- 5 个 Excel 规格均只标记 `ProductAttribute candidate`，SKU dimension/combination inference=0。

## Real Evidence Design Matrix

| Stage | Required evidence | Current status |
|---|---|---|
| Search/identity | 输入行、搜索词、稳定 `platform_product_id`、详情链接 identity | PENDING_REAL_DEVICE |
| Before click | 详情页 Raw/hash/time、页面状态、主商品事实 | PENDING_REAL_DEVICE |
| Entry action | 购买/拼单入口标识、单次点击时间、guard | PENDING_REAL_DEVICE |
| Panel opened | `SKU_PANEL` Raw/hash/manifest、面板确实展示 | PENDING_REAL_DEVICE |
| Dimensions/options | 动态 dimension/option 文本、selected/disabled observation | PENDING_REAL_DEVICE |
| Combination | 只记录实际完成选择且页面确认的组合 | PENDING_REAL_DEVICE |
| Price/state | 组合级显示价格与可选状态；主商品价不得复制 | PENDING_REAL_DEVICE |
| Platform SKU ID | 平台直接提供则 `OBSERVED`；否则 `NOT_OBSERVED` | PENDING_REAL_DEVICE |
| Exit | 退出面板且 order/submit/payment guards 全为 false | PENDING_REAL_DEVICE |
| Replay/DTO | Raw → Replay → DTO identity/version/quality | DEFERRED_NO_REAL_DEVICE_RAW；本地服务已恢复 |

## Acceptance Criteria

- [x] 原 Excel 与隔离副本 SHA-256 一致，原文件未修改；
- [x] 5 行离线 parse/validate/dedupe 状态矩阵完成；
- [x] 混合证件类型和 `●` 未静默丢弃；
- [x] Excel 规格未生成 SKU 维度或组合；
- [ ] 已连接批准真机且确认现有受控登录会话；
- [ ] 最多 1～2 个样本完成点击前→面板→退出的证据链；
- [ ] 所有 observation 均为 `OBSERVED / NOT_OBSERVED / NOT_CONFIRMED`，无推断或伪造；
- [ ] Raw/hash/manifest/identity 与脱敏派生产物分离；
- [ ] Raw → Replay → DTO 验证完成；
- [ ] cleanup 与 `persistent_business_changes=false` 有证据；
- [ ] Independent Review 给出 `ACCEPT`。

## Test Plan

| Layer | Command | Current result |
|---|---|---|
| Input hash | `Get-FileHash` source and isolated copy | identical / PASS |
| Server parse | isolated `offline_parse.py` importing current `excel_match.py` helpers | rows=5, headers=4 / PASS |
| Web draft | isolated `offline_matrix.mjs` importing current `taskDraft.js` | valid=5, duplicate=0, invalid=0 / PASS |
| Real-device precheck | approved SDK `adb devices -l`；restart daemon 后再次枚举 | device_count=0 / BLOCKED |
| Local server | `python -m server.main`，process env only，`127.0.0.1:8080` | LISTEN；health/root/docs HTTP 200 / PASS |
| Raw/replay/DTO | after real capture | DEFERRED_NO_REAL_DEVICE_RAW；不得宣称 PASS |
| Regression | only after tracked evidence is finalized | PENDING |

## Oracle Gate

- Required：No for current setup/offline/real-device evidence collection；无 Server SQL/transaction/Schema change。
- Status：Oracle test suite 仍为 `SKIPPED / not applicable`；本地服务 lifespan 已使用批准的隔离测试环境成功启动，但这不等价于 Oracle Gate PASS。
- 若后续变更触及 Oracle-sensitive 范围，必须停止并重新分类；本 Task 不执行 migration。

## Real-device Gate

- Required：Yes。
- Approved scope：现有合法测试账号、真机、人工监督；单商品低频串行，仅打开/读取/退出 SKU 面板。
- Precheck：固定 Head `eb8a3221b55fba435a09f59dbc683047dd750431` 起步；`adb devices -l` 设备列表为空。随后执行 `adb kill-server` / `adb start-server` 并再次枚举，仍为 `DEVICE_COUNT=0`，因此 screen、PDD package 和现有会话检查均未执行。
- Current status：`HUMAN_GATE / BLOCKED — APPROVED_DEVICE_NOT_CONNECTED`。

## Local Server Recovery

- 从干净 `D:\work\PDD_con_data_main@f7d037cd612df09059dcea83189e63f99097042d` 启动，未写入或提交配置文件；
- 仅使用进程环境绑定 `APP_ENV=test`、`HOST=127.0.0.1`、`PORT=8080`；秘密值未写日志或 tracked 文件；
- `127.0.0.1:8080` 为 LISTEN，`GET /api/health` 返回 HTTP 200 与 `{\"ok\":true}`，`GET /`、`GET /docs` 均 HTTP 200；
- 主服务保持运行；专属停止脚本已在另一个短生命周期 probe 上验证，只停止 metadata 记录 PID，并验证 command/repository context；
- 本轮未调用业务写 API；服务启动可能执行既有 idempotent schema 检查，未做数据库前后差异审计，因此仅声明“无已观测业务写入”，不把启动动作表述为完整 Oracle Gate；
- `Raw → Replay → DTO` 标记 `DEFERRED_NO_REAL_DEVICE_RAW`，不记为 PASS；
- 因 ADB 未枚举到设备，本轮没有点击前详情、SKU_PANEL、组合或退出面板证据；样本数与 Raw Capture 数均为 0。

## Rollback

- 不修改原 Excel、生产配置、数据库或平台业务数据；
- 删除本机隔离输入/派生目录即可清理未提交副本；
- tracked docs/fixtures 可由 Task 专属 `ROLLBACK.sh` 恢复；
- 当前 `persistent_business_changes=false`。

## Human Decision Points

- 连接已批准真机并确认现有受控登录会话后可继续既定采样，无需扩大范围；
- 若需要输入/传输新账号、密码、OTP、验证码或人工验证，立即停止；
- 若目标页面必须越过订单/支付边界、需改变产品语义、Schema/migration 或扩大样本数，立即停止并请求 Product Owner。

## Stop Condition

- 当前已触发：本地服务恢复后再次检查固定 ADB，仍为 `DEVICE_COUNT=0`；Real-device Gate 为 `HUMAN_GATE / BLOCKED`，Replay/DTO 为 `DEFERRED_NO_REAL_DEVICE_RAW`；
- 后续证据足以提交独立 ADR/Schema Review，或证据推翻模型假设时停止；
- 不自动创建产品功能 PR，不实施 Schema/runtime，不 release，不启动下一任务。

## Evidence

- [`SKU-EVIDENCE-VALIDATION-001-offline-matrix.md`](SKU-EVIDENCE-VALIDATION-001-offline-matrix.md)
- [`SKU-EVIDENCE-VALIDATION-001-real-device-precheck.md`](SKU-EVIDENCE-VALIDATION-001-real-device-precheck.md)
- [`SKU-EVIDENCE-VALIDATION-001-evidence-manifest.json`](SKU-EVIDENCE-VALIDATION-001-evidence-manifest.json)
- [`SKU-EVIDENCE-VALIDATION-001-fixture.json`](SKU-EVIDENCE-VALIDATION-001-fixture.json)
- `SKU-EVIDENCE-VALIDATION-001-verification/`
