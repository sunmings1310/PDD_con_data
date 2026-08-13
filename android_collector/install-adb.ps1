# 无数据线时：若手机开发者选项有「无线调试」，可用本脚本安装
param(
    [string]$Connect = ''  # 例：192.168.1.20:37561  或配对后的地址
)
$ErrorActionPreference = 'Stop'
$adb = 'D:\代码库\pda-picking\tools\android-sdk\platform-tools\adb.exe'
if (-not (Test-Path $adb)) { $adb = (Get-Command adb -ErrorAction SilentlyContinue).Source }
if (-not $adb) { throw '未找到 adb' }

$apk = @(
    (Join-Path $PSScriptRoot 'dist\联机工具-v1.0.23.apk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) '联机工具-v1.0.23.apk')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $apk) { throw '未找到 联机工具-v1.0.23.apk' }

& $adb start-server | Out-Null
if ($Connect) {
    Write-Host "连接 $Connect ..."
    & $adb connect $Connect
}
$devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_ -match 'device$' }
if (-not $devices) {
    Write-Host @'
未检测到设备。无数据线时可试：
1) 手机与电脑同一 WiFi
2) 设置 → 系统和更新 → 开发人员选项
3) 若有「无线调试」：打开后点进详情，看 IP:端口
4) 再运行:  .\install-adb.ps1 -Connect 192.168.x.x:端口
Mate 60 若没有「无线调试」项，只能借数据线，或用下方「断网点装」方式。
'@
    exit 1
}
foreach ($p in @('com.sjzq.collector','com.sjzq.tool.app','com.linkdesk.tool')) {
    & $adb uninstall $p 2>$null | Out-Null
}
& $adb install -r $apk
if ($LASTEXITCODE -ne 0) { throw "install failed: $LASTEXITCODE" }
Write-Host '安装完成。无障碍里打开「联机工具」。'
