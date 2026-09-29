# Отчет Phase 1: Спецификация контрактов (Wire Protocol, Data Models, Config)

> **Дата:** 2026-09-30  
> **Фаза:** 1 — Спецификация контрактов  
> **Статус:** ✅ Завершена  
> **Git commit:** `19d160f` — Phase 1: Pydantic V2 DTO contracts, TOML config, JSON-RPC models, 58 tests

---

## 1. Цель фазы
Реализовать типизированные контракты данных (Pydantic V2 DTO) для всех сетевых сообщений Bridge Local, спроектировать TOML-конфигурацию и утвердить wire protocol.

---

## 2. Выполненные работы

### 2.1. Модели данных (`src/bridge_core/models.py`)
Реализованы **все** DTO-контракты на базе Pydantic V2:

| Группа | Модели | Назначение |
|---|---|---|
| **JSON-RPC 2.0** | `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcErrorResponse` | Универсальные обёртки протокола |
| **Heartbeat** | `PingParams`, `PongResult` | Контракт liveness-пинга с метриками узла |
| **Exec** | `ExecRequestParams`, `ExecResult`, `ExecTimeoutErrorData` | Удалённое выполнение PowerShell |
| **Notes** | `NoteSendParams`, `NoteDeliveryResult`, `NoteHistoryParams`, `NoteEntry`, `NoteHistoryResult` | Двусторонний обмен записками |
| **Pocket Sync** | `PocketFileInfo`, `PocketManifestResult`, `PocketPullParams`, `PocketPushParams` | Синхронизация кармана по чанкам |
| **Audit Log** | `AuditLogEntry` | JSONL-совместимая запись аудита |

Также реализованы:
- **5 StrEnum перечислений:** `NodeOS`, `NodeStatus`, `ConnectionState`, `AuditStatus`, `NoteStatus`.
- **Класс `RpcErrorCode`:** Стандартные JSON-RPC + кастомные коды (COMMAND_TIMEOUT, AUTH_FAILED и т.д.).
- **Класс `RpcMethod`:** Реестр имён RPC-методов.
- **Константы wire protocol:** `FRAME_MAGIC`, `FRAME_HEADER_SIZE`, `MAX_PAYLOAD_SIZE`.

### 2.2. Конфигурация (`src/bridge_core/config.py`)
Реализован TOML-конфиг с Pydantic-валидацией:

| Секция | Модель | Ключевые поля |
|---|---|---|
| `[connection]` | `ConnectionConfig` | host, port, timeout, TLS пути, PSK токен |
| `[heartbeat]` | `HeartbeatConfig` | interval, timeout (fail-fast 1.5s), max_missed, reconnect_delay |
| `[pocket]` | `PocketConfig` | path, sync_watch, max_chunk_size, log_max_days |
| `[exec]` | `ExecConfig` | default_timeout, run_as_admin, force_utf8 |
| `[logging]` | `LoggingConfig` | level (TRACE по умолчанию), dev_mode, console/file output |

- Загрузка: `BridgeConfig.load(path)` — читает TOML через `tomllib`, при отсутствии файла — дефолты.
- Сохранение: `config.save(path)` — ручная TOML-сериализация без внешних зависимостей.
- Roundtrip: load → save → load протестирован.

### 2.3. Архитектурные решения (зафиксированы)
| Решение | Значение |
|---|---|
| Транспорт | Raw TCP + Length-Prefix Binary Framing (MAGIC `0x4252` + uint32 BE + JSON UTF-8) |
| Шифрование | TLS обязательно + PSK/HMAC |
| Конфиг | TOML (`bridge.toml`) |
| Sync кармана | Watchdog (inotify/ReadDirectoryChanges) + ручная команда |

---

## 3. Результаты тестирования

```
58 passed in 0.12s

Breakdown:
  test_config.py   — 15 тестов (defaults, bounds, load, save, roundtrip, partial)
  test_models.py   — 40 тестов (enums, JSON-RPC, heartbeat, exec, notes, pocket, audit, wire)
  test_smoke.py    —  3 теста (импорт пакетов)
```

**Ruff lint:** All checks passed  
**Ruff format:** All files formatted

---

## 4. Логирование (Dev-Mode)
- Конфиг по умолчанию: `level = "TRACE"`, `dev_mode = true`.
- Архитектура переключения Dev vs Release заложена в `LoggingConfig`: одна переменная `dev_mode` + `level` контролируют уровень детализации.
- Фактические точки трассировки будут добавлены в Фазе 2 (transport, heartbeat, file I/O).

---

## 5. Выявленные нюансы
1. **Ruff UP017:** Python 3.11+ имеет `datetime.UTC` alias вместо `timezone.utc`. Ruff автоматически исправил на `UTC`.
2. **TOML-сериализация `None`:** TOML не имеет типа null. Принято решение сериализовать `None` как пустую строку `""` — при обратном чтении Pydantic корректно обработает пустую строку как `None` для `Optional[str]` полей.
3. **SHA-256 валидация в `PocketFileInfo`:** Установлены жёсткие границы `min_length=64, max_length=64` для гарантии корректности хешей.

---

## 6. Чеклист готовности к Фазе 2 (Definition of Done)

- [x] Все DTO-модели реализованы и покрыты тестами.
- [x] JSON-RPC roundtrip (serialize → deserialize) проверен для каждой модели.
- [x] Валидация ограничений (min, max, required, bounds) протестирована.
- [x] TOML-конфигурация: load, save, roundtrip, partial — всё зелёное.
- [x] Формат `.jsonl` аудита: однострочный JSON без переносов — верифицирован.
- [x] Wire protocol константы зафиксированы.
- [x] Ruff lint + format — чисто.
- [x] Архитектурный документ обновлён с утверждёнными решениями.
- [x] Git commit зафиксирован.

---

## 7. Следующий шаг: Фаза 2 — Bridge Core Library
- Реализация асинхронного TCP-транспорта с TLS (`asyncio`).
- Механизм Fail-Fast Heartbeat.
- Атомарный JSONL-логгер с ротацией по дате.
- Декодер кодовых страниц Windows (UTF-8 / CP1251 / CP866).
- Тотальное Dev-логирование на уровне ядра.
