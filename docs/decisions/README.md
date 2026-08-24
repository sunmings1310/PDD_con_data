# Architecture Decision Records

本目录保存影响产品不变量、跨模块协议、数据模型、迁移、安全或长期兼容性的决策。第一轮治理不批量重命名历史 ADR；现有文件在实际修改时逐步补齐元数据。

## 状态

- **Proposed**：讨论中，不能作为实现授权。
- **Accepted**：已批准并生效。
- **Superseded**：被新 ADR 明确替代，保留历史。
- **Rejected**：明确不采用，保留原因。
- **Deprecated**：实现可能仍存在，但不再用于新能力。

## 新 ADR 命名

新文件使用 `YYYY-MM-DD-short-kebab-title.md`。现有 `phase*.md`、`T*.md` 文件保留原名。

## 必需字段

每个新 ADR 必须具有以下字段，不适用时填写 `None` 并解释：

```markdown
# ADR：<Title>

- ID：ADR-YYYY-NNN
- Status：Proposed | Accepted | Superseded | Rejected | Deprecated
- Date：YYYY-MM-DD
- Supersedes：相对链接或 None
- Superseded By：相对链接或 None

## Context

## Decision

## Alternatives

## Consequences

## Migration
```

字段语义：

- **ID**：稳定且唯一的决策标识；
- **Status / Date**：生效状态和决策日期；
- **Context**：问题、约束与证据；
- **Decision**：可机械判断的选择；
- **Alternatives**：其他方案和拒绝原因；
- **Consequences**：收益、代价、风险与兼容影响；
- **Migration**：实施、兼容、回滚或 `None`；
- **Supersedes / Superseded By**：双向链接决策替代关系。

Accepted ADR 的语义变化必须创建新 ADR，并显式 `Supersedes` 旧 ADR；不得静默改写历史结论。权威顺序见 [`../../AGENTS.md`](../../AGENTS.md#2-文档权威顺序)。
