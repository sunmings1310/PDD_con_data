[CmdletBinding()]
param(
    [ValidateSet('all', 'python', 'oracle', 'android', 'web')]
    [string]$Suite = 'all',
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PassCount = 0
$FailCount = 0
$BlockedCount = 0

function Add-Result([string]$Name, [string]$Status, [string]$Detail) {
    switch ($Status) {
        'PASS' { $script:PassCount++ }
        'FAIL' { $script:FailCount++ }
        'BLOCKED' { $script:BlockedCount++ }
    }
    Write-Output ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
}

function Should-Run([string]$Name) { return $Suite -eq 'all' -or $Suite -eq $Name }

function Test-PythonDependencies([string]$Candidate) {
    & $Candidate -c 'import loguru, oracledb' 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-PythonPath {
    if ($env:PDD_PYTHON -and (Test-Path -LiteralPath $env:PDD_PYTHON)) { return $env:PDD_PYTHON }
    foreach ($candidate in @("$Root\.venv\Scripts\python.exe", "$Root\.venv-t001\Scripts\python.exe")) {
        if ((Test-Path -LiteralPath $candidate) -and (Test-PythonDependencies $candidate)) { return $candidate }
    }
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

function Invoke-Native([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        if ([IO.Path]::GetExtension($File) -in @('.bat', '.cmd')) {
            $command = 'call "' + $File + '" ' + ($Arguments -join ' ')
            $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/c', $command) -WorkingDirectory $WorkingDirectory -Wait -PassThru -NoNewWindow
        } else {
            $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -Wait -PassThru -NoNewWindow
        }
        $nativeExit = $process.ExitCode
        if ($nativeExit -eq 0) { Add-Result $Name 'PASS' 'exit=0' }
        else { Add-Result $Name 'FAIL' "exit=$nativeExit" }
    } catch {
        Add-Result $Name 'FAIL' $_.Exception.Message
    } finally {
        Pop-Location
    }
}

if (Should-Run 'python') {
    $python = Get-PythonPath
    if (-not $python) { Add-Result 'python-unit' 'BLOCKED' 'set PDD_PYTHON or create .venv with Python 3.10.x' }
    elseif ((& $python --version 2>&1) -notmatch '^Python 3\.10\.') { Add-Result 'python-unit' 'BLOCKED' 'requires Python 3.10.x' }
    else { Invoke-Native 'python-unit' $python @('scripts/run_python_unit_tests.py') $Root }
}

if (Should-Run 'oracle') {
    $python = Get-PythonPath
    $required = @('T003_ORACLE_DSN', 'T003_ORACLE_USER', 'T003_ORACLE_PASSWORD')
    $missing = @($required | Where-Object { -not (Get-Item -Path "Env:$($_)" -ErrorAction SilentlyContinue).Value })
    if (-not $python) { Add-Result 'oracle-integration' 'BLOCKED' 'Python test environment is unavailable' }
    elseif ($env:T003_ORACLE_TEST_ENABLED -ne '1' -or $missing.Count -gt 0) {
        Add-Result 'oracle-integration' 'BLOCKED' 'requires T003_ORACLE_TEST_ENABLED=1 and isolated T003 Oracle environment variables; see docs/tasks/T003-oracle-test-env.md'
    } else {
        Invoke-Native 'oracle-integration' $python @(
            '-m', 'unittest', '-v',
            'tests/test_task_state_r2_oracle.py',
            'tests/test_phase2_schema_contract.py',
            'tests/test_job_service.py',
            'tests/test_phase2_route_oracle.py',
            'tests/test_phase3_oracle.py'
        ) $Root
    }
}

if (Should-Run 'android') {
    $jdk = Get-JdkHome
    $sdk = Get-AndroidSdkRoot
    if (-not $jdk) { Add-Result 'android-jvm' 'BLOCKED' 'run .\scripts\bootstrap-jdk17.ps1 or set JAVA_HOME to JDK 17' }
    elseif ((& (Join-Path $jdk 'bin\java.exe') -version 2>&1 | Select-Object -First 1) -notmatch '"17\.') { Add-Result 'android-jvm' 'BLOCKED' 'requires JDK 17' }
    elseif (-not $sdk -or -not (Test-Path (Join-Path $sdk 'platforms\android-34')) -or -not (Test-Path (Join-Path $sdk 'build-tools\34.0.0'))) { Add-Result 'android-jvm' 'BLOCKED' 'Android SDK Platform 34 and Build Tools 34.0.0 are required' }
    else {
        $env:JAVA_HOME = $jdk
        $env:ANDROID_SDK_ROOT = $sdk
        $env:ANDROID_HOME = $sdk
        $env:Path = "$(Join-Path $jdk 'bin');$env:Path"
        $java = Join-Path $jdk 'bin\java.exe'
        $wrapperJar = Join-Path $Root 'android_collector\gradle\wrapper\gradle-wrapper.jar'
        Invoke-Native 'android-jvm' $java @('-classpath', $wrapperJar, 'org.gradle.wrapper.GradleWrapperMain', 'testDebugUnitTest', '--no-daemon') (Join-Path $Root 'android_collector')
    }
}

if (Should-Run 'web') {
    $nodeRoot = Join-Path $Root '.tools\node-v22.18.0-win-x64'
    $npm = Join-Path $nodeRoot 'npm.cmd'
    if (-not (Test-Path -LiteralPath $npm)) { Add-Result 'web-build' 'BLOCKED' 'bundled Node 22.18.x/npm 10.x is absent' }
    elseif (-not (Test-Path -LiteralPath (Join-Path $Root 'web\node_modules'))) { Add-Result 'web-build' 'BLOCKED' 'run npm ci in web first' }
    else {
        $env:Path = "$nodeRoot;$env:Path"
        Invoke-Native 'web-build' $npm @('run', 'build') (Join-Path $Root 'web')
    }
}

Write-Output ("SUMMARY PASS={0} FAIL={1} BLOCKED={2} STRICT={3}" -f $PassCount, $FailCount, $BlockedCount, [bool]$Strict)
if ($FailCount -gt 0) { exit 1 }
if ($Strict -and $BlockedCount -gt 0) { exit 2 }
exit 0
