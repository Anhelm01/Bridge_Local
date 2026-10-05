<#
.SYNOPSIS
    Сборка релизного пакета Bridge Local для Windows (BridgeLocal-Windows-x64.zip).
#>
[CmdletBinding()]
param(
    [string]$DistPkgName = "BridgeLocal-Windows-x64"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$distDir = Join-Path $repoRoot "dist"
$targetDir = Join-Path $distDir $DistPkgName
$exePath = Join-Path $distDir "bridge-agent.exe"

if (-not (Test-Path $exePath)) {
    Write-Error "[FAIL] $exePath не найден! Сначала выполните сборку bridge-agent.exe."
    exit 1
}

Write-Host "[PACKAGE] Формирование структуры дистрибутива в $targetDir..."
if (Test-Path $targetDir) {
    Remove-Item -Path $targetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

# 1. Бинарный файл
Copy-Item $exePath -Destination $targetDir

# 2. Файлы управления (.bat)
$winScriptsDir = Join-Path $repoRoot "scripts\windows"
Get-ChildItem -Path $winScriptsDir -Filter "*.bat" | ForEach-Object {
    Copy-Item $_.FullName -Destination $targetDir
}

# 3. Конфигурация bridge.toml (шаблон для Windows)
$tomlTemplate = Join-Path $winScriptsDir "bridge.win.toml"
if (Test-Path $tomlTemplate) {
    Copy-Item $tomlTemplate -Destination (Join-Path $targetDir "bridge.toml")
} else {
    Copy-Item (Join-Path $repoRoot "bridge.toml") -Destination (Join-Path $targetDir "bridge.toml")
}

# 4. Документация пользователя
$manualSource = Join-Path $repoRoot "docs\05_BINARY_GUIDE_WINDOWS.md"
$readmeRoot = Join-Path $repoRoot "README.md"
if (Test-Path $manualSource) {
    Copy-Item $manualSource -Destination (Join-Path $targetDir "README.md")
} elseif (Test-Path $readmeRoot) {
    Copy-Item $readmeRoot -Destination (Join-Path $targetDir "README.md")
}

# 5. Каталог кармана
New-Item -ItemType Directory -Path (Join-Path $targetDir "pocket") -Force | Out-Null

# 6. Упаковка в ZIP-архив
$zipPath = Join-Path $distDir "$DistPkgName.zip"
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}
Compress-Archive -Path "$targetDir\*" -DestinationPath $zipPath -Force

Write-Host "============================================================"
Write-Host "  [OK] Пакет успешно собран: $zipPath"
Write-Host "============================================================"
