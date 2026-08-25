## Task ID / ADR

- **Task ID**：
- **ADR**：链接或 `None`

## Summary

## Scope

- Allowed：
- Affected modules：

## Non-goals

## Migration

- Schema/data migration：None / details
- Approval and reversibility：

## Actual Tests

| Gate | Exact command / environment | Literal result | Exit | Status |
|---|---|---|---:|---|
| Python |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Android JVM |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Web build |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Compile/static |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Oracle |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Real device |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |

`BLOCKED`/`SKIPPED` 不得写为 `PASS`。只有明确不适用的 Oracle Gate 才可 `SKIPPED`；Required/启用但未配置时必须记为 `BLOCKED`。

## Oracle Status

- Required：Yes / No
- Status and evidence：本地隔离 Oracle strict manifest / 明确不适用理由
- Fixed PR Head：
- Independent Reviewer provenance check：ACCEPT / BLOCKED / pending

Required 时，在固定 Head 运行 canonical strict command，并把完整 manifest 放入下方唯一 marker 后的 JSON code block。提交 manifest 后不得移动 Head；Head 移动必须重跑并替换证据。GitHub 只验证证据结构、Head/时效/hash/结果与四制品，不连接数据库；Reviewer 仍需核验本地运行来源。

<!-- oracle-local-evidence:v1 -->
```json
{}
```

## Real-device Status

- Required：Yes / No
- Status and evidence：

## Risk

## Rollback

- Code/config：
- Data recovery / irreversible items：

## Known Issues

## Documentation

- [ ] `docs/CURRENT_STATE.md` 已更新
- [ ] `docs/CURRENT_STATE.md` 不适用，原因已说明
- [ ] 适用的 `PRODUCT.md` / ADR / architecture / Task / backlog 已更新

## Reviewer Checklist

- [ ] 变更符合 Task Scope，无无关重构
- [ ] 实际测试和外部门禁状态可复现
- [ ] Oracle-sensitive 时，本地 strict 证据绑定当前 Head，且未把 BLOCKED/SKIPPED 冒充 PASS
- [ ] Reviewer 已核对本地 Oracle 来源、隔离、rollback 与四制品；未宣称等价于 Hosted DB run
- [ ] 风险、已知问题和回滚完整
- [ ] Reviewer 已明确 `ACCEPTED`
- [ ] merge 仍等待维护者明确批准
