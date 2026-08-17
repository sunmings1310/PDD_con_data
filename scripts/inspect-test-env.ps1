[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Write-Check([string]$Name, [string]$Status, [string]$Detail) {
    Write-Output ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
}

function Test-PythonDependencies([string]$Candidate) {
    & $Candidate -c 'import loguru, oracledb' 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-PythonPath {
    if ($env:PDD_PYTHON -and (Test-Path -LiteralPath $env:PDD_PYTHON)) { return $env:PDD_PYTHON }
    foreach ($candidate in @("$Root\.venv\Scripts\python.exe", "$Root\.venv-t001\Scripts\python.exe")) {
        if ((Test-Path -LiteralPath $candidate) -and (Test-PythonDependencies $candidate)) { return $candidate }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Get-JdkHome {
    if ($env:JAVA_HOME -and (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { return $env:JAVA_HOME }
    foreach ($candidate in @("$Root\.tools\jdk-17.0.20+8", "$Root\.tools\jdk-17")) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'bin\java.exe')) { return $candidate }
    }
    return $null
}

function Get-AndroidSdkRoot {
    foreach ($candidate in @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    $properties = Join-Path $Root 'android_collector\local.properties'
    if (Test-Path -LiteralPath $properties) {
        $line = Get-Content -LiteralPath $properties | Where-Object { $_ -match '^\s*sdk\.dir\s*=' } | Select-Object -First 1
        if ($line) {
            $value = ($line -replace '^\s*sdk\.dir\s*=\s*', '') -replace '\\:', ':' -replace '\\\\', '\\'
            if (Test-Path -LiteralPath $value) { return $value }
        }
    }
    return $null
}

Write-Output 'PDD test environment probe (does not print connection strings or secrets)'

$python = Get-PythonPath
if ($python) {
    $version = & $python --version 2>&1
    if ($version -match '^Python 3\.10\.') { Write-Check 'python' 'READY' "$version ($python)" }
    else { Write-Check 'python' 'BLOCKED' "need Python 3.10.x; found $version" }
} else { Write-Check 'python' 'BLOCKED' 'set PDD_PYTHON or create .venv with Python 3.10.x' }

$node = Join-Path $Root '.tools\node-v22.18.0-win-x64\node.exe'
if (Test-Path -LiteralPath $node) {
    Write-Check 'node' 'READY' "$(& $node --version) ($node)"
} else {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($nodeCommand) { Write-Check 'node' 'BLOCKED' "need Node 22.18.x; bundled Node is absent, found $(& $nodeCommand.Source --version)" }
    else { Write-Check 'node' 'BLOCKED' 'bundled Node 22.18.x is absent' }
}

$jdk = Get-JdkHome
if ($jdk) {
    $version = & (Join-Path $jdk 'bin\java.exe') -version 2>&1 | Select-Object -First 1
    if ($version -match '"17\.') { Write-Check 'jdk' 'READY' "$version ($jdk)" }
    else { Write-Check 'jdk' 'BLOCKED' "need JDK 17; found $version" }
} else { Write-Check 'jdk' 'BLOCKED' 'run .\scripts\bootstrap-jdk17.ps1 or set JAVA_HOME to JDK 17' }

$sdk = Get-AndroidSdkRoot
if ($sdk -and (Test-Path (Join-Path $sdk 'platforms\android-34')) -and (Test-Path (Join-Path $sdk 'build-tools\34.0.0'))) {
    Write-Check 'android-sdk' 'READY' 'Platform 34 and Build Tools 34.0.0 are available'
} else { Write-Check 'android-sdk' 'BLOCKED' 'set ANDROID_SDK_ROOT (or android_collector/local.properties) to an SDK with Platform 34 and Build Tools 34.0.0' }

$oracleRequired = @('T003_ORACLE_DSN', 'T003_ORACLE_USER', 'T003_ORACLE_PASSWORD')
$oracleMissing = @($oracleRequired | Where-Object { -not (Get-Item -Path "Env:$($_)" -ErrorAction SilentlyContinue).Value })
if ($env:T003_ORACLE_TEST_ENABLED -eq '1' -and $oracleMissing.Count -eq 0) {
    Write-Check 'oracle-integration' 'READY' 'isolated test configuration is present; test-baseline will run real tests'
} else {
    Write-Check 'oracle-integration' 'BLOCKED' 'configure an isolated T003 schema as documented in docs/tasks/T003-oracle-test-env.md'
}

$docker = Get-Command docker.exe -ErrorAction SilentlyContinue
if ($docker) { Write-Check 'docker' 'READY' 'docker.exe is available for the documented isolated Oracle setup' }
else { Write-Check 'docker' 'INFO' 'docker.exe is not available; use a separately managed isolated Oracle test schema' }
