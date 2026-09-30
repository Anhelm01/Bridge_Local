# Руководство по развертыванию и администрированию Bridge Local

Данное руководство содержит исчерпывающие инструкции по установке, конфигурированию, обеспечению безопасности и сопровождению платформы **Bridge Local** в производственном и повседневном режимах эксплуатации на узлах под управлением **Windows** (серверный агент) и **Linux** (клиент оператора).

---

## Содержание
1. [Архитектура и системные требования](#1-архитектура-и-системные-требования)
2. [Развертывание на стороне Windows (Агент и Служба)](#2-развертывание-на-стороне-windows-агент-и-служба)
   - [2.1. Автономный исполняемый файл (PyInstaller)](#21-автономный-исполняемый-файл-pyinstaller)
   - [2.2. Автоматическая установка службы (install-service.ps1)](#22-автоматическая-установка-службы-install-serviceps1)
   - [2.3. Исключения Windows Defender](#23-исключения-windows-defender)
   - [2.4. Отключение индексирования Windows Search на каталоге Pocket](#24-отключение-индексирования-windows-search-на-каталоге-pocket)
   - [2.5. Настройка Брандмауэра Windows (Firewall)](#25-настройка-брандмауэра-windows-firewall)
   - [2.6. Контекстное меню Проводника Windows (Explorer)](#26-контекстное-меню-проводника-windows-explorer)
   - [2.7. Деинсталляция службы (uninstall-service.ps1)](#27-деинсталляция-службы-uninstall-serviceps1)
3. [Развертывание на стороне Linux (Клиент и TUI)](#3-развертывание-на-стороне-linux-клиент-и-tui)
   - [3.1. Установка пакета (uv tool / pip)](#31-установка-пакета-uv-tool--pip)
   - [3.2. Конфигурирование bridge.toml](#32-конфигурирование-bridgetoml)
   - [3.3. Использование TUI и Neofetch-дашборда](#33-использование-tui-и-neofetch-дашборда)
   - [3.4. Протокол взаимодействия для ИИ-агентов (agy_cli)](#34-протокол-взаимодействия-для-ии-агентов-agy_cli)
   - [3.5. Опциональный сервис systemd для синхронизации кармана](#35-опциональный-сервис-systemd-для-синхронизации-кармана)
4. [Разделение Dev-Mode Hyper-Logging и Release Clean Mode](#4-разделение-dev-mode-hyper-logging-и-release-clean-mode)
5. [Безопасность и сетевое экранирование](#5-безопасность-и-сетевое-экранирование)
6. [Диагностика и устранение неполадок](#6-диагностика-и-устранение-неполадок)

---

## 1. Архитектура и системные требования

Bridge Local обеспечивает защищенное взаимодействие между машинами в локальной сети (LAN) без облачных посредников, сторонних VPN или протокола SMB:
- **Транспорт:** Асинхронный TCP сокет с бинарным фреймингом (длина пакета + JSON-RPC 2.0).
- **Сетевой порт по умолчанию:** TCP `9732` (настраивается в `bridge.toml` или скриптах развертывания).
- **Аутентификация:** Pre-Shared Key (PSK) токен с контролем целостности HMAC-SHA256, временными метками и защитой от атак повторного воспроизведения (anti-replay cache).

### Системные требования

| Платформа | Роль | Минимальные требования | Рекомендуемое окружение |
|-----------|------|------------------------|-------------------------|
| **Windows** | Агент / Сервер | Windows 10/11 x64, Windows Server 2019+, PowerShell 5.1+ | Windows 11 x64, Python 3.14+ (или автономный `bridge-agent.exe`) |
| **Linux** | Клиент / Оператор | Любой современный дистрибутив (Kernel 5.15+), Python 3.14+ | Ubuntu 22.04+, Debian 12+, Arch Linux, Fedora; пакетный менеджер `uv` |

---

## 2. Развертывание на стороне Windows (Агент и Служба)

### 2.1. Автономный исполняемый файл (PyInstaller)

Для запуска агента без установки локального интерпретатора Python на Windows-машине выполняется сборка автономного бинарного файла `bridge-agent.exe`:

```powershell
# Сборка из корневого каталога проекта в среде с установленным PyInstaller:
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-agent.ps1
```

Скрипт использует спецификацию [bridge-agent.spec](file:///home/anhelm/Projects/Bridge_Local/bridge-agent.spec) и формирует единый бинарный файл `dist\bridge-agent.exe`, включающий ядро `bridge_core`, модуль агента `bridge_agent_win` и все сопутствующие библиотеки.

### 2.2. Автоматическая установка службы (install-service.ps1)

Установка службы Windows под управлением SCM (Service Control Manager) выполняется производственным скриптом [scripts/install-service.ps1](file:///home/anhelm/Projects/Bridge_Local/scripts/install-service.ps1). Скрипт запускается в консоли PowerShell от имени Администратора:

```powershell
# Стандартная установка с параметрами по умолчанию (каталог C:\BridgeLocal, порт 9732):
powershell -ExecutionPolicy Bypass -File .\scripts\install-service.ps1

# Установка с пользовательскими параметрами и преднастроенным PSK-токеном:
powershell -ExecutionPolicy Bypass -File .\scripts\install-service.ps1 `
    -InstallDir "C:\BridgeLocal" `
    -PocketDir "D:\SharedPocket" `
    -Port 9732 `
    -PskToken "секретный_токен_длиной_от_16_символов"
```

Скрипт автоматически выполняет следующий пайплайн:
1. Проверяет наличие прав Администратора (UAC Elevation).
2. Создает каталог установки (`C:\BridgeLocal`) и каталог кармана (`C:\BridgeLocal\pocket`).
3. Копирует исполняемый файл `bridge-agent.exe` в целевую папку (или настраивает вызов через `python.exe -m bridge_agent_win service-run`).
4. Формирует релизный файл конфигурации `bridge.toml` со значением `dev_mode = false` (Release Clean Mode).
5. Добавляет каталоги и процесс в доверенные исключения Windows Defender.
6. Отключает индексатор Windows Search для каталога `pocket` во избежание файловых коллизий.
7. Регистрирует правило входящих подключений Брандмауэра Windows для TCP-порта.
8. Регистрирует службу `BridgeLocalAgent` в SCM с автоматическим типом запуска (`Automatic`) и политикой самовосстановления при сбоях (`sc.exe failure reset= 86400 actions= restart/5000/restart/10000/restart/60000`).
9. Запускает службу в режиме SCM-диспетчера (`service-run`) и проверяет ее статус.

### 2.3. Исключения Windows Defender

При интенсивной передаче файлов через «Карман» и частых атомарных операциях создания/переименования файлов Defender может вызывать микрозадержки или ложные срабатывания. Скрипт `install-service.ps1` применяет следующие исключения:

```powershell
Add-MpPreference -ExclusionPath "C:\BridgeLocal"
Add-MpPreference -ExclusionPath "C:\BridgeLocal\pocket"
Add-MpPreference -ExclusionProcess "bridge-agent.exe"
```

### 2.4. Отключение индексирования Windows Search на каталоге Pocket

Служба Windows Search (`SearchIndexer.exe`) пытается захватить монопольный дескриптор на чтение каждого вновь создаваемого файла в индексируемых областях. В момент, когда Bridge Local завершает запись чанка и атомарно перемещает файл из `.filename.part` в `filename`, вмешательство индексатора приводит к ошибке `WinError 32: Процесс не может получить доступ к файлу, так как этот файл занят другим процессом`.

Для предотвращения таких конфликтов на каталог кармана устанавливается атрибут `NotContentIndexed`:

```powershell
$folder = Get-Item "C:\BridgeLocal\pocket"
$folder.Attributes = $folder.Attributes -bor [System.IO.FileAttributes]::NotContentIndexed
Get-ChildItem -Path "C:\BridgeLocal\pocket" -Recurse -Force | ForEach-Object {
    $_.Attributes = $_.Attributes -bor [System.IO.FileAttributes]::NotContentIndexed
}
```

### 2.5. Настройка Брандмауэра Windows (Firewall)

Для открытия входящего трафика на порт службы создается правило в Брандмауэре Windows:

```powershell
New-NetFirewallRule -DisplayName "Bridge Local Daemon (TCP-In)" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 9732 `
    -Action Allow `
    -Profile Any `
    -Description "Allow incoming TCP connections for Bridge Local remote agent"
```

### 2.6. Контекстное меню Проводника Windows (Explorer)

Для отправки любых файлов в «Карман» прямо из проводника Windows достаточно нажать правой кнопкой мыши на файл или папку и выбрать пункт **Отправить в Карман (Bridge Local)**:

```powershell
# Регистрация пункта в контекстном меню (текущий пользователь HKCU):
bridge-agent install-context-menu

# Экспорт .reg файла для ручного или группового применения:
bridge-agent generate-reg C:\BridgeLocal\context_menu.reg
```

### 2.7. Управление службой через CLI (bridge-agent service)

Помимо PowerShell-скриптов, агент Windows предоставляет встроенный диспетчер службы:

```powershell
# Запуск службы через pywin32 диспетчер:
bridge-agent service start

# Остановка службы:
bridge-agent service stop

# Перезапуск службы:
bridge-agent service restart

# Ручной запуск диспетчера службы SCM (используется Windows SCM):
bridge-agent service-run
```

### 2.8. Деинсталляция службы (uninstall-service.ps1)

Для корректной остановки и удаления службы используется скрипт [scripts/uninstall-service.ps1](file:///home/anhelm/Projects/Bridge_Local/scripts/uninstall-service.ps1):

```powershell
# Остановка, удаление службы из SCM, очистка Defender и правил Firewall:
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-service.ps1

# Полное удаление, включая файлы бинарников (файлы кармана сохраняются):
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-service.ps1 -DeleteFiles
```

---

## 3. Развертывание на стороне Linux (Клиент и TUI)

### 3.1. Установка пакета (uv tool / pip)

Клиентская часть устанавливается в изолированное окружение через пакетный менеджер `uv` или через стандартный `pip`:

```bash
# Вариант А: Глобальная изолированная утилита через uv tool (рекомендуется):
uv tool install .

# Вариант Б: Установка из собранного wheel-пакета:
pip install dist/bridge_local-0.1.0-py3-none-any.whl

# Вариант В: Установка из локального репозитория в режиме редактирования:
pip install -e .
```

После установки в системе становится доступна команда `bridge-cli`.

### 3.2. Конфигурирование bridge.toml

Создайте или отредактируйте файл `bridge.toml` в рабочей директории или рядом с проектом:

```toml
[node]
name = "workstation-linux"
display_name = "Linux Workstation"

[connection]
host = "192.168.1.150"       # IP-адрес или DNS-имя Windows-машины
port = 9732                  # Порт службы BridgeLocalAgent
timeout_sec = 5.0
psk_token = "секретный_токен_длиной_от_16_символов"

[pocket]
path = "./pocket"            # Локальный каталог кармана
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
console_output = true
```

### 3.3. Использование TUI и Neofetch-дашборда

Для оператора-человека предусмотрен эргономичный терминальный интерфейс:

```bash
# 1. Запуск полноэкранного Neofetch-дашборда с эмблемой BRIDGES Master:
bridge-cli welcome

# 2. Запуск интерактивной панели управления (6 режимов на [F1..F6] / Tab):
bridge-cli tui

# 3. Быстрая отправка файлов в карман Windows в один клик:
bridge-cli send document.pdf archive.zip

# 4. Отправка текстовой ссылки или заметки:
bridge-cli note send "https://github.com/project/issues/42"
```

### 3.4. Протокол взаимодействия для ИИ-агентов (agy_cli)

При вызове CLI из скриптов автоматизации или ИИ-агентов Antigravity (`agy_cli`) обязательно передается флаг `--json`:

```bash
# Выполнение PowerShell команды на Windows с чистым JSON выводом:
bridge-cli exec "Get-Process -Name BridgeLocalAgent" --json

# Проверка статуса сетевого соединения и метрик удаленного узла:
bridge-cli status --json

# Синхронизация файлов кармана:
bridge-cli pocket sync --direction both --json
```

**Стандартизированные коды завершения (Exit Codes):**
- `0` (`SUCCESS`): Операция завершена успешно.
- `1` (`GENERAL_ERROR`): Ошибка аргументов, конфигурации или внутренняя ошибка.
- `2` (`NETWORK_ERROR`): Удаленный узел недоступен, отказ в соединении.
- `3` (`AUTH_ERROR`): Несовпадение PSK-токена, ошибка HMAC или повтор пакета.
- `4` (`COMMAND_FAILED`): Удаленный процесс PowerShell завершился с ненулевым кодом.
- `5` (`TIMEOUT`): Превышен таймаут выполнения команды или ожидания RPC-ответа.

В режиме `--json` полностью подавляются ANSI-последовательности, анимации спиннеров и служебный текст, обеспечивая минимальный расход контекстных токенов LLM.

### 3.5. Опциональный сервис systemd для синхронизации кармана

Для постоянной фоновой синхронизации файлов каталога `pocket` на стороне Linux можно зарегистрировать пользовательский юнит systemd [scripts/systemd/bridge-client-sync.service](file:///home/anhelm/Projects/Bridge_Local/scripts/systemd/bridge-client-sync.service):

```bash
mkdir -p ~/.config/systemd/user/
cp scripts/systemd/bridge-client-sync.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bridge-client-sync.service
systemctl --user status bridge-client-sync.service
```

---

## 4. Разделение Dev-Mode Hyper-Logging и Release Clean Mode

Архитектура логирования Bridge Local поддерживает строгое разграничение между отладочным режимом глубокой диагностики и релизной чистой эксплуатацией:

### Режим Release Clean Mode (`dev_mode = false`)
- **Уровень по умолчанию:** `INFO`.
- **Формат:** `YYYY-MM-DD HH:MM:SS | LEVEL | Сообщение` (без микросекунд и номеров строк кода).
- **Поведение протокола:** Полностью отключены побайтовые дампы сетевых фреймов, дампы чанков файлов и подробные отладочные сообщения о блокировках.
- Консоль чистая, минимальное потребление дискового I/O и вычислительных ресурсов.

### Режим Dev-Mode Hyper-Logging (`dev_mode = true`)
- **Уровень по умолчанию:** `TRACE` (кастомный уровень детализации 5).
- **Формат:** `YYYY-MM-DD HH:MM:SS.mmm | LEVEL | logger_name:line | Сообщение`.
- **Поведение протокола:** Логируется каждый сетевой пакет с микросекундной точностью, длительность fsync, вызовы PowerShell с аргументами, хеши чанков и события детектора Watchdog.

Переключение режима осуществляется параметром в `bridge.toml`:
```toml
[logging]
level = "INFO"
dev_mode = false
```

### Аудит-логи кармана (`pocket/logs/YYYY-MM-DD.jsonl`)
Независимо от значения `dev_mode`, все выполненные удаленные команды и операции модификации данных **безусловно** фиксируются в структурированном аудит-логе кармана с контролем целостности `os.fsync`.

---

## 5. Безопасность и сетевое экранирование

1. **PSK Аутентификация:** Каждое сетевое сообщение подписывается HMAC-SHA256 хешем от секрета, временной метки (в микросекундах) и случайного одноразового значения (nonce).
2. **Защита от Replay-атак:** Агент ведет кеш использованных nonce и отклоняет запросы с рассинхронизацией системных часов более 60 секунд.
3. **Защита от Path Traversal:** При получении файлов через карман все относительные пути строго валидируются (`resolve()` и запрет выхода за пределы корневого каталога `pocket`). Попытка передачи `../` или `C:\Windows` отклоняется с ошибкой `PATH_TRAVERSAL_DETECTED`.

---

## 6. Диагностика и устранение неполадок

### 1. Проверка доступности порта с Linux:
```bash
nc -zv 192.168.1.150 9732
# или
bridge-cli status --timeout 3.0
```

### 2. Проверка состояния службы на Windows:
```powershell
Get-Service -Name BridgeLocalAgent
Get-Content C:\BridgeLocal\pocket\logs\*.jsonl -Tail 20
```

### 3. Просмотр системных событий службы:
```powershell
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='BridgeLocalAgent'} -MaxEvents 10
```

### 4. Включение временной глубокой трассировки при сбоях:
Установите в `bridge.toml` на обоих узлах:
```toml
[logging]
level = "TRACE"
dev_mode = true
```
и перезапустите службу: `Restart-Service -Name BridgeLocalAgent`.
