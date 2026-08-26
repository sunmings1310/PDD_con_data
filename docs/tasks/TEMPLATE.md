# <Task ID>：<Title>

- **Task ID**：
- **Title**：
- **Status**：BACKLOG | READY | IN_PROGRESS | TEST | REVIEW | CHANGES_REQUIRED | ACCEPTED | PR | MERGED | E2E | RELEASED

## Goal

## Context

## Scope

### Allowed

### Forbidden

## Non-goals

## Dependencies

## Affected Modules

## ADR

## Acceptance Criteria

- [ ]

## Test Plan

| Layer | Command | Input / Environment | Expected | Actual Result | Exit | Status |
|---|---|---|---|---|---:|---|
| Targeted |  |  |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Module |  |  |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |
| Full regression |  |  |  |  |  | PASS/FAIL/BLOCKED/SKIPPED |

## Oracle Gate

- Required：Yes / No
- Reason：
- Local isolated environment identifier：
- Fixed Head SHA：
- Canonical command / test count / literal result hash / exit：
- Evidence generated at / expiry：
- Four artifacts / rollback / persistent business changes：
- Hosted evidence validator：PASS / FAIL / BLOCKED / SKIPPED
- Independent Reviewer provenance check：ACCEPT / BLOCKED / pending

Oracle-sensitive Task 必须在固定 PR Head 本地 strict 通过；缺环境、参数、证据或 Reviewer 核验均为 `BLOCKED`。GitHub Actions 不连接数据库，只校验证据 manifest。Head 移动后旧证据失效并必须重跑。

## Real-device Gate

- Required：Yes / No
- Device/scenario：
- Command or steps / result：

## Rollback

- Code rollback：
- Configuration rollback：
- Data recovery：
- Irreversible items：

## Human Decision Points

## Stop Condition

## Evidence

- Original evidence：
- Derived artifacts：
- Review findings：
- Commit / PR：
