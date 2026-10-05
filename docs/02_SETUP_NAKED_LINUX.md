# 02_SETUP_NAKED_LINUX: Setup from Naked System on Linux

Полное пошаговое руководство по развертыванию, конфигурации, оперированию и взаимодействию с платформой **Bridge Local** на чистой операционной системе Linux из исходного кода Python (без использования скомпилированных бинарных файлов).

---

## 1. Системные требования и зависимости

Bridge Local протестирован и поддерживается на следующих дистрибутивах:
- Arch Linux / Manjaro
- Ubuntu 22.04 LTS / 24.04 LTS, Debian 12
- Fedora 39/40, Rocky Linux / AlmaLinux 9

### 1.1 Необходимые системные пакеты
- **Python**: версия `3.11` или `3.12`
- **Git**: для клонирования репозитория
- **Утилиты**: `curl`, `tar`, `iproute2`, `netcat` (или `socat`)

### 1.2 Команды установки пакетов по дистрибутивам

#### Arch Linux:
```bash
sudo pacman -Syu --needed python python-pip python-virtualenv git curl openbsd-netcat
```

#### Ubuntu / Debian:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git curl netcat-openbsd
```

#### Fedora / RHEL / Rocky Linux:
```bash
sudo dnf install -y python3 python3-pip python3-virtualenv git curl nc
```

---

## 2. Клонирование репозитория

Склонируйте исходный код проекта в рабочую директорию:

```bash
git clone https://github.com/Anhelm01/Bridge_Local.git
cd Bridge_Local
```

Структура каталога репозитория:
```text
Bridge_Local/
├── bridge.toml             # Центральный конфигурационный файл
├── start.sh                # Консоль управления Linux (интерактивное меню)
├── pyproject.toml          # Конфигурация пакетов и зависимостей
├── src/
│   ├── bridge_core/        # Сетевой протокол, криптография, хранилище
│   ├── bridge_client_linux/# CLI, TUI, транспорт Linux
│   └── bridge_agent_win/   # Исходный код агента Windows
├── pocket/                 # Локальный каталог Карман (общие файлы)
│   └── .notes/             # SQLite-журнал заметок (journal.db)
└── docs/                   # Документация проекта
```

---

## 3. Настройка виртуального окружения Python

Вы можете использовать современный пакетный менеджер **`uv`** (рекомендуется за счет максимальной скорости) либо стандартный модуль **`venv`**.

### Вариант А: Использование `uv` (Рекомендуется)

1. Установка `uv` в систему:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source ~/.bashrc  # или source ~/.zshrc
   ```

2. Создание изолированного виртуального окружения:
   ```bash
   uv venv .venv
   source .venv/bin/activate
   ```

3. Установка проекта и зависимостей в режиме редактирования (`editable`):
   ```bash
   uv pip install -e ".[client,dev]"
   ```

### Вариант Б: Использование стандартного `venv` + `pip`

1. Создание виртуального окружения:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Обновление базовых компонентов:
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

3. Установка проекта и зависимостей:
   ```bash
   pip install -e ".[client,dev]"
   ```

### 3.1 Проверка корректности установки
Выполните команду проверки импортов:
```bash
python3 -c "import bridge_core, bridge_client_linux; print('[OK] Bridge Local Core and Client successfully imported')"
```
Вывод должен подтвердить успешную загрузку модулей:
```text
[OK] Bridge Local Core and Client successfully imported
```

---

## 4. Конфигурация (`bridge.toml`)

Создайте или отредактируйте конфигурационный файл `bridge.toml` в корне проекта:

```bash
nano bridge.toml
```

### Пример рабочей конфигурации для Linux-клиента:
```toml
# Переключатель режима разработчика: true (полная трассировка) / false (тихий режим)
dev_mode = false

[node]
name = "linux-workstation"
role = "client"
listen_host = "127.0.0.1"
listen_port = 9733
auth_token = "0123456789abcdef0123456789abcdef"

[network]
heartbeat_interval_sec = 10.0
connect_timeout_sec = 5.0
request_timeout_sec = 30.0

[network.nodes.win-pc]
host = "192.168.1.150"       # IP-адрес вашей Windows-машины в локальной сети
port = 9732                  # Порт агента Bridge Local
role = "agent"

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

> [!IMPORTANT]
> Параметры `auth_token` и `psk_secret` на Linux-клиенте и Windows-агенте **должны быть идентичны**. Если токены не совпадают, агент отклонит все запросы с ошибкой `AUTH_ERROR`.

Создайте каталоги для Кармана и базы заметок:
```bash
mkdir -p pocket/.notes
chmod 700 bridge.toml
```

---

## 5. Интерактивная консоль управления (`start.sh`)

В проект включен скрипт быстрой диагностики и управления `start.sh`.

1. Предоставьте права на исполнение:
   ```bash
   chmod +x start.sh
   ```

2. Запустите консоль:
   ```bash
   ./start.sh
   ```

### Возможности меню `start.sh`:
- **`[1] QUICK START`** — Автоматическая проверка сокета на Windows-узле, создание нужных каталогов и запуск интерактивной сессии.
- **`[2] Launch Interactive TUI Dashboard`** — Запуск графического дашборда прямо в терминале.
- **`[3] Continuous Pocket Synchronization Daemon`** — Запуск циклического синхронизатора файлов Кармана в активном терминале.
- **`[4] Install Systemd User Service`** — Регистрация демона синхронизации в системной службе пользователя `systemd --user`.
- **`[5] Ping Remote Agent`** — Проверка времени отклика (RTT), загрузки процессора и ОЗУ Windows-узла.
- **`[6] Remote PowerShell Execution Prompt`** — Интерактивная отправка PowerShell-команд на удалённую машину.
- **`[7] Send Quick Note / URL`** — Быстрая отправка текста, кода или веб-ссылки на экран Windows.
- **`[8] View Pocket Status & Diff`** — Сравнение содержимого локального и удалённого кармана.
- **`[9] Pull All Changed Files from Windows`** — Скачивание новых файлов из Windows.
- **`[10] Push All Changed Files to Windows`** — Выгрузка локальных файлов на Windows.
- **`[11] Edit bridge.toml Configuration`** — Быстрое открытие настроек в системном редакторе.
- **`[12] Run Development Verification`** — Запуск локальных линтеров (`ruff`, `mypy`).

---

## 6. Работа через командную строку (CLI из исходного кода)

При работе из активированного виртуального окружения (`source .venv/bin/activate`) доступна прямая команда `bridge-cli`, либо вызов через Python: `python3 -m bridge_client_linux.cli`.

Для удобства можно добавить алиас в `~/.bashrc`:
```bash
alias bridge-cli="python3 -m bridge_client_linux.cli"
```

### 6.1 Проверка связи (`ping`)
Отправка эхо-запроса на Windows-агент:
```bash
bridge-cli ping
```
*Пример вывода:*
```text
PONG from win-pc (windows): rtt=14.12ms status=ready cpu=0.0% ram=11769MB
```

В формате JSON (для скриптов и AI-агентов):
```bash
bridge-cli ping --json
```

### 6.2 Удаленное выполнение PowerShell-команд (`exec`)
Выполнение команд в среде PowerShell на Windows с сохранением рабочего каталога между вызовами:

```bash
# Получить список процессов
bridge-cli exec "Get-Process -Name 'bridge-agent', 'explorer' | Select-Object Id, ProcessName"

# Проверить свободное место на дисках Windows
bridge-cli exec "Get-PSDrive -PSProvider FileSystem | Select-Object Root, Free, Used"

# Выполнить длительную команду с увеличенным таймаутом (секунды)
bridge-cli exec --timeout 120 "Get-ChildItem -Path C:\ -Recurse -Filter '*.log' -ErrorAction SilentlyContinue | Select-Object -First 10 FullName"
```

Коды возврата PowerShell транслируются в Linux: если скрипт на Windows падает с ошибкой, `bridge-cli` завершается с кодом `4` (`COMMAND_FAILED`).

### 6.3 Работа с файловым Карманом (`pocket`)

#### Просмотр статуса и очереди синхронизации:
```bash
bridge-cli pocket status
```
*Пример вывода:*
```text
                           ◈ POCKET STORAGE STATUS ◈                            
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Параметр                     ┃ Значение                                      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Локальный путь               │ /home/user/Bridge_Local/pocket               │
│ Файлов (Local / Remote)      │ 29 / 29                                       │
│ Размер (Local / Remote)      │ 641849 B / 641849 B                           │
│ Очередь PULL (скачать)       │ 0 файлов                                      │
│ Очередь PUSH (отправить)     │ 0 файлов                                      │
│ Статус синхронизации         │ 100% IN SYNC                                  │
└──────────────────────────────┴───────────────────────────────────────────────┘
```

#### Загрузка файла в удаленный карман на Windows:
```bash
bridge-cli pocket push my_document.pdf
```

#### Скачивание файла из удаленного кармана:
```bash
bridge-cli pocket pull photo_2026-10-03.jpg
```

#### Однократная двунаправленная синхронизация всех файлов:
```bash
bridge-cli pocket sync
```

#### Непрерывный режим наблюдения (Watchdog):
Фоновое отслеживание изменений с интервалом проверки (например, каждые 3 секунды):
```bash
bridge-cli pocket sync --watch --interval 3.0
```

### 6.4 Быстрые записки и ссылки (`note`)

#### Отправка заметки на Windows:
```bash
bridge-cli note send "https://github.com/Anhelm01/Bridge_Local"
bridge-cli note send "Привет! Файлы в кармане обновлены."
```

#### Просмотр журнала заметок:
```bash
bridge-cli note list
```

#### Отметка заметок как прочитанных:
```bash
bridge-cli note read <NOTE_ID>
```

### 6.5 Графический терминальный интерфейс (`tui`)
Запуск полноэкранного дашборда на базе Rich/Textual:
```bash
bridge-cli tui
```
- **Горячие клавиши:**
  - `Tab` / `Shift+Tab`: переключение между панелями (Статус, Карман, Заметки, Логи).
  - `s`: принудительная синхронизация кармана.
  - `p`: отправка пинга.
  - `r`: обновить экран.
  - `q` / `Ctrl+C`: выход из TUI.

---

## 7. Фоновая автоматизация через `systemd --user`

Чтобы Карман синхронизировался непрерывно в фоне без необходимости держать открытый терминал:

1. Создайте каталог для пользовательских служб:
   ```bash
   mkdir -p ~/.config/systemd/user
   ```

2. Создайте файл службы `~/.config/systemd/user/bridge-pocket-sync.service`:
   ```ini
   [Unit]
   Description=Bridge Local Pocket Storage Continuous Sync
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=%h/Projects/Bridge_Local
   ExecStart=%h/Projects/Bridge_Local/.venv/bin/python3 -m bridge_client_linux.cli pocket sync --watch --interval 3.0
   Restart=always
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1
   Environment=BRIDGE_CONFIG=%h/Projects/Bridge_Local/bridge.toml

   [Install]
   WantedBy=default.target
   ```

3. Активируйте и запустите службу:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now bridge-pocket-sync.service
   ```

4. Проверка статуса и просмотр логов:
   ```bash
   systemctl --user status bridge-pocket-sync.service
   journalctl --user -u bridge-pocket-sync.service -f
   ```

---

## 8. Устранение неполадок (Troubleshooting)

### 8.1 Сеть: Агент недоступен (`NETWORK_ERROR`, код 2)
1. Проверьте физическую связь с Windows-узлом:
   ```bash
   ping -c 3 192.168.1.150
   ```
2. Проверьте доступность порта 9732:
   ```bash
   nc -zv 192.168.1.150 9732
   ```
   *Если выводится `Connection refused` или таймаут:*
   - Убедитесь, что агент запущен на Windows.
   - Проверьте, что в брандмауэре Windows открыт порт 9732 TCP (см. `docs/03_SETUP_NAKED_WINDOWS.md`).

### 8.2 Ошибка авторизации (`AUTH_ERROR`, код 3)
- Проверьте совпадение `auth_token` и `psk_secret` в файле `bridge.toml` на обоих компьютерах.
- Проверьте системные часы: разница во времени между Linux и Windows не должна превышать $\pm 60$ секунд (защита от атак повторного воспроизведения).
  ```bash
  date
  ```

### 8.3 Конфликты `LD_PRELOAD` или Proxychains
Если в системе активен `proxychains` или задан `LD_PRELOAD`, локальные соединения по 192.168.x.x могут перенаправляться в прокси.
Запускайте команды с очисткой переменной:
```bash
LD_PRELOAD="" bridge-cli ping
```
