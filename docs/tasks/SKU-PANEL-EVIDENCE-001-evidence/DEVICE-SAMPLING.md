# SKU-PANEL-EVIDENCE-001 Device Sampling

## Outcome

- **Captured at**：2026-08-29 12:13–12:29 +08:00
- **Result**：`PARTIAL / BLOCKED — TARGET_IDENTITY_AND_RETRY_SEMANTICS_DEFECT`
- **Panel entry count**：`0`
- **Reason**：联机与 canonical Task 链路可用，但 Excel 5 行没有产生同时满足“输入身份匹配”和“页面已确认多规格”的安全候选。

## Runtime and device

```text
SERVICE_LISTEN=0.0.0.0:8080
HEALTH_HTTP=200
HEALTH_OK=True
DEVICE_ALIAS=device-e4a6069f4f
DEVICE_STATUS=online
ASSIGNED_TASK=False ACTIVE_JOB=False ACTIVE_ATTEMPT=False
```

真实 device key/serial、账号和鉴权材料未写入仓库。服务仅通过当前进程环境改变监听地址，仓库配置无变化。

## Candidate matrix

| Excel row | Canonical Task | Retained observation | Identity/multi-SKU decision | Action |
|---:|---:|---|---|---|
| 2 | 3528 | `3g*2丸/盒` 商品详情；输入为 `3G*1丸(铁盒装)`；CTA 为 `去复诊开药` | `NOT_APPLICABLE`：规格不一致且入口触及问诊边界；未确认多规格 | 未点击；取消 Task |
| 3 | 3529 | 药品详情，但页面品名/规格与输入 `银丹心脑通软胶囊 0.4g*36s` 不一致 | `NOT_APPLICABLE`：搜索结果漂移；未确认多规格 | 未点击；取消 Task |
| 4 | 3530 | 便携 Wi-Fi 商品 | `NOT_APPLICABLE`：明显非目标医疗器械 | 未点击；取消 Task |
| 5 | 3531 | 颈椎贴商品 | `NOT_APPLICABLE`：明显非目标 `骨痛灵酊` | 未点击；取消 Task |
| 6 | 3532 | 返回其他药品详情 | `NOT_APPLICABLE`：与 `复方罗布麻片 100s` 不一致 | 未点击；取消 Task |
| 4 exact retry | 3533 | 胶原蛋白敷料详情，但品牌/规格与输入不一致；底部两组圆形缩略图是“这些人已拼”的买家头像和拼单行，不是 SKU 选项 | `NOT_APPLICABLE`：身份不可靠；未确认多规格 | 未点击；取消 Task |

首行点击前 Original 帧已保存并记录 hash。最后一次搜索漂移帧也已保存；中间帧只用于当场 Stop/Continue 判断，未作为可复验 Original 留存。

## Canonical state and cleanup

```text
TASK_3528=cancelled; JOB_1511=cancelled; ATTEMPT_1313=failed/LOCAL_TASK_FINISHED; ATTEMPT_1314=cancelled/TASK_CANCELLED; leases=released
TASK_3529=cancelled; JOB_1512=cancelled; ATTEMPT_1315=cancelled/TASK_CANCELLED; lease=released
TASK_3530=cancelled; JOB_1513=cancelled; ATTEMPT_1316=cancelled/TASK_CANCELLED; lease=released
TASK_3531=cancelled; JOB_1514=cancelled; ATTEMPT_1317=cancelled/TASK_CANCELLED; lease=released
TASK_3532=cancelled; JOB_1515=cancelled; ATTEMPT_1318=cancelled/TASK_CANCELLED; lease=released
TASK_3533=cancelled; JOB_1516=cancelled; ATTEMPT_1319=cancelled/TASK_CANCELLED; lease=released
DEVICE_FINAL=online; assigned_task=false; active_job=false; active_attempt=false
RESULT_RECEIPT_COUNT=0
PRODUCT_COUNT=0
RAW_COLLECTION_COUNT=0
SNAPSHOT_COUNT=0
```

Task/Attempt 审计行按系统设计保留；未将其描述为“零数据库写入”。没有产生商品、Raw、Snapshot 或上传 ACK。

## Observation semantics

```text
sku_panel_entry_count=0
dimensions=NOT_OBSERVED
options=NOT_OBSERVED
combination_price=NOT_OBSERVED
availability=NOT_OBSERVED
ui_hierarchy=NOT_OBSERVED
return_path=NOT_EXECUTED_NO_PANEL
platform_sku_id=NOT_OBSERVED
cart_action=false
order_confirmation_clicked=false
order_submitted=false
payment_started=false
```

首行的 Excel `规格` 仍只属于 ProductAttribute candidate，未被转换为 SKU 维度或组合；页面主价未复制成组合价格。

## Original / derived separation

Original 位于仓库外：

- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\cast\task-3528-row1-detail-before.jpg`
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\runtime-final.txt`
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\cast\task-3534-row4-before.jpg`
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\task-3534-terminal.txt`

仓库只保留此脱敏报告和 manifest；截图、账号、Token、真实设备标识及网络 Raw 均未提交。

## Stop condition

已到达“目标页面不可安全取得/证据不足”的 Stop Condition。需要 Product Owner 提供或批准一个已确认多规格、且点击购买入口不会越过问诊/订单边界的测试商品后，才能续接同一 Task 的单次面板采样；本报告不支持启动 Generic SKU 契约冻结。

## Final canonical Task 3534

Product Owner 批准以 Excel 工作表第 4 行建立一个且仅一个最终 Task。Task `3534` / Job `1517` / Item `3811` 使用同一生命周期，没有创建或取消新的筛选 Task。

点击前投屏显示 `HURMEVKOR` 烟酰胺美白祛斑面膜，与输入“京润珍珠/医用重组III型人源化胶原蛋白敷贴(赠品)/5片装/湖南紫晶汇康”明显不一致。底部入口为 `去拼单`；因目标身份不匹配，未请求或执行人工点击。

```text
TASK=failed; success=0; fail=1
ITEM_3811=failed; product_id=None; message=LOCAL_TASK_FINISHED
JOB_1517=failed; attempt_count=5; active_attempt=None; error=transient/LOCAL_TASK_FINISHED; local_status=failed
ATTEMPT_1320..1324=failed; lease=released
PRODUCT=0; RAW=0; SNAPSHOT=0; RECEIPT=0; QUALITY=0; QUARANTINE=0
DEVICE_FINAL=online; assigned_task=false; active_job=false; active_attempt=false
```

五次 Attempt 均把“本地流程结束/没有合格目标”映射为 transient，导致同一错误商品页面被重复启动；直到达到 max attempts 后，Task 才聚合为 failed。没有错误 Complete，也没有数据污染，但错误分类造成不必要的重复执行，并且 Item 没有得到 `not_matched` 终态。

### Web visibility

```text
DETAIL_HTTP=200 OK=True TASK_STATUS=failed SUCCESS=0 FAIL=1 ITEMS=1
ITEM row=0 status=failed product_id=None message=LOCAL_TASK_FINISHED approval_present=True spec_present=True
RESULTS_HTTP=200 OK=True TOTAL=0 ITEMS=0
```

`TaskDetail.vue` 会把当前 Item 显示为“采集失败/匹配失败”，在失败页签展示 `LOCAL_TASK_FINISHED`，并显示“本次采集结果（0）”和空结果提示。源码 hash 一致的外置测试副本真实 mounted `TaskDetail`，输出 `TASK_DETAIL_COMPONENT=PASS`；`tests.test_web_result_visibility` 4 项也通过。当前 Web 能展示真实失败和零结果；“未匹配”未显示是因为服务端/Android 没有产生 `not_matched` 状态，不是 Web 伪造。

## Independent development Task candidates

1. **PDD-TARGET-IDENTITY-GATE-001（P0/P1）**：搜索结果进入详情或任何购买面板交互前，以服务端目标四字段和当前允许的匹配策略验证候选身份；不匹配结果不得成为 Product/Raw/Snapshot，不得进入 SKU_PANEL。验收需覆盖错误首条结果、相似标题、品牌/规格不一致和无候选。
2. **ANDROID-NOT-MATCHED-TERMINAL-001（P1）**：本地流程结束且不存在合格目标时，Item 返回可解释 `not_matched`，Job 使用非重试业务终态；`LOCAL_TASK_FINISHED/local_status=failed` 不得统一映射 transient。验收需证明单次执行、无 retry storm、Task 聚合正确、Web 显示未匹配原因。

两项属于同一条身份与失败语义链，可作为一个独立开发 Task 的两个 Acceptance 分支；本证据 Task 不实施代码修改。
