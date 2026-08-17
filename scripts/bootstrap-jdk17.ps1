[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root '.tools'
$Version = '17.0.20+8'
$Archive = Join-Path $Tools 'OpenJDK17U-jdk_x64_windows_hotspot_17.0.20_8.zip'
$ExpectedSha256 = '418497BE5CF585BDD2203D6486A565D66D3F5E992D5630D45104CB873FAB8122'
$Destination = Join-Path $Tools "jdk-$Version"
$Uri = 'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20%2B8/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20_8.zip'

if (Test-Path -LiteralPath (Join-Path $Destination 'bin\java.exe')) {
    & (Join-Path $Destination 'bin\java.exe') -version
    Write-Output "JDK17_READY=$Destination"
    exit 0
}

New-Item -ItemType Directory -Path $Tools -Force | Out-Null
if (-not (Test-Path -LiteralPath $Archive)) {
    Invoke-WebRequest -Uri $Uri -OutFile $Archive
}
$actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
if ($actual -ne $ExpectedSha256) {
    throw "JDK archive checksum mismatch: expected $ExpectedSha256, got $actual"
}
Expand-Archive -LiteralPath $Archive -DestinationPath $Tools -Force
if (-not (Test-Path -LiteralPath (Join-Path $Destination 'bin\java.exe'))) {
    throw "JDK archive did not create expected directory: $Destination"
}
& (Join-Path $Destination 'bin\java.exe') -version
Write-Output "JDK17_READY=$Destination"
