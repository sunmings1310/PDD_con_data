# PDD-TARGET-MATCH-TERMINAL-001 Proposal

> 状态：`PROPOSED / WAITING FOR PRODUCT OWNER APPROVAL`
> 来源：`SKU-PANEL-EVIDENCE-001`；本文件只冻结候选范围与验收，不授权开发。

## Goal

修复同一条 PDD 搜索身份与失败终态链：不相关搜索结果不得成为目标商品；无合格目标必须以可解释、非重试的 `not_matched` 终态结束。

## Scope

### Acceptance branch A：两阶段目标身份门禁（P0/P1）

1. 搜索卡片阶段使用当前可见的标题、店铺、规格摘要或平台标识做初筛；不得要求卡片具备详情页才可取得的完整四字段。
2. 允许只读进入候选详情以取得完整目标字段。
3. 在任何购买/SKU 交互、Product/Raw/Snapshot 持久化或成功 ACK 前，由 `ProductTargetMatcher` 对任务目标与详情事实执行权威匹配。
4. 明显不相关首条结果、相似标题、品牌不一致、规格不一致和无候选均不得进入 SKU_PANEL 或业务持久化。

### Acceptance branch B：`not_matched` 非重试业务终态（P1）

1. 无合格目标时只产生一次 Attempt。
2. Item 进入 `not_matched`，包含稳定、可解释的原因码。
3. Job 进入非重试业务终态；不得映射为 `transient/LOCAL_TASK_FINISHED`。
4. Task 聚合正确，不发生 retry storm 或错误 Complete。
5. API/Web 显示“未匹配”原因与本次结果 `0`。
6. Result、Product、Raw、Snapshot 均为 `0`，Lease 释放，设备恢复 idle。

## Required tests

- Android：错误首条搜索结果、相似标题、品牌/规格不一致、无候选、单 Attempt 与 `not_matched` 上传。
- Server：`not_matched` 状态转换、非重试分类、Task 聚合、幂等重复上报、Lease 释放。
- Web/API：未匹配原因、失败/结果零的准确展示。
- Oracle：真实 transaction/tenant 场景下的 Item/Job/Attempt/Task 终态与零业务结果门禁。
- E2E：一个错误候选产生一次 `not_matched`；修复后再用一个预先确认的多规格商品重跑 `SKU-PANEL-EVIDENCE-001`。

## Non-goals

- 不实现 Generic SKU runtime、SKU Schema/migration、P1 或 Phase 6B；
- 不改变 Product identity、Snapshot 或 Task Complete 产品语义；
- 不通过前端防抖或人工取消掩盖服务端/Android 终态缺陷。

## Stop Condition

等待 Product Owner 单独批准开发 Task。未批准前不建实现分支、不修改业务代码、不创建功能 PR。
