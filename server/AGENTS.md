# Server Module Rules

适用于 `server/`。同时遵守根 [`AGENTS.md`](../AGENTS.md)。

- FastAPI router 负责协议和权限适配；状态机、事务和幂等语义进入 service/domain 层，禁止复制 SQL 状态转换。
- Oracle 是 Task/Job/Attempt/Lease、租户、Receipt、Product/Snapshot/Quality 的权威来源。任何写入必须保留事务边界和当前 ownership fence。
- Schema 只能通过版本化、可重入 migration 修改；禁止启动时无版本 DDL、手工生产改表和无批准破坏性迁移。
- 配置必须来自环境或本机未跟踪文件；错误与日志不得回显密码、JWT、Lease token 或设备密钥。
- Pydantic/API 契约变化必须同步 Android/Web 消费方或提供兼容路径。
- 优先运行相关 Python 单测；涉及 Oracle 语义时补真实专用 Oracle 测试。缺环境必须为 BLOCKED/SKIPPED，不得使用 Mock 结果替代 Oracle PASS。
