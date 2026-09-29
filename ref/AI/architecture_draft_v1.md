# Архитектура компонентов и контракты сетевых сообщений (Черновик)

> **Статус:** Рабочий черновик — ожидает проверки и корректировки пользователем.  
> **Автор:** AI  
> **Фаза:** 0 → вход в Фазу 1 (контракты и протокол)

---

## 1. Общая архитектурная схема компонентов

```
┌──────────────────────────────────────────────────────────────────┐
│                     LINUX HOST (Controller)                      │
│                                                                  │
│  ┌────────────────────┐     ┌──────────────────────────────────┐ │
│  │  bridge-cli (TUI)  │────▷│  bridge_client_linux             │ │
│  │  bridge-cli --json ├────▷│    ├── ConnectionManager         │ │
│  └────────────────────┘     │    ├── ExecClient                │ │
│                             │    ├── PocketClient               │ │
│                             │    ├── NotesClient                │ │
│                             │    └── StatusMonitor              │ │
│                             └────────────┬─────────────────────┘ │
│                                          │                       │
│  ┌───────────────────────────────────────┼───────────────────┐   │
│  │  bridge_core                          │                   │   │
│  │    ├── transport.py (AsyncClient)     │                   │   │
│  │    ├── protocol.py (JSON-RPC framing) │                   │   │
│  │    ├── models.py (Pydantic DTOs)      │                   │   │
│  │    ├── heartbeat.py (Liveness probe)  │                   │   │
│  │    ├── logger.py (JSONL audit writer) │                   │   │
│  │    ├── codec.py (UTF-8/CP decoder)    │                   │   │
│  │    └── security.py (PSK auth, HMAC)   │                   │   │
│  └───────────────────────────────────────┼───────────────────┘   │
│                                          │                       │
└──────────────────────────────────────────┼───────────────────────┘
                                           │  TCP / WebSocket
                                           │  (TLS optional)
┌──────────────────────────────────────────┼───────────────────────┐
│                     WINDOWS HOST (Agent)  │                      │
│                                          │                       │
│  ┌───────────────────────────────────────┼───────────────────┐   │
│  │  bridge_core (та же библиотека)       │                   │   │
│  │    ├── transport.py (AsyncServer)     │                   │   │
│  │    ├── protocol.py                    │                   │   │
│  │    ├── models.py                      │                   │   │
│  │    ├── heartbeat.py                   │                   │   │
│  │    ├── logger.py                      │                   │   │
│  │    ├── codec.py                       │                   │   │
│  │    └── security.py                    │                   │   │
│  └───────────────────────────────────────┼───────────────────┘   │
│                                          │                       │
│  ┌───────────────────────────────────────┼───────────────────┐   │
│  │  bridge_agent_win                     │                   │   │
│  │    ├── service.py (Windows Service)   │                   │   │
│  │    ├── executor.py (PowerShell runner)│                   │   │
│  │    ├── process_killer.py              │                   │   │
│  │    ├── pocket_sync.py (File watcher)  │                   │   │
│  │    └── notes_store.py                 │                   │   │
│  └───────────────────────────────────────┴───────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  pocket/ (shared directory on disk)                       │   │
│  │    ├── logs/                                              │   │
│  │    │   ├── 2026-09-30.jsonl                               │   │
│  │    │   └── 2026-10-01.jsonl                               │   │
│  │    ├── user_file_1.pdf                                    │   │
│  │    └── user_file_2.txt                                    │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Дерево модулей (Module Tree)

```
src/
├── bridge_local/
│   └── __init__.py          # Корневой пакет, точка входа bridge-cli
│
├── bridge_core/
│   ├── __init__.py
│   ├── models.py            # Pydantic V2 DTO: все типы сообщений
│   ├── protocol.py          # Фрейминг JSON-RPC 2.0 (length-prefix или newline-delimited)
│   ├── transport.py         # AsyncTransportClient / AsyncTransportServer (asyncio)
│   ├── heartbeat.py         # HeartbeatManager: fail-fast с настраиваемым интервалом
│   ├── logger.py            # AtomicJSONLWriter: потокобезопасный, ротация по дате
│   ├── codec.py             # WindowsOutputDecoder: UTF-8 / CP1251 / CP866 fallback
│   ├── security.py          # PSKAuthenticator: HMAC-SHA256, nonce anti-replay
│   └── config.py            # BridgeConfig: загрузка/сохранение конфигурации
│
├── bridge_agent_win/
│   ├── __init__.py
│   ├── service.py           # WindowsBridgeService: жизненный цикл службы SCM
│   ├── executor.py          # PowerShellExecutor: запуск, чтение потоков, кодировка
│   ├── process_killer.py    # ProcessTreeKiller: завершение зависших процессов
│   ├── pocket_sync.py       # PocketSyncEngine: отслеживание и отправка файлов
│   └── notes_store.py       # NotesStore: хранение и управление записками
│
└── bridge_client_linux/
    ├── __init__.py
    ├── cli.py               # Typer CLI (интерактивный + headless)
    ├── connection.py         # ConnectionManager: подключение, реконнект
    ├── exec_client.py        # Клиент удаленного выполнения команд
    ├── pocket_client.py      # Клиент синхронизации «кармана»
    ├── notes_client.py       # Клиент записок
    └── status_monitor.py     # Мониторинг статуса Windows-узла (Dashboard)
```

---

## 3. Черновик контрактов сетевых сообщений (JSON-RPC 2.0)

Все сообщения передаются как JSON-RPC 2.0 объекты с обязательным полем `method`.

### 3.1. Heartbeat (Ping/Pong)

```json
// --> Client to Agent
{
    "jsonrpc": "2.0",
    "method": "heartbeat.ping",
    "id": "uuid-1234",
    "params": {
        "client_timestamp_us": 1727650000000000,
        "client_os": "linux"
    }
}

// <-- Agent to Client
{
    "jsonrpc": "2.0",
    "id": "uuid-1234",
    "result": {
        "agent_timestamp_us": 1727650000012345,
        "agent_os": "windows",
        "cpu_percent": 12.5,
        "memory_used_mb": 4200,
        "uptime_seconds": 86400,
        "status": "ready"
    }
}
```

### 3.2. Remote Execution (ExecRequest / ExecResponse)

```json
// --> Client to Agent
{
    "jsonrpc": "2.0",
    "method": "exec.run",
    "id": "uuid-5678",
    "params": {
        "command": "Get-Service | Where-Object {$_.Status -eq 'Running'}",
        "timeout_sec": 30,
        "run_as_admin": true,
        "working_dir": null,
        "env": null
    }
}

// <-- Agent to Client (success)
{
    "jsonrpc": "2.0",
    "id": "uuid-5678",
    "result": {
        "exit_code": 0,
        "stdout": "Status   Name               DisplayName\n------   ----               -----------\nRunning  Winmgmt            Windows Management Instrumentation\n...",
        "stderr": "",
        "duration_ms": 1250,
        "started_at": "2026-09-30T00:10:00.000Z",
        "completed_at": "2026-09-30T00:10:01.250Z",
        "timed_out": false,
        "encoding_detected": "utf-8"
    }
}

// <-- Agent to Client (timeout)
{
    "jsonrpc": "2.0",
    "id": "uuid-5678",
    "error": {
        "code": -32001,
        "message": "Command execution timed out",
        "data": {
            "timeout_sec": 30,
            "duration_ms": 30012,
            "partial_stdout": "...",
            "processes_killed": [1234, 5678, 9012]
        }
    }
}
```

### 3.3. Notes (Записки)

```json
// --> Отправка записки (любая сторона → любая сторона)
{
    "jsonrpc": "2.0",
    "method": "notes.send",
    "id": "uuid-note-01",
    "params": {
        "text": "Резервная копия завершена успешно",
        "author_os": "linux"
    }
}

// <-- Подтверждение доставки
{
    "jsonrpc": "2.0",
    "id": "uuid-note-01",
    "result": {
        "note_id": "note-2026-09-30-0001",
        "received_at": "2026-09-30T00:15:00.000Z",
        "status": "delivered"
    }
}

// --> Запрос истории
{
    "jsonrpc": "2.0",
    "method": "notes.history",
    "id": "uuid-hist-01",
    "params": {
        "limit": 50,
        "since": "2026-09-29T00:00:00.000Z"
    }
}
```

### 3.4. Pocket Sync (Синхронизация «Кармана»)

```json
// --> Запрос манифеста (Client → Agent)
{
    "jsonrpc": "2.0",
    "method": "pocket.manifest",
    "id": "uuid-sync-01",
    "params": {}
}

// <-- Манифест
{
    "jsonrpc": "2.0",
    "id": "uuid-sync-01",
    "result": {
        "files": [
            {
                "path": "report.pdf",
                "sha256": "a1b2c3d4...",
                "size_bytes": 1048576,
                "mtime_iso": "2026-09-30T00:00:00.000Z"
            }
        ],
        "total_size_bytes": 1048576,
        "file_count": 1
    }
}

// --> Запрос передачи файла (чанками)
{
    "jsonrpc": "2.0",
    "method": "pocket.pull",
    "id": "uuid-pull-01",
    "params": {
        "path": "report.pdf",
        "offset": 0,
        "chunk_size": 65536
    }
}
```

### 3.5. Схема записи в JSONL-лог аудита (`pocket/logs/YYYY-MM-DD.jsonl`)

Каждая строка — самодостаточный JSON-объект:

```json
{
    "ts": "2026-09-30T00:10:01.250123Z",
    "session_id": "sess-abc-123",
    "client_ip": "192.168.1.100",
    "method": "exec.run",
    "request_id": "uuid-5678",
    "command": "Get-Service | Where-Object {$_.Status -eq 'Running'}",
    "timeout_sec": 30,
    "exit_code": 0,
    "duration_ms": 1250,
    "stdout_preview": "Status   Name               DisplayName...",
    "stderr_preview": "",
    "timed_out": false,
    "status": "success"
}
```

---

## 4. Протокол фрейминга (Wire Format)

Предлагается **Length-Prefix Binary Framing** поверх TCP:

```
┌──────────┬──────────┬────────────────────────────────────┐
│ MAGIC(2) │ LEN(4)   │ PAYLOAD (LEN bytes, UTF-8 JSON)    │
│ 0xBR 0xDG│ uint32 BE│ JSON-RPC 2.0 message               │
└──────────┴──────────┴────────────────────────────────────┘
```

- **MAGIC:** 2 байта `0x42 0x52` ("BR") — для быстрого отсечения мусорных пакетов.
- **LEN:** 4 байта Big-Endian unsigned — длина payload в байтах.
- **PAYLOAD:** UTF-8 encoded JSON-RPC 2.0 сообщение.
- **Максимальный размер payload:** 64 МБ (настраиваемый) — для файловых чанков.

### Альтернатива (для обсуждения):
- **WebSocket** вместо raw TCP: встроенный фрейминг, проще с прокси/NAT, но тяжелее по зависимостям.
- **Newline-delimited JSON (NDJSON)** через TCP: проще, но невозможно передавать бинарные данные без base64.

---

## 5. Модель состояний подключения

```
                    ┌─────────────┐
       ┌───────────▷│ DISCONNECTED │◁──── timeout / error
       │            └──────┬──────┘
       │                   │ connect()
       │            ┌──────▼──────┐
       │            │ CONNECTING  │
       │            └──────┬──────┘
       │                   │ auth OK
       │            ┌──────▼──────┐
       │      ◁─────│  CONNECTED  │──── heartbeat OK ──▷ (stay)
       │  auth fail └──────┬──────┘
       │                   │ heartbeat miss × N
       │            ┌──────▼──────┐
       └────────────│ UNREACHABLE │──── auto-reconnect timer
                    └─────────────┘
```

---

## 6. Открытые вопросы (для обсуждения с пользователем)

1. **TCP vs WebSocket:** Рекомендация — начать с raw TCP + length-prefix (минимум зависимостей, полный контроль). WebSocket можно добавить позже как альтернативный транспорт.

2. **Шифрование канала:** Обязательно ли TLS в локальной сети, или достаточно PSK + HMAC для аутентификации без шифрования payload?

3. **Формат конфига:** TOML (`bridge.toml`) или JSON? TOML проще для редактирования человеком.

4. **Pocket Sync стратегия:** 
   - Polling (периодическое сканирование раз в N секунд)?
   - Watchdog (inotify на Linux / ReadDirectoryChangesW на Windows)?
   - Ручная команда `bridge-cli pocket sync`?
