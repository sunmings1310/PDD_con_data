# Project Rules

## Development principles

- 修改代码前先阅读相关模块。
- 不确定业务逻辑时不得自行假设。
- 优先修复根因，不使用临时 workaround。
- 不允许无关重构。
- 每次任务尽量保持单一目的。

## Architecture

- 保持现有分层结构。
- 网络层、业务层、数据层不得随意交叉。
- 新依赖必须说明必要性。

## Testing

所有功能修改必须：
- 运行现有测试
- 补充相关测试
- 报告实际测试结果

## Documentation

架构发生变化：
更新 docs/architecture.md

需求完成：
更新 docs/backlog.md

重要技术决策：
写入 docs/decisions/