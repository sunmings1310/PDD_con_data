# SKU-EVIDENCE-VALIDATION-001 Real-device Precheck

- Date：2026-08-28
- Gate：Required
- Approved SDK adb：`D:\work\pda-picking\tools\android-sdk\platform-tools\adb.exe`
- Interaction performed：passive device enumeration and local adb daemon restart only

## Literal result

```text
* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached

adb.exe: no devices/emulators found
```

用户声明真机已准备并完成 ADB 授权后，本机再次执行：

```text
adb kill-server
adb start-server
* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
DEVICE_COUNT=0
EXIT=0
```

脱敏本地证据：`C:\Users\Eden\AppData\Local\Temp\SKU-EVIDENCE-VALIDATION-001\evidence\adb-precheck-20260828-retry.txt`（不提交），SHA-256 `3fe59b0c59a5519e692a52fce08b7e70dac7bf1896c485e3d87abe30febd6cc8`。

## Gate result

`HUMAN_GATE / BLOCKED — APPROVED_DEVICE_NOT_CONNECTED`

- 未检查或回显账号、cookie、token 或设备标识；
- 未打开拼多多、未搜索商品、未点击购买入口；
- 未创建采样任务或 Raw Capture；
- 未发生订单、购物车、提交或支付动作；
- 因没有设备连接，screen、PDD package 和登录会话检查均为 `NOT_EXECUTED_NO_DEVICE`；
- Product Owner 声明 Server unavailable，本轮未尝试 Oracle、生产 DB 或 API，`Raw → Replay → DTO=DEFERRED_SERVER_UNAVAILABLE`；
- 在已观测范围内 `persistent_business_changes=false`。

恢复条件：连接已批准真机并完成现有 ADB 授权；设备上存在已批准的受控登录会话。若需要新账号、密码、OTP、验证码或人工验证，仍保持 Human Gate 并停止。
