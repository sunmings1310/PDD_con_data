# SKU-PANEL-EVIDENCE-001 Device Sampling

## Outcome

- **Captured at**：2026-08-29 12:13–12:29 +08:00
- **Result**：`PARTIAL / BLOCKED — NO_CONFIRMED_MULTI_SKU_CANDIDATE`
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
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\cast\frame-001.jpg`
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\runtime-final.txt`

仓库只保留此脱敏报告和 manifest；截图、账号、Token、真实设备标识及网络 Raw 均未提交。

## Stop condition

已到达“目标页面不可安全取得/证据不足”的 Stop Condition。需要 Product Owner 提供或批准一个已确认多规格、且点击购买入口不会越过问诊/订单边界的测试商品后，才能续接同一 Task 的单次面板采样；本报告不支持启动 Generic SKU 契约冻结。
