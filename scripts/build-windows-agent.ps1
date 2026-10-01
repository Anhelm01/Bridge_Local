<#
.SYNOPSIS
    Сборка автономного исполняемого файла Windows-агента (bridge-agent.exe) с помощью PyInstaller.

.DESCRIPTION
    Скрипт выполняет:
      1. Проверку окружения Python и наличия PyInstaller.
      2. Установку зависимостей проекта и PyInstaller при их отсутствии.
      3. Сборку bridge-agent.exe согласно спецификации bridge-agent.spec.
      4. Проверку собранного бинарного файла и расчет контрольной суммы SHA-256.

.PARAMETER Clean
    Выполнить предварительную очистку каталогов build/ и dist/.
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
Write-Host "  Сборка автономного агента Bridge Local (bridge-agent.exe)"

Write-Host "============================================================"

# Определение корневого каталога репозитория
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$specFile = Join-Path $repoRoot "bridge-agent.spec"
if (-not (Test-Path $specFile)) {
    Write-Error "[FAIL] Файл спецификации PyInstaller не найден: $specFile"
    exit 1
}

# Очистка артефактов предыдущей сборки
if ($Clean) {
    Write-Host "[BUILD] Очистка предыдущих артефактов сборки..."
    $buildDir = Join-Path $repoRoot "build"
    $distDir = Join-Path $repoRoot "dist"
    if (Test-Path $buildDir) { Remove-Item -Path $buildDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path (Join-Path $distDir "bridge-agent.exe")) {
        Remove-Item -Path (Join-Path $distDir "bridge-agent.exe") -Force -ErrorAction SilentlyContinue
    }
}

# Проверка наличия pyinstaller
$pyinstallerCmd = Get-Command "pyinstaller" -ErrorAction SilentlyContinue
if (-not $pyinstallerCmd) {
    Write-Host "[BUILD] PyInstaller не найден в PATH. Попытка запуска через uv / python..."
    $uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($uvCmd) {
        Write-Host "[BUILD] Запуск через uv run pyinstaller..."
        & uv run pyinstaller --clean $specFile
    } else {
        Write-Host "[BUILD] Запуск через python -m PyInstaller..."
        & python -m PyInstaller --clean $specFile
    }
} else {
    Write-Host "[BUILD] Запуск PyInstaller: pyinstaller --clean $specFile"
    & pyinstaller --clean $specFile
}

$outputExe = Join-Path $repoRoot "dist\bridge-agent.exe"
if (Test-Path $outputExe) {
    $fileInfo = Get-Item $outputExe
    $sizeMb = [Math]::Round($fileInfo.Length / 1MB, 2)
    $hash = (Get-FileHash -Path $outputExe -Algorithm SHA256).Hash

    Write-Host "============================================================"
    Write-Host "  [OK] Сборка успешно завершена!"
    Write-Host "  Бинарник:  $outputExe"
    Write-Host "  Размер:    $sizeMb MB ($($fileInfo.Length) байт)"
    Write-Host "  SHA-256:   $hash"
    Write-Host "============================================================"
} else {
    Write-Error "[FAIL] Файл bridge-agent.exe не был создан в каталоге dist."
    exit 1
}
