# Android Collector Module Rules

适用于 `android_collector/`。同时遵守根 [`AGENTS.md`](../AGENTS.md)。

- 服务端是任务和 Lease 真相；Room 只保存可恢复 assignment、checkpoint、outbox 和本地执行状态。
- 页面操作、Parser 返回或 HTTP 2xx 不等于成功。只有明确 `acknowledged + persisted` 的 receipt 才能推进 checkpoint/complete。
- Product/outbox 写入必须保持原子；进程/App 重启、网络恢复和重复提交不能静默丢数据或重复业务事实。
- 平台特有 Selector、文案、点击和解析放在 Collector Adapter；核心调度不得新增 PDD 特判。
- 不承诺无限后台常驻。系统 kill/Doze 下必须依赖 WorkManager/合法前台机制和服务端 Lease reclaim 降级。
- Room schema 变更必须提供 migration 和升级测试；禁止 `fallbackToDestructiveMigration` 处理用户任务数据。
- 使用 JDK 17、SDK 34，优先运行相关 JVM 测试，最终执行 `testDebugUnitTest --no-daemon`。Release 签名只由环境/本机 secret 注入。
