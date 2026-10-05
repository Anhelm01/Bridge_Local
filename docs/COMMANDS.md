# Bridge Local: Complete CLI & Agent Command Reference

Полный справочник всех команд, параметров, флагов, кодов завершения и форматов вывода утилит **`bridge-cli`** (Linux) и **`bridge-agent`** (Windows).

---

## 1. Архитектура и принципы вывода

Bridge Local спроектирован с поддержкой двух режимов работы:
1. **Человеческий интерфейс (Human Ergonomics)**:
   - Цветной форматированный вывод (библиотека Rich), таблицы, прогресс-бары, интуитивные подсказки и полноэкранный TUI.
2. **Интерфейс ИИ-агентов (AI Operator / `agy_cli`)**:
   - Активируется флагом `--json` (`-j`).
   - Чистый JSON в `stdout` без ANSI-escape последовательностей.
   - Отсутствие интерактивных блокировок на `stdin`.
   - Детерминированные коды возврата процессов (Exit Codes 0..5).
   - Минимальное потребление токенов контекста LLM.

### Стандартизированные коды завершения (Exit Codes)
| Код | Символическое имя | Описание |
|:---:|:---|:---|
| **`0`** | `SUCCESS` | Команда успешно выполнена. |
| **`1`** | `GENERAL_ERROR` | Ошибка аргументов, сбой парсинга, ошибка конфигурации или внутреннее исключение. |
| **`2`** | `NETWORK_ERROR` | Сетевой сбой: хост недоступен, отказ в соединении (`ConnectionRefused`), сброс сокета. |
| **`3`** | `AUTH_ERROR` | Несовпадение токена PSK (Pre-Shared Key), HMAC верификации или обнаружен replay. |
| **`4`** | `COMMAND_FAILED` | Удаленный процесс PowerShell завершился с ненулевым кодом выхода. |
| **`5`** | `TIMEOUT` | Превышен лимит времени ожидания выполнения команды или ответа RPC. |

---

## 2. Справочник команд Linux-клиента (`bridge-cli`)

Синтаксис вызова:
```bash
bridge-cli [ОБЩИЕ_ФЛАГИ] [КОМАНДА] [ПОДКОМАНДА] [ПАРАМЕТРЫ...]
```

### Общие глобальные флаги
- `--json`, `-j`: Переключение вывода в машиночитаемый JSON.
- `--version`, `-v`: Отображение версии утилиты и компонентов.
- `--help`, `-h`: Справка по командам и параметрам.
- При запуске `bridge-cli` без аргументов в интерактивном TTY автоматически запускается полноэкранный **TUI**. В неинтерактивном окружении выводится справка.

---

### 2.1 Команды статуса и проверки связи

#### `bridge-cli ping`
Heartbeat-проверка доступности удаленного агента Windows с замером круговой задержки (RTT).

```bash
bridge-cli ping [-n COUNT] [-j] [-c CONFIG] [-h HOST] [-p PORT] [-t TOKEN] [--node NODE]
```
- `-n, --count INTEGER`: Количество отправляемых пробных запросов (по умолчанию: `1`, диапазон: `1..10`).
- `-j, --json`: Вывод JSON-структуры с RTT и метриками узла.
- `-c, --config PATH`: Путь к альтернативному файлу `bridge.toml`.
- `-h, --host TEXT`: Переопределить IP-адрес / хост удаленного узла.
- `-p, --port INTEGER`: Переопределить TCP-порт.
- `-t, --token TEXT`: Переопределить PSK-токен.
- `--node TEXT`: Имя целевого узла (по умолчанию из конфига).

**Пример JSON-вывода (`--json`)**:
```json
{
  "pings": [
    {
      "latency_ms": 38.45,
      "pong": {
        "status": "ok",
        "agent_os": "Windows",
        "cpu_percent": 3.2,
        "memory_used_mb": 4120,
        "timestamp": 1728130800.123
      }
    }
  ],
  "target_node": "win-pc"
}
```

#### `bridge-cli status`
Сводный статус всей системы: сетевая связь, метрики удаленного ПК (CPU, RAM, Uptime), состояние кармана и количество заметок.

```bash
bridge-cli status [-j] [-c CONFIG] [-h HOST] [-p PORT] [-t TOKEN] [-n NODE]
```

**Пример JSON-вывода (`--json`)**:
```json
{
  "node": {
    "name": "workstation-node",
    "target": "win-pc",
    "host": "192.168.1.150",
    "port": 9732
  },
  "connection": {
    "status": "online",
    "latency_ms": 35.12
  },
  "remote": {
    "status": "healthy",
    "os": "Windows",
    "cpu_percent": 5.1,
    "memory_used_mb": 4200,
    "uptime_seconds": 86400
  },
  "pocket": {
    "local_files": 4,
    "remote_files": 4,
    "in_sync": true,
    "pending_push": 0,
    "pending_pull": 0
  },
  "notes": {
    "total": 12,
    "unread": 0
  }
}
```

---

### 2.2 Удаленное исполнение PowerShell (`bridge-cli exec`)

Выполнение произвольных команд и скриптов PowerShell на удаленном узле Windows с автоматическим кодированием UTF-8 (`chcp 65001`), отслеживанием каталога (CWD) и возвратом exit-кода.

```bash
bridge-cli exec "<КОМАНДА>" [-T TIMEOUT] [--admin / --no-admin] [-d DIR] [-n NODE] [-j]
```
- `<КОМАНДА>` (Argument): Строка команды PowerShell.
- `-T, --timeout INTEGER`: Таймаут выполнения в секундах (по умолчанию: `30`). При превышении процесс принудительно завершается и возвращается exit-код `5`.
- `--admin / --no-admin`: Выполнять с повышенными привилегиями Администратора (по умолчанию: `--admin`).
- `-d, --dir TEXT`: Рабочий каталог на Windows (например: `C:\Projects` или `C:\Windows\System32`).
- `-n, --node TEXT`: Целевой узел исполнения.
- `-j, --json`: Машиночитаемый JSON-ответ.

**Пример вызова**:
```bash
bridge-cli exec "Get-Process -Name chrome | Select-Object -First 3" --json
```

**Пример JSON-вывода (`--json`) при успехе (Exit Code: 0)**:
```json
{
  "exit_code": 0,
  "stdout": " NPM(K)    PM(M)      WS(M)     CPU(s)      Id  SI ProcessName\n ------    -----      -----     ------      --  -- -----------\n     54    82.11     112.45      12.41    8412   1 chrome     \n",
  "stderr": "",
  "duration_ms": 142.5,
  "working_dir": "C:\\Users\\Operator"
}
```

**Пример JSON-вывода при ошибке команды (Exit Code: 4)**:
```json
{
  "status": "error",
  "error_code": 4,
  "error_type": "BridgeRemoteCommandError",
  "message": "PowerShell command returned exit code 1",
  "cmd_exit_code": 1,
  "stdout": "",
  "stderr": "Get-Process : Cannot find a process with the name 'unknown_proc'.\n"
}
```

---

### 2.3 Быстрая отправка файлов (`bridge-cli send` / `pocket drop`)

Мгновенная доставка файлов с Linux в удаленный карман на Windows.

```bash
bridge-cli send <ФАЙЛЫ...> [-d TARGET_DIR] [-j] [-c CONFIG] [-h HOST] [-p PORT] [-t TOKEN] [-n NODE]
```
- `<ФАЙЛЫ...>`: Один или несколько локальных путей к файлам.
- `-d, --target-dir TEXT`: Относительный подкаталог внутри удаленного кармана.
- `-j, --json`: Вывод списка отправленных файлов с хэшами SHA-256 и размерами.

**Пример**:
```bash
bridge-cli send build/app.exe report.pdf -d release --json
```

**Пример JSON-вывода**:
```json
{
  "count": 2,
  "sent": [
    {
      "file": "app.exe",
      "local_path": "/home/user/build/app.exe",
      "target_rel_path": "release/app.exe",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "total_bytes": 1048576,
      "completed": true
    },
    {
      "file": "report.pdf",
      "local_path": "/home/user/report.pdf",
      "target_rel_path": "release/report.pdf",
      "sha256": "ca978112ca1bbdcaf062c99460ced822cd106ffb309e6f410cf71ab68930add4",
      "total_bytes": 245120,
      "completed": true
    }
  ]
}
```

---

### 2.4 Управление Карманом (`bridge-cli pocket ...`)

#### `bridge-cli pocket status`
Диагностика состояния локального и удаленного кармана, сверка файлов и выявление очередей push/pull.
```bash
bridge-cli pocket status [-j]
```

#### `bridge-cli pocket sync`
Запуск механизма двухсторонней или односторонней синхронизации.
```bash
bridge-cli pocket sync [-d DIRECTION] [-w] [-i INTERVAL] [-j]
```
- `-d, --direction`: Направление синхронизации: `both` (по умолчанию), `push` или `pull`.
- `-w, --watch`: Режим непрерывного отслеживания изменений и автосинхронизации (Daemon Watcher).
- `-i, --interval FLOAT`: Интервал опроса в режиме `--watch` в секундах (по умолчанию `2.5`).

#### `bridge-cli pocket push`
Загрузка конкретного файла в карман Windows с возможностью переименования.
```bash
bridge-cli pocket push <FILE_PATH> [-t TARGET_NAME] [-j]
```

#### `bridge-cli pocket pull`
Скачивание конкретного файла из кармана Windows на Linux.
```bash
bridge-cli pocket pull <REMOTE_FILE> [-d LOCAL_DEST] [-j]
```
- `<REMOTE_FILE>`: Имя файла в кармане (например, `installer.exe`).
- `-d, --dest PATH`: Куда сохранить файл локально (по умолчанию: текущий локальный карман).

#### `bridge-cli pocket list`
Список файлов, находящихся в текущем локальном кармане на диске.
```bash
bridge-cli pocket list [-j]
```

#### `bridge-cli pocket path`
Вывод абсолютного пути к локальному каталогу кармана.
```bash
bridge-cli pocket path [-j]
```

---

### 2.5 Быстрые Заметки (`bridge-cli note ...`)

Двунаправленная доставка коротких сообщений, ссылок, буферов обмена и сниппетов.

#### `bridge-cli note send`
Отправка заметки на удаленный узел:
```bash
bridge-cli note send "<ТЕКСТ_ЗАМЕТКИ>" [-t TO_NODE] [-j]
```

#### `bridge-cli note list`
Просмотр истории входящих и исходящих заметок:
```bash
bridge-cli note list [-l LIMIT] [-u] [-j]
```
- `-l, --limit INTEGER`: Максимальное количество записок в выдаче (по умолчанию `20`).
- `-u, --unread`: Фильтровать только непрочитанные заметки.

#### `bridge-cli note read`
Пометка заметок как прочитанных:
```bash
bridge-cli note read <ID_ЗАМЕТКИ...> [-j]
```

---

### 2.6 Первоначальная настройка и конфигурация

#### `bridge-cli connect`
Быстрое сохранение адреса узла Windows в `bridge.toml` и немедленный замер сетевой доступности:
```bash
bridge-cli connect <IP[:PORT]> [-t TOKEN] [-c CONFIG] [-j]
```
*Пример:* `bridge-cli connect 192.168.1.150:9732 -t MySecretPskToken12345 --json`

#### `bridge-cli setup`
Интерактивный консольный мастер настройки (диалог с запросом хоста, порта и токена).

#### `bridge-cli config show`
Просмотр текущего активного файла `bridge.toml` (или JSON представление).
```bash
bridge-cli config show [-j]
```

#### `bridge-cli config set`
Программное обновление параметров конфигурации:
```bash
bridge-cli config set [--host HOST] [--port PORT] [--token TOKEN] [-j]
```

#### `bridge-cli config path`
Выводит точный абсолютный путь к активному файлу конфигурации.
```bash
bridge-cli config path [-j]
```

---

### 2.7 Графические и терминальные интерфейсы

#### `bridge-cli tui`
Запуск интерактивного полноэкранного интерфейса мониторинга и управления (Rich / Textual-like).
```bash
bridge-cli tui [-m MODE] [--single-pass]
```
- `-m, --mode`: Стартовый экран: `DASH`, `POCKET`, `NOTES`, `EXEC`, `CONFIG`, `DEV`.
- `--single-pass`: Отрисовка одного кадра без бесконечного цикла обновления (удобно для CI/скриптов).

#### `bridge-cli welcome`
Отрисовка официального фирменного экрана приветствия BRIDGES Master (Neofetch-стиль).

---

## 3. Справочник команд Windows-агента (`bridge-agent.exe`)

Синтаксис вызова на Windows:
```cmd
bridge-agent.exe [КОМАНДА] [ПАРАМЕТРЫ...]
```

При запуске без аргументов:
- Если запущен Windows SCM (Service Control Manager) — запускается как системная фоновая служба.
- Если запущен вручную (двойной клик в Проводнике или вызов из `cmd.exe`) — стартует консольный агент.

### 3.1 Основные команды агента

#### `bridge-agent.exe run`
Запуск демона службы агента в текущем консольном окне.
- Слушает на порту (по умолчанию `9732` на `0.0.0.0`).
- Запускает Watchdog мониторинга локального кармана.
- Обрабатывает входящие RPC-запросы от Linux (`ping`, `exec`, `pocket`, `notes`).
- Прерывание: `Ctrl+C`.

#### `bridge-agent.exe setup`
Интерактивный мастер первоначальной конфигурации в Windows-консоли:
- Автоматически сканирует все локальные IPv4 адреса сетевых адаптеров и выводит их оператору.
- Запрашивает желаемый порт, ключ PSK и путь к каталогу кармана.
- Сохраняет настройки в локальный `bridge.toml`.

#### `bridge-agent.exe config [show|path|opts]`
Просмотр и изменение сетевых параметров:
```cmd
bridge-agent.exe config
bridge-agent.exe config --port 9732 --token MyToken --pocket C:\BridgePocket
bridge-agent.exe config path
```

#### `bridge-agent.exe drop <ФАЙЛ_ИЛИ_КАТАЛОГ>`
Копирование файла или папки в локальный Карман для немедленной автосинхронизации с Linux:
```cmd
bridge-agent.exe drop C:\Work\archive.zip
bridge-agent.exe drop --clipboard
```
- Флаг `--alert`: показать системное уведомление Windows.
- Флаг `--quiet` / `--no-alert`: тихий режим без всплывающих окон.
- Флаг `--clipboard` / `-c`: извлечь файлы или текст из системного буфера обмена Windows и сохранить в карман.

#### `bridge-agent.exe tray [--with-agent]`
Запуск приложения в системном трее Windows (рядом с часами):
- Иконка статуса связи.
- Контекстное меню: открыть Карман, просмотр логов, ручная синхронизация, выход.
- Флаг `--with-agent`: автоматически запускает фоновый процесс агента вместе с треем.

#### `bridge-agent.exe service [install|start|stop|remove]`
Управление агентом как стандартной системной службой Windows (SCM Windows Service):
- `service install`: Регистрация службы `BridgeLocalAgent` с автозапуском при включении ПК.
- `service start`: Запуск зарегистрированной службы.
- `service stop`: Остановка службы.
- `service remove`: Полное удаление службы из системы.

#### `bridge-agent.exe install-context-menu` / `uninstall-context-menu`
- `install-context-menu`: Добавление пункта **«Отправить в Bridge Pocket»** в контекстное меню Проводника Windows (Explorer) при правом клике на любых файлах и папках.
- `uninstall-context-menu`: Удаление пункта меню из системного реестра.
- `generate-reg [file.reg]`: Генерация `.reg` файла для импорта настроек реестра администратором вручную.

---

## 4. Переменные окружения (Environment Variables)

| Переменная | Значение по умолчанию | Описание |
|:---|:---:|:---|
| `BRIDGE_CONFIG` | — | Явный путь к файлу конфигурации `bridge.toml`. |
| `BRIDGE_DEV_MODE` | `0` | Включение режима Hyper-Logging (`1` или `true` активирует миллисекундную трассировку сокетов). |
| `BRIDGE_NO_PROXY_BYPASS` | `0` | Отключает автоматический обход `proxychains` в Linux (по умолчанию `bridge-cli` сбрасывает `LD_PRELOAD`, чтобы соединяться с локальной подсетью напрямую). |
| `BRIDGE_LOG_LEVEL` | `INFO` | Уровень журналирования (`TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 5. Типовые сценарии использования (Cheat Sheet)

### Сценарий A: Проверка доступности Windows-станции
```bash
bridge-cli ping --json
```

### Сценарий B: Запуск фонового процесса на Windows без зависания
Если требуется запустить тяжелый длительный процесс (например, компиляцию или запуск игры/видеоплеера):
```bash
bridge-cli exec "Start-Process 'C:\Tools\app.exe' -ArgumentList '--silent'" --json
```

### Сценарий C: Завершение зависшего процесса на Windows
```bash
bridge-cli exec "Stop-Process -Name 'mygame' -Force" --json
```

### Сценарий D: Отправка собранного бинарника на Windows
```bash
bridge-cli send ./build/target.exe -d tools --json
```

### Сценарий E: Скачивание отчета или сгенерированного файла с Windows
```bash
bridge-cli pocket pull build_log.txt --dest ./logs/win_build.log --json
```
