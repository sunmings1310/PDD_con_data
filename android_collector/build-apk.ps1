$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

if (-not $env:JAVA_HOME) {
    throw 'JAVA_HOME is required and must point to JDK 17.'
}
if (-not (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
    throw "JDK not found under JAVA_HOME: $env:JAVA_HOME"
}

$sdkRoot = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { $env:ANDROID_HOME }
if (-not $sdkRoot) {
    throw 'ANDROID_SDK_ROOT (or ANDROID_HOME) is required.'
}
if (-not (Test-Path (Join-Path $sdkRoot 'platforms\android-34'))) {
    throw "Android SDK Platform 34 not found under: $sdkRoot"
}

$javaVersion = & (Join-Path $env:JAVA_HOME 'bin\java.exe') -version 2>&1
if (($javaVersion | Out-String) -notmatch 'version "17\.') {
    throw "JDK 17 is required. Detected: $($javaVersion | Select-Object -First 1)"
}

$localProperties = Join-Path $root 'local.properties'
if (-not (Test-Path $localProperties)) {
    $sdkProp = 'sdk.dir=' + ($sdkRoot.Replace('\', '\\').Replace(':', '\:'))
    Set-Content -Path $localProperties -Value $sdkProp -Encoding ASCII
}

Write-Host ">> JAVA_HOME=$env:JAVA_HOME"
Write-Host ">> ANDROID_SDK_ROOT=$sdkRoot"
Write-Host '>> Building debug APK with the repository Gradle Wrapper...'

Push-Location $root
try {
    & .\gradlew.bat assembleDebug testDebugUnitTest --no-daemon
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed with exit code $LASTEXITCODE" }

    $apkSrc = Join-Path $root 'app\build\outputs\apk\debug\app-debug.apk'
    if (-not (Test-Path $apkSrc)) { throw "APK not found: $apkSrc" }

    $distDir = Join-Path $root 'dist'
    New-Item -ItemType Directory -Force -Path $distDir | Out-Null
    $apkDst = Join-Path $distDir 'PddCollector-debug.apk'
    Copy-Item $apkSrc $apkDst -Force
    Write-Host ">> Build complete: $apkDst"
} finally {
    Pop-Location
}
