<#
.SYNOPSIS
    Build standalone Windows Agent (bridge-agent.exe) via PyInstaller.
#>

[CmdletBinding()]
param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

Write-Host "============================================================"
Write-Host "  Building Standalone Bridge Local Agent (bridge-agent.exe)"
Write-Host "============================================================"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$specFile = Join-Path $repoRoot "bridge-agent.spec"
if (-not (Test-Path $specFile)) {
    Write-Error "[FAIL] PyInstaller spec file not found: $specFile"
    exit 1
}

if ($Clean) {
    Write-Host "[BUILD] Cleaning previous build artifacts..."
    $buildDir = Join-Path $repoRoot "build"
    $distDir = Join-Path $repoRoot "dist"
    if (Test-Path $buildDir) { Remove-Item -Path $buildDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path (Join-Path $distDir "bridge-agent.exe")) {
        Remove-Item -Path (Join-Path $distDir "bridge-agent.exe") -Force -ErrorAction SilentlyContinue
    }
}

try {
    $postinstallCmd = Get-Command "pywin32_postinstall.py" -ErrorAction SilentlyContinue
    if ($postinstallCmd) {
        Write-Host "[BUILD] Registering pywin32 system components..."
        python $postinstallCmd.Source -install -silent 2>$null
    }
} catch {}

$pyinstallerCmd = Get-Command "pyinstaller" -ErrorAction SilentlyContinue
if (-not $pyinstallerCmd) {
    Write-Host "[BUILD] PyInstaller not in PATH. Running via uv run..."
    & uv run pyinstaller --clean $specFile
} else {
    Write-Host "[BUILD] Running PyInstaller: pyinstaller --clean $specFile"
    & pyinstaller --clean $specFile
}

$outputExe = Join-Path $repoRoot "dist\bridge-agent.exe"
$outputTray = Join-Path $repoRoot "dist\bridge-tray.exe"
if (Test-Path $outputExe) {
    Copy-Item (Join-Path $repoRoot "bridge.toml") -Destination (Join-Path $repoRoot "dist\bridge.toml") -Force -ErrorAction SilentlyContinue
    $fileInfo = Get-Item $outputExe
    $sizeMb = [Math]::Round($fileInfo.Length / 1MB, 2)
    $hash = (Get-FileHash -Path $outputExe -Algorithm SHA256).Hash

    Write-Host "============================================================"
    Write-Host "  [OK] Build completed successfully!"
    Write-Host "  Agent (Console):   $outputExe ($sizeMb MB)"
    Write-Host "  SHA-256:           $hash"
    if (Test-Path $outputTray) {
        $trayInfo = Get-Item $outputTray
        $trayMb = [Math]::Round($trayInfo.Length / 1MB, 2)
        Write-Host "  Tray (NoConsole):  $outputTray ($trayMb MB)"
    }
    Write-Host "============================================================"
} else {
    Write-Error "[FAIL] File bridge-agent.exe was not created in dist directory."
    exit 1
}
