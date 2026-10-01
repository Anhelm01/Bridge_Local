<#
.SYNOPSIS
    Корректная остановка и удаление службы Bridge Local Agent из Windows SCM.

.DESCRIPTION
    Скрипт деинсталляции Windows-агента Bridge Local:
      1. Проверяет права Администратора.
      2. Корректно останавливает системную службу BridgeLocalAgent (Stop-Service).
      3. Удаляет регистрацию службы из SCM (sc.exe delete).
      4. Удаляет исключения из Windows Defender (Remove-MpPreference).
      5. Удаляет правило входящих соединений брандмауэра (Remove-NetFirewallRule).
      6. Опционально очищает файлы установки (-DeleteFiles).

.PARAMETER ServiceName
    Имя системной службы в SCM (по умолчанию BridgeLocalAgent).

.PARAMETER InstallDir
    Каталог установки (по умолчанию C:\BridgeLocal).

.PARAMETER PocketDir
    Каталог кармана (по умолчанию C:\BridgeLocal\pocket).

.PARAMETER CleanDefender
    Удалить исключения Windows Defender (по умолчанию $true).

.PARAMETER CleanFirewall
    Удалить правило брандмауэра (по умолчанию $true).

.PARAMETER DeleteFiles
    Удалить файлы каталога установки (файлы кармана не удаляются во избежание потери данных).
#>

[CmdletBinding()]
param(
    [string]$ServiceName = "BridgeLocalAgent",
    [string]$InstallDir = "C:\BridgeLocal",
    [string]$PocketDir = "C:\BridgeLocal\pocket",
    [bool]$CleanDefender = $true,
    [bool]$CleanFirewall = $true,
    [bool]$DeleteFiles = $false
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host "  Bridge Local Windows Agent — Деинсталляция службы SCM"
Write-Host "============================================================"

# 1. Проверка прав Администратора
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "[FAIL] Скрипт удаления требует повышенных прав Администратора. Запустите PowerShell от имени Администратора."
    exit 1
}
Write-Host "[OK] Права Администратора подтверждены."

# 2. Остановка и удаление службы SCM
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "[SERVICE] Остановка службы $ServiceName..."
    if ($svc.Status -ne "Stopped") {
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            $timeoutSec = 15
            while ((Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -ne "Stopped" -and $timeoutSec -gt 0) {
                Start-Sleep -Seconds 1
                $timeoutSec--
            }
            Write-Host "[OK] Служба $ServiceName остановлена."
        } catch {
            Write-Warning "[WARN] Не удалось штатно остановить службу: $_"
        }
    }

    Write-Host "[SERVICE] Удаление службы $ServiceName из реестра SCM..."
    try {
        sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
        Write-Host "[OK] Служба $ServiceName успешно удалена из SCM."
    } catch {
        Write-Error "[FAIL] Ошибка удаления службы из SCM: $_"
    }
} else {
    Write-Host "[WARN] Служба $ServiceName не обнаружена в реестре SCM."
}

# 3. Очистка исключений Windows Defender
if ($CleanDefender) {
    Write-Host "[SERVICE] Очистка исключений Windows Defender..."
    try {
        Remove-MpPreference -ExclusionPath $PocketDir -ErrorAction SilentlyContinue
        Remove-MpPreference -ExclusionPath $InstallDir -ErrorAction SilentlyContinue
        Remove-MpPreference -ExclusionProcess "bridge-agent.exe" -ErrorAction SilentlyContinue
        Remove-MpPreference -ExclusionProcess "python.exe" -ErrorAction SilentlyContinue
        Write-Host "[OK] Исключения Windows Defender очищены."
    } catch {
        Write-Warning "[WARN] Не удалось удалить некоторые исключения Defender: $_"
    }
}

# 4. Очистка правила брандмауэра
if ($CleanFirewall) {
    Write-Host "[SERVICE] Очистка правил брандмауэра Windows..."
    try {
        $ruleName = "Bridge Local Daemon (TCP-In)"
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if ($existing) {
            Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
            Write-Host "[OK] Правило брандмауэра '$ruleName' удалено."
        } else {
            Write-Host "[OK] Правило брандмауэра не найдено (уже удалено)."
        }
    } catch {
        Write-Warning "[WARN] Не удалось удалить правило брандмауэра: $_"
    }
}

# 5. Опциональное удаление исполняемых файлов
if ($DeleteFiles) {
    Write-Host "[SERVICE] Удаление файлов установки из $InstallDir..."
    try {
        $exeFile = Join-Path $InstallDir "bridge-agent.exe"
        if (Test-Path $exeFile) {
            Remove-Item -Path $exeFile -Force -ErrorAction SilentlyContinue
        }
        $logFile = Join-Path $InstallDir "agent.log"
        if (Test-Path $logFile) {
            Remove-Item -Path $logFile -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[OK] Бинарные файлы и логи службы удалены. (Файлы кармана в $PocketDir сохранены)."
    } catch {
        Write-Warning "[WARN] Ошибка удаления файлов: $_"
    }
}

Write-Host "============================================================"
Write-Host "  [OK] Служба Bridge Local Windows Agent полностью деинсталлирована."
Write-Host "============================================================"
