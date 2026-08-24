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
- Status and evidence：

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
- [ ] 风险、已知问题和回滚完整
- [ ] Reviewer 已明确 `ACCEPTED`
- [ ] merge 仍等待维护者明确批准
