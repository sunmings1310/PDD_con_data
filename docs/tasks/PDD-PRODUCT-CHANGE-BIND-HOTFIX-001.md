# PDD-PRODUCT-CHANGE-BIND-HOTFIX-001：修复 Product Change Oracle 非法绑定名

- **Task ID**：PDD-PRODUCT-CHANGE-BIND-HOTFIX-001
- **Title**：修复 Product Change Oracle 非法绑定名
- **Status**：REVIEW ACCEPT / WAITING DRAFT PR

## Goal

修复 `PUT /api/products/{product_id}` 写入 `SJZQ_PRODUCT_CHANGE`，以及 `POST /api/products/save-batch` 更新 `SAVED_BY` 时因 Oracle 绑定变量 `:uid` 触发 `ORA-01745` 的 P0 运行故障，并以真实隔离 Oracle 回归证明更新、保存资料库与变更审计可提交。

## Context

- 固定基线：`main@80b3435558e67850c9cba4215ca81456721ef0db`。
- 实时证据：`server/routers/products.py::_record_change` 的 INSERT 与 `save_products` 的 UPDATE 均使用 `:uid`；Oracle 拒绝该绑定名，而非保留名称可执行。第一处修复后，真实 `save-batch` 再次精确复现第二处 `ORA-01745`。
- 本 Task 只处理这两个已复现 Product 保存调用链，不扩大到其他模块的历史 SQL 清理。

## Scope

### Allowed

- 将 `_record_change` 中 `:uid` 及参数键改为 `:actor_user_id`，将 `save_products` 中 `:uid` 及参数键改为 `:saved_by_user_id`。
- 增加离线契约测试与真实隔离 Oracle 执行测试，覆盖审计 INSERT 的绑定、提交和清理。
- 更新本 Task、最小 backlog 状态与专属验证制品。

### Forbidden

- 业务语义、Product/Change Schema、migration、生产配置或生产数据变更。
- Generic SKU、P1 Schema、Phase 6B、无关 SQL 重命名或重构。
- merge、release。

## Non-goals

- 不改变商品更新权限、租户边界、字段映射、审计内容或事务边界。
- 不清理仓库内所有相似绑定名；未实际纳入本调用链的问题另建 Task。

## Dependencies

- 已批准隔离 Oracle 测试环境；秘密只通过进程环境提供且不写入证据。

## Affected Modules

- `server/routers/products.py`
- 产品更新/变更审计的 targeted 与 Oracle tests
- 本 Task 文档与验证制品

## ADR

无需 ADR。属于保持既有语义的 Oracle 驱动兼容性修复。

## Acceptance Criteria

- [x] `_record_change` 与 `save_products` 不再使用 Oracle 非法绑定名 `:uid`。
- [x] 离线回归断言 SQL 与参数键一致且不含问题绑定名。
- [x] 隔离 Oracle 实际执行 Product Change INSERT，以及真实 `save_products → UPDATE → _record_change → commit`，读取到预期 `SAVED_BY/USER_ID`，随后双表清理为零残留。
- [x] `PUT /api/products/{id}` 既有 targeted 回归继续通过。
- [x] Python full regression、compile 与 `git diff --check` 通过。
- [x] Independent Review 为 `ACCEPT`。

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted offline | `python -m unittest tests.test_product_change_bind tests.test_product_consistency_p0 -v` | test-only injected config | 非保留绑定且 PUT 契约无回归 | `Ran 7 tests ... OK` | 0 | PASS |
| Oracle targeted | `python -m unittest tests.test_product_change_bind_oracle -v` | 已批准隔离 Oracle；秘密仅进程环境 | 实际 INSERT 与 save-batch/读取/cleanup | 两项真实 Oracle case 均由 canonical strict 执行 | 0 | PASS |
| Python full | `powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite python -Strict` | Python 3.10 fixed Head | Python baseline PASS | `Ran 253 tests ... OK (skipped=33)`；summary PASS | 0 | PASS |
| Oracle strict | `powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict` | Phase 1–6A flags + 隔离 Oracle | canonical suite 包含两条 hotfix Oracle test | `Ran 55 tests in 330.866s ... OK`；summary PASS | 0 | PASS |
| Static | `python -m compileall server tests`; `git diff --check` | fixed Head | 无语法/whitespace 错误 | no errors / no output | 0 | PASS |

## Oracle Gate

- Required：Yes
- Reason：故障是 Oracle 对绑定变量名的真实解析错误；mock 不足以验收。
- Local isolated environment identifier：已批准专用可写可清理 Oracle；不记录秘密值。
- Fixed code Head SHA：`892fa9faf224b3c3160d26dfcdd85bd65522209f`
- Canonical command / test count / literal result hash / exit：`powershell -NoProfile -File .\scripts\test-baseline.ps1 -Suite oracle -Strict`；55/55；`OK`；exit 0。
- Evidence generated at / expiry：2026-08-31 本地隔离 Oracle；PR Head 变化后失效并重跑。
- Four artifacts / rollback / persistent business changes：专属验证目录；Oracle fixture cleanup=0；persistent business changes=false。
- Hosted evidence validator：GitHub 不连接 Oracle；Hosted CI 仅运行非数据库门禁。
- Independent Reviewer provenance check：`ACCEPT`（最终 code Head `892fa9f`；两处生产绑定、离线与真实 Oracle 路径均复核）。

## Real-device Gate

- Required：No
- Device/scenario：服务端 Oracle SQL hotfix，不改变 Android。
- Command or steps / result：SKIPPED / not applicable。

## Rollback

- Code rollback：revert 本 Task commit，恢复基线文件。
- Configuration rollback：无配置变更。
- Data recovery：Oracle fixture 在测试事务/cleanup 中删除；不得保留业务变化。
- Irreversible items：无。

## Human Decision Points

- Draft PR 可在 Review ACCEPT 后创建；merge/release 仍需 Product Owner 明确批准。

## Stop Condition

- Oracle targeted 与回归通过、Independent Review ACCEPT 后创建 Draft PR 并停止在 merge 门禁。
- 若修复需要 Schema/migration、改变审计语义或触及生产数据，立即停止。

## Evidence

- Original evidence：实时 `PUT /api/products/1182` 返回 500；Oracle `ORA-01745`；最小探针对比 `:uid` 失败、非保留绑定成功。
- Derived artifacts：`docs/tasks/PDD-PRODUCT-CHANGE-BIND-HOTFIX-001-verification/`。
- Review findings：`ACCEPT`。两条已复现 Product 保存链路均关闭；其他模块若存在历史 `:uid`，不在本 Task 范围。
- Commit / PR：`352b4101af797e4fbe619d7d6a7e6e4e867497a3`（首处修复）；`973eeedab3c6ae83c5b96ac2aac622add12fde87`（canonical Oracle gate）；`892fa9faf224b3c3160d26dfcdd85bd65522209f`（save-batch closure）；PR pending。
