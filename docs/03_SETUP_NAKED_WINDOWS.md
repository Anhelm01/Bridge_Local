# 03_SETUP_NAKED_WINDOWS: Setup from Naked System on Windows

Полное пошаговое руководство по развертыванию, конфигурации, локальной сборке, оперированию и взаимодействию с платформой **Bridge Local** на чистой операционной системе Windows (10 или 11) непосредственно из исходного кода Python (без использования готового бинарного файла `bridge-agent.exe`).

---

## 1. Системные требования и предварительная подготовка

### 1.1 Поддерживаемые ОС
- Windows 10 (x64) сборка 1909 или новее
- Windows 11 (x64) всех ревизий
- Windows Server 2022 / 2025

### 1.2 Необходимые инструменты
Для развертывания из исходного кода требуются:
1. **Python**: версия `3.11` или `3.12` (x64).
2. **Git**: для клонирования и обновления репозитория.
3. **PowerShell**: версия 5.1 (встроена в Windows) или PowerShell 7+.

### 1.3 Установка компонентов через `winget` (Быстрая установка)
Откройте PowerShell от имени Администратора (Win+X -> Терминал / PowerShell Администратор) и выполните:

```powershell
# Установка Python 3.12 и Git
winget install --id Python.Python.3.12 --exact --source winget
winget install --id Git.Git --exact --source winget
```

> [!IMPORTANT]
> При ручной установке Python с официального сайта python.org **обязательно** установите флажок:
> ☑ **"Add python.exe to PATH"** на первом шаге установщика.

### 1.4 Разрешение выполнения локальных PowerShell-скриптов
По умолчанию Windows блокирует запуск сторонних скриптов `.ps1`. Разрешите запуск скриптов для текущего пользователя:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
```

---

## 2. Клонирование репозитория

Откройте стандартную консоль PowerShell (или CMD) и перейдите в каталог для установки (например, `D:\progs` или `C:\Projects`):

```powershell
Set-Location D:\progs
git clone https://github.com/Anhelm01/Bridge_Local.git
Set-Location D:\progs\Bridge_Local
```

Структура каталога проекта:
```text
Bridge_Local/
├── bridge.toml             # Главный конфигурационный файл
├── start.bat               # Консоль управления Windows (CMD / PowerShell)
├── run_tray.bat            # Запуск значка в системном трее
├── bridge-agent.spec       # Спецификация PyInstaller для сборки .exe
├── pyproject.toml          # Манифест пакета и зависимостей
├── src/
│   ├── bridge_core/        # Ядро сетевого протокола, криптография, хранилище
│   └── bridge_agent_win/   # Исходный код демона Windows (служба, трей, меню)
├── pocket/                 # Общий каталог Карман
│   └── .notes/             # Локальная база заметок SQLite
└── scripts/
    └── build-windows-agent.ps1  # Скрипт сборки автономного бинарника
```

---

## 3. Настройка виртуального окружения Python

### 3.1 Создание и активация `venv`
В корне проекта выполните:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(В командной строке CMD для активации используйте: `.venv\Scripts\activate.bat`)*

В начале строки появится префикс `(.venv)`.

### 3.2 Установка зависимостей Windows-агента
Обновите пакетные менеджеры и установите проект в режиме разработки (`editable`):

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[agent,dev]"
```

### 3.3 Инициализация системных библиотек `pywin32`
Для интеграции с Windows Service Control Manager (SCM), Проводником (Explorer) и системным треем критически важна правильная регистрация компонентов `pywin32`. Выполните:

```powershell
python .venv\Scripts\pywin32_postinstall.py -install
```

### 3.4 Проверка окружения
Убедитесь, что все модули импортируются без ошибок:

```powershell
python -c "import bridge_core, bridge_agent_win, win32service, win32gui; print('[OK] Windows Agent environment successfully verified')"
```
*Ожидаемый вывод:*
```text
[OK] Windows Agent environment successfully verified
```

---

## 4. Конфигурация (`bridge.toml`)

Откройте файл `bridge.toml` в текстовом редакторе (Notepad, VS Code):

```powershell
notepad bridge.toml
```

### Эталонный конфиг для Windows-агента:
```toml
# Переключатель режима разработчика: true (полная трассировка) / false (тихий режим)
dev_mode = false

[node]
name = "win-pc"
role = "agent"
listen_host = "0.0.0.0"       # Слушать все локальные интерфейсы
listen_port = 9732            # Стандартный входящий порт Bridge Local
auth_token = "0123456789abcdef0123456789abcdef"

[network]
heartbeat_interval_sec = 10.0
connect_timeout_sec = 5.0
request_timeout_sec = 30.0

[network.nodes.linux-workstation]
host = "192.168.1.50"         # IP-адрес вашей Linux-машины
port = 9733
role = "client"

[pocket]
storage_path = "pocket"
sync_interval_sec = 3.0
max_file_size_mb = 500
conflict_strategy = "newer_wins"

[notes]
storage_path = "pocket/.notes"
max_history_entries = 1000
poll_interval_sec = 5.0

[security]
psk_secret = "0123456789abcdef0123456789abcdef"
allow_unauthenticated = false
```

Создайте рабочий каталог Кармана:
```powershell
New-Item -ItemType Directory -Path "pocket\.notes" -Force
```

---

## 5. Настройка Брандмауэра Windows (Firewall)

Чтобы агент мог принимать сетевые пакеты от Linux-клиента на порт `9732`, откройте порт в Windows Defender Firewall.

Запустите PowerShell от имени **Администратора**:

```powershell
# 1. Удаление старого правила (при наличии) и добавление разрешающего правила для порта 9732 TCP
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)"
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any

# 2. Установка сетевого профиля как "Частная сеть" (Private) для предотвращения блокировок
Set-NetConnectionProfile -InterfaceAlias 'Ethernet*','Wi-Fi*' -NetworkCategory Private -ErrorAction SilentlyContinue
```

*Проверка созданного правила:*
```powershell
netsh advfirewall firewall show rule name="Bridge Local Daemon (TCP-In)"
```

---

## 6. Запуск и оперирование из исходного кода

При работе из исходного кода все действия выполняются через запуск модуля `bridge_agent_win`.

### 6.1 Запуск интерактивной консоли (Live Monitor)
Основной режим работы для оператора с живым экраном мониторинга:

```powershell
python -m bridge_agent_win run
```

*Интерфейс консоли оператора:*
```text
==============================================================================
   BRIDGE LOCAL - WINDOWS AGENT CONSOLE (LIVE MONITOR)
==============================================================================
 [NODE]      win-pc (Windows 10/11)
 [NETWORK]   TCP Server listening on 0.0.0.0:9732
 [POCKET]    D:\progs\Bridge_Local\pocket
 [STATUS]    READY - Waiting for incoming Linux client requests...
==============================================================================
[COMMANDS]: help | status | notes | pocket | clip | clear | exit
bridge-agent> 
```

#### Встроенные команды консоли:
- **`status`**: отображение текущего состояния сокета, времени работы (uptime), загрузки ОЗУ и количества файлов в Кармане.
- **`notes`**: вывод последних полученных записок и ссылок от Linux.
- **`pocket`**: вывод списка локальных файлов в каталоге `pocket/`.
- **`clip`** (или **`drop`**): моментальное извлечение содержимого системного буфера обмена Windows (файлы, изображения, скопированный текст) и перемещение в Карман.
- **`clear`**: очистка экрана консоли с повторным выводом информационного баннера.
- **`exit`**: корректная остановка сервера и завершение работы.

### 6.2 Интеграция с контекстным меню Проводника (Explorer)
Вы можете зарегистрировать пункт меню «Отправить в Карман (Bridge Local)» по правому клику мыши на любой файл или папку:

```powershell
# Регистрация меню в реестре HKCU (не требует прав Администратора)
python -m bridge_agent_win install-context-menu
```
*Удаление пункта меню:*
```powershell
python -m bridge_agent_win uninstall-context-menu
```

### 6.3 Отправка файлов и буфера обмена в Карман из консоли

#### Отправка конкретного файла:
```powershell
python -m bridge_agent_win drop "C:\Users\user\Desktop\document.pdf"
```

#### Отправка содержимого буфера обмена:
Если вы скопировали файл в Проводнике (Ctrl+C), ссылку в браузере или текст, выполните:
```powershell
python -m bridge_agent_win drop --clipboard
```
*Пример вывода:*
```text
[OK] Из буфера обмена скопировано в Карман: photo_2026-10-03.jpg
```

### 6.4 Запуск значка в системном трее Windows
Для работы значка в правом нижнем углу экрана (возле часов):

```powershell
python -m bridge_agent_win tray
```
В трее появится значок Bridge Local. Правый клик открывает меню:
- **Открыть Карман** — открывает папку `pocket/` в Проводнике.
- **Вставить из буфера в Карман** — мгновенно сохраняет скопированный объект.
- **Статус службы** — проверка состояния демона.
- **Выход**.

---

## 7. Универсальная консоль `start.bat` в режиме исходного кода

В корне репозитория расположен файл `start.bat`. При запуске из исходного кода он автоматически обнаруживает `.venv` и позволяет выполнять все операции в один клик:

```cmd
start.bat
```

- Выберите **`[1] QUICK START`** — скрипт сам проверит брандмауэр, зарегистрирует контекстное меню и откроет Live Monitor.
- Выберите **`[12] Drop Clipboard to Pocket`** — сохранит буфер обмена в Карман.

---

## 8. Компиляция в автономный бинарный файл (`bridge-agent.exe`)

Когда вы закончили модификацию исходного кода и хотите получить полностью автономный `.exe` файл:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-windows-agent.ps1
```

Скрипт автоматически:
1. Проверит наличие PyInstaller (установит при необходимости).
2. Зарегистрирует компоненты `pywin32`.
3. Соберет файл `dist\bridge-agent.exe` по спецификации `bridge-agent.spec`.
4. Скопирует актуальный `bridge.toml` в каталог `dist\`.
5. Рассчитает размер и контрольную сумму SHA-256 собранного бинарника.

> [!TIP]
> Если на компьютере уже запущен старый агент `dist\bridge-agent.exe`, перед пересборкой переименуйте его во временное имя:
> ```powershell
> Move-Item dist\bridge-agent.exe dist\bridge-agent.old.exe -Force
> ```
> Это позволит PyInstaller записать новый файл без конфликтов блокировки NTFS.

---

## 9. Устранение неполадок (Troubleshooting)

### 9.1 Ошибка «Порт 9732 уже используется» (`WinError 10048`)
Если при запуске `python -m bridge_agent_win run` выводится сообщение о занятом порте:
1. Найдите процесс, занимающий порт:
   ```powershell
   Get-NetTCPConnection -LocalPort 9732 | Select-Object OwningProcess
   ```
2. Остановите конфликтующий процесс:
   ```powershell
   Stop-Process -Id <PID> -Force
   ```
   Либо, если агент был ранее установлен как служба Windows:
   ```powershell
   net stop BridgeLocalAgent
   ```

### 9.2 Ошибки кодировки или кракозябры в терминале
Bridge Local строго работает в стандарте UTF-8. Если вывод PowerShell искажается:
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
chcp 65001
```

### 9.3 Ошибка `ImportError: DLL load failed while importing win32api`
Указывает на незавершённую регистрацию `pywin32`. Выполните в активированном `.venv`:
```powershell
python .venv\Scripts\pywin32_postinstall.py -install
```
