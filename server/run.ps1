# 启动数据采集中控 Web 服务
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
& "$Root\.venv\Scripts\python.exe" -m server.main
