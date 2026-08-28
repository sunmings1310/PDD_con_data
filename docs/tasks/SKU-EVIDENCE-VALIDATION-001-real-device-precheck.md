# SKU-EVIDENCE-VALIDATION-001 Real-device Precheck

- Date：2026-08-28
- Gate：Required
- Approved SDK adb：`D:\work\pda-picking\tools\android-sdk\platform-tools\adb.exe`
- Interaction performed：passive device enumeration only

## Literal result

```text
* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached

adb.exe: no devices/emulators found
```

## Gate result

`HUMAN_GATE / BLOCKED — APPROVED_DEVICE_NOT_CONNECTED`

- 未检查或回显账号、cookie、token 或设备标识；
- 未打开拼多多、未搜索商品、未点击购买入口；
- 未创建采样任务或 Raw Capture；
- 未发生订单、购物车、提交或支付动作；
- `persistent_business_changes=false`。

恢复条件：连接已批准真机并完成现有 ADB 授权；设备上存在已批准的受控登录会话。若需要新账号、密码、OTP、验证码或人工验证，仍保持 Human Gate 并停止。
