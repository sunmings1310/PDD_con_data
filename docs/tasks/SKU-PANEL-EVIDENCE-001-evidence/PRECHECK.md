# SKU-PANEL-EVIDENCE-001 E2E Precheck

- **Captured at**：2026-08-29 11:42–11:43 +08:00
- **Baseline**：`main@80b3435558e67850c9cba4215ca81456721ef0db`
- **Result**：`HUMAN_GATE / BLOCKED — APPROVED_DEVICE_NOT_CONNECTED`

## Service

```text
COMMAND=<REDACTED_ENV> D:\work\PDD_con_data\.venv-t001\Scripts\python.exe -m server.main
INPUT=working directory D:\work\PDD_con_data_main; APP_ENV=test; HOST=127.0.0.1; PORT=8080; Oracle/JWT loaded from the existing approved local environment without printing values
LITERAL_REDACTED_OUTPUT=LISTEN=127.0.0.1:8080 STATE=Listen PID=17756; HEALTH_HTTP=200; HEALTH_BODY={"ok":true,"oracle":"<REDACTED>","image_dir":"<REDACTED_LOCAL_PATH>","web_dist":true,"ocr_license_filter":true}
EXIT=0
RESULT=PASS
```

The runtime was started without changing a repository configuration file. The validated stop command is:

```text
powershell -NoProfile -File C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\runtime\server-8080\stop_server.ps1
```

The stop script parsed with `STOP_SCRIPT_PARSE_ERRORS=0`. It was not run against the main service because the service must remain available at the Human Gate.

## Device

```text
COMMAND=D:\work\pda-picking\tools\android-sdk\platform-tools\adb.exe kill-server; D:\work\pda-picking\tools\android-sdk\platform-tools\adb.exe start-server; D:\work\pda-picking\tools\android-sdk\platform-tools\adb.exe devices -l
INPUT=approved adb binary; expected exactly one previously approved physical device
LITERAL_REDACTED_OUTPUT=* daemon not running; starting now at tcp:5037 | * daemon started successfully | List of devices attached | DEVICE_COUNT=0
EXIT=2 (gate command deliberately returns 2 when device count is not exactly one)
RESULT=BLOCKED
```

Because no device was visible, the following checks were not executed:

- screen/unlock state：`NOT_EXECUTED_NO_DEVICE`
- PDD package：`NOT_EXECUTED_NO_DEVICE`
- controlled login session：`NOT_EXECUTED_NO_DEVICE`
- confirmed multi-SKU sample selection：`NOT_EXECUTED_NO_DEVICE`
- SKU panel entry/exit：`NOT_EXECUTED_NO_DEVICE`

No real device serial was stored or printed. A serial hash/alias will only be created after exactly one approved device is visible.

## Sampling and guards

```text
sample_count=0
sku_panel_entry_count=0
cart_action=false
order_confirmation_clicked=false
order_submitted=false
payment_started=false
api_business_write_attempted=false
persistent_business_changes=false (within the observed local-service/device-precheck scope)
```

No product page, SKU option, price, combination, platform SKU ID, UI hierarchy, screenshot, network capture, or account datum was observed. Those fields are `NOT_OBSERVED`, not inferred.

## Original / derived separation

Original runtime evidence remains outside the repository at:

- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\service-precheck.txt`
- `C:\Users\Eden\AppData\Local\Temp\SKU-PANEL-EVIDENCE-001\original\adb-precheck.txt`

This repository file is a redacted derived report. Hashes and paths are recorded in `manifest.json`.

## Resume condition

Connect the already-approved device by USB, keep the existing ADB authorization, and unlock the screen. Do not click the purchase/group-buy entry before E2E resumes. The next check is a single `adb devices -l`; sampling remains limited to one confirmed multi-SKU product and one panel entry.
