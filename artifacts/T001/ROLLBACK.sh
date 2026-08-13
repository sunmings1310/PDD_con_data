#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Source = "$PSScriptRoot/ORIGINAL_FILE.txt"
)
Copy-Item -LiteralPath $Source -Destination $Target -Force
Write-Output "restored:$Target"
