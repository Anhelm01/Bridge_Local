<#
.SYNOPSIS
    Установка и регистрация системной службы Bridge Local Agent в Windows SCM.

.DESCRIPTION
    Скрипт развертывания Windows-агента Bridge Local:
      1. Проверяет права Администратора (UAC elevation).
      2. Создает структуру каталогов ($InstallDir, $PocketDir).
      3. Генерирует или валидирует конфигурационный файл bridge.toml.
      4. Настраивает исключения Windows Defender (Add-MpPreference).
      5. Отключает индексирование Windows Search для каталога Pocket во избежание блокировок WinError 32.
      6. Настраивает входящее правило брандмауэра Windows (New-NetFirewallRule).
      7. Регистрирует службу в Windows SCM (New-Service) с автоматическим запуском и восстановлением.
      8. Запускает службу и проверяет статус.

.PARAMETER InstallDir
    Каталог установки службы (по умолчанию C:\BridgeLocal).

.PARAMETER PocketDir
    Каталог синхронизации Карман (по умолчанию C:\BridgeLocal\pocket).

.PARAMETER Port
    TCP-порт прослушивания (по умолчанию 9732).

.PARAMETER BinaryPath
    Путь к исполняемому файлу bridge-agent.exe или python.exe. Если не указан,
    выполняется автопоиск в $InstallDir, dist/ или в PATH.

.PARAMETER ServiceName
    Имя системной службы в SCM (по умолчанию BridgeLocalAgent).

.PARAMETER DisplayName
    Отображаемое имя службы (по умолчанию Bridge Local Windows Daemon).

.PARAMETER Description
    Описание службы.

.PARAMETER PskToken
    Pre-shared key токен для HMAC-аутентификации.

.PARAMETER SkipDefender
    Пропустить настройку исключений Windows Defender.

.PARAMETER SkipFirewall
    Пропустить настройку правил брандмауэра.

.PARAMETER SkipIndexing
    Пропустить отключение индексирования каталога pocket.

.PARAMETER NoStart
    Зарегистрировать службу, но не запускать ее немедленно.
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "C:\BridgeLocal",
    [string]$PocketDir = "C:\BridgeLocal\pocket",
    [int]$Port = 9732,
    [string]$BinaryPath = "",
    [string]$ServiceName = "BridgeLocalAgent",
    [string]$DisplayName = "Bridge Local Windows Daemon",
    [string]$Description = "Cross-platform Linux-to-Windows remote management and file synchronization service",
    [string]$PskToken = "",
    [switch]$SkipDefender,
    [switch]$SkipFirewall,
    [switch]$SkipIndexing,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host "  Bridge Local Windows Agent — Установка службы SCM"
Write-Host "============================================================"

# 1. Проверка прав Администратора
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "[FAIL] Скрипт установки требует повышенных прав Администратора. Запустите PowerShell от имени Администратора."
    exit 1
}
Write-Host "[OK] Права Администратора подтверждены."

# 2. Создание каталогов
try {
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Write-Host "[OK] Создан каталог установки: $InstallDir"
    }
    if (-not (Test-Path $PocketDir)) {
        New-Item -ItemType Directory -Path $PocketDir -Force | Out-Null
        Write-Host "[OK] Создан каталог кармана: $PocketDir"
    }
    $logsDir = Join-Path $PocketDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
} catch {
    Write-Error "[FAIL] Ошибка создания каталогов: $_"
    exit 1
}

# 3. Определение пути к бинарнику / скрипту
$resolvedBinPath = ""
$targetExeName = "bridge-agent.exe"

if ($BinaryPath -ne "") {
    $resolvedBinPath = $BinaryPath
} else {
    $candidates = @(
        (Join-Path $InstallDir "bridge-agent.exe"),
        (Join-Path $PSScriptRoot "bridge-agent.exe"),
        (Join-Path (Join-Path $PSScriptRoot "..") "dist\bridge-agent.exe"),
        (Join-Path (Get-Location) "dist\bridge-agent.exe")
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            $resolvedBinPath = (Resolve-Path $cand).Path
            break
        }
    }
}

if ($resolvedBinPath -eq "") {
    # Поиск команды bridge-agent в PATH
    $cmd = Get-Command "bridge-agent" -ErrorAction SilentlyContinue
    if ($cmd) {
        $resolvedBinPath = $cmd.Source
    }
}

# Формирование командной строки запуска службы
$serviceBinCommand = ""
if ($resolvedBinPath -ne "" -and (Test-Path $resolvedBinPath)) {
    Write-Host "[OK] Найден бинарный файл агента: $resolvedBinPath"
    $targetExeName = [System.IO.Path]::GetFileName($resolvedBinPath)
    # Если файл находится вне InstallDir, копируем его туда при необходимости
    $destExe = Join-Path $InstallDir $targetExeName
    if (-not (Test-Path $destExe) -and ($resolvedBinPath -ne $destExe)) {
        Copy-Item -Path $resolvedBinPath -Destination $destExe -Force
        Write-Host "[OK] Бинарный файл скопирован в $destExe"
        $resolvedBinPath = $destExe
    }
    $serviceBinCommand = "`"$resolvedBinPath`" service-run"
} else {
    # Fallback: запуск через python
    $pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = $pythonCmd.Source
        $targetExeName = [System.IO.Path]::GetFileName($pythonExe)
        $serviceBinCommand = "`"$pythonExe`" -m bridge_agent_win service-run"
        Write-Host "[WARN] Бинарный bridge-agent.exe не найден. Используется Python: $serviceBinCommand"
    } else {
        Write-Error "[FAIL] Не удалось найти bridge-agent.exe или python.exe. Укажите -BinaryPath."
        exit 1
    }
}

# 4. Проверка и генерация bridge.toml
$configPath = Join-Path $InstallDir "bridge.toml"
if (-not (Test-Path $configPath)) {
    Write-Host "[SERVICE] Создание базовой конфигурации $configPath..."
    $tomlContent = @"
[node]
name = "$env:COMPUTERNAME"
display_name = "Windows Rig ($env:COMPUTERNAME)"

[connection]
host = "0.0.0.0"
port = $Port
timeout_sec = 5.0
psk_token = "$PskToken"

[pocket]
path = "$($PocketDir -replace '\\', '\\')"
logs_subdir = "logs"
sync_watch = true
max_chunk_size = 65536
log_max_days = 30

[exec]
default_timeout_sec = 30
run_as_admin = true
force_utf8 = true

[logging]
level = "INFO"
dev_mode = false
console_output = false
file_output = "$($InstallDir -replace '\\', '\\')\\agent.log"
"@
    Set-Content -Path $configPath -Value $tomlContent -Encoding UTF8
    Write-Host "[OK] Конфигурация $configPath создана (режим Release clean mode)."
} else {
    Write-Host "[OK] Использована существующая конфигурация: $configPath"
}

# 5. Исключения Windows Defender
if (-not $SkipDefender) {
    Write-Host "[SERVICE] Настройка исключений Windows Defender..."
    try {
        Add-MpPreference -ExclusionPath $PocketDir -ErrorAction SilentlyContinue
        Add-MpPreference -ExclusionPath $InstallDir -ErrorAction SilentlyContinue
        if ($targetExeName -ne "") {
            Add-MpPreference -ExclusionProcess $targetExeName -ErrorAction SilentlyContinue
        }
        Write-Host "[OK] Исключения Windows Defender применены: $PocketDir, $InstallDir, $targetExeName"
    } catch {
        Write-Warning "[WARN] Не удалось настроить исключения Windows Defender: $_"
    }
}

# 6. Отключение индексирования Windows Search на каталоге Pocket
if (-not $SkipIndexing) {
    Write-Host "[SERVICE] Отключение индексирования Windows Search для $PocketDir..."
    try {
        if (Test-Path $PocketDir) {
            $folderItem = Get-Item $PocketDir
            $folderItem.Attributes = $folderItem.Attributes -bor [System.IO.FileAttributes]::NotContentIndexed
            Get-ChildItem -Path $PocketDir -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
                $_.Attributes = $_.Attributes -bor [System.IO.FileAttributes]::NotContentIndexed
            }
            Write-Host "[OK] Атрибут NotContentIndexed успешно установлен для $PocketDir."
        }
    } catch {
        Write-Warning "[WARN] Не удалось отключить индексирование Windows Search: $_"
    }
}

# 7. Правило брандмауэра Windows
if (-not $SkipFirewall) {
    Write-Host "[SERVICE] Настройка правила брандмауэра для порта $Port TCP..."
    try {
        $ruleName = "Bridge Local Daemon (TCP-In)"
        $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $existingRule) {
            New-NetFirewallRule -DisplayName $ruleName `
                -Direction Inbound `
                -Protocol TCP `
                -LocalPort $Port `
                -Action Allow `
                -Profile Any `
                -Description "Allow incoming connections for Bridge Local Windows Agent" `
                -ErrorAction Stop | Out-Null
            Write-Host "[OK] Правило брандмауэра '$ruleName' успешно создано."
        } else {
            Write-Host "[OK] Правило брандмауэра '$ruleName' уже существует."
        }
    } catch {
        Write-Warning "[WARN] Не удалось настроить правило брандмауэра: $_"
    }
}

# 8. Регистрация службы в Windows SCM
Write-Host "[SERVICE] Регистрация службы $ServiceName в Windows Service Control Manager..."
try {
    $existingSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingSvc) {
        Write-Host "[SERVICE] Обнаружена существующая служба $ServiceName, остановка..."
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        # Удаляем старую регистрацию
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
    }

    # Создание службы через New-Service
    New-Service -Name $ServiceName `
        -BinaryPathName $serviceBinCommand `
        -DisplayName $DisplayName `
        -Description $Description `
        -StartupType Automatic `
        -ErrorAction Stop | Out-Null

    # Настройка политики автоматического перезапуска при сбоях (Recovery actions)
    # Перезапуск через 5 сек, 10 сек, 60 сек; сброс счетчика через 24 часа (86400 сек)
    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/60000 | Out-Null

    Write-Host "[OK] Служба $ServiceName успешно зарегистрирована в SCM с автозапуском."
} catch {
    Write-Error "[FAIL] Ошибка регистрации службы в SCM: $_"
    exit 1
}

# 9. Запуск службы
if (-not $NoStart) {
    Write-Host "[SERVICE] Запуск службы $ServiceName..."
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 1
        $status = (Get-Service -Name $ServiceName).Status
        Write-Host "[OK] Служба $ServiceName успешно запущена. Текущий статус: $status"
    } catch {
        Write-Error "[FAIL] Не удалось запустить службу $ServiceName: $_"
        exit 1
    }
}

Write-Host "============================================================"
Write-Host "  [OK] Развертывание Bridge Local Windows Agent завершено."
Write-Host "  Каталог:  $InstallDir"
Write-Host "  Карман:   $PocketDir"
Write-Host "  Служба:   $ServiceName ($DisplayName)"
Write-Host "============================================================"
