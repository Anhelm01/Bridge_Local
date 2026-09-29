# Отчет Phase 2: Реализация общего ядра (Bridge Core Library)

> **Дата:** 2026-09-30  
> **Фаза:** 2 — Общее ядро (Bridge Core Library)  
> **Статус:** ✅ Завершена (100% тестов пройдены)  
> **Тестовое покрытие:** 104 unit/integration теста (104 passed за 1.65 сек)  

---

## 1. Цель фазы
Создать высокопроизводительный, отказоустойчивый и кроссплатформенный программный фундамент (`bridge_core`) для работы поверх TCP:
- Бинарный фрейминг (Length-Prefix Framing: MAGIC `0x42 0x52` + uint32 BE + JSON-RPC).
- Асинхронный сетевой транспорт (`AsyncTransportServer` и `AsyncTransportClient`) с поддержкой TLS.
- Механизм мгновенного Fail-Fast Heartbeat с порогом probe <= 1.5 сек.
- Потокобезопасный и асинхронный логгер аудита в `.jsonl` с ротацией по датам и `fsync`.
- Декодер кодовых страниц вывода Windows (UTF-8, CP1251, CP866, удаление BOM и ANSI-последовательностей).
- Модуль безопасности: PSK-аутентификация с HMAC-SHA256, защита от replay-атак и Path Traversal.
- Сквозное Dev-Mode Hyper-Logging с микросекундной точностью и кастомным уровнем `TRACE`.

---

## 2. Реализованные модули и компоненты

### 2.1. `bridge_core/protocol.py` (Бинарный фрейминг и JSON-RPC 2.0)
- `encode_frame(payload) -> bytes`: сборка фрейма с проверкой максимального размера (`MAX_PAYLOAD_SIZE = 64MB`).
- `read_frame(reader) -> bytes`: потоковое чтение из `asyncio.StreamReader` с контролем `FRAME_MAGIC` и защитой от переполнения памяти.
- `write_frame(writer, payload)`: асинхронная запись в `asyncio.StreamWriter` со сбросом буфера `drain()`.
- `parse_jsonrpc(data)`: десериализация в строго типизированные модели `JsonRpcRequest`, `JsonRpcResponse` или `JsonRpcErrorResponse`.

### 2.2. `bridge_core/codec.py` (Интеллектуальный декодер вывода Windows)
- `WindowsOutputDecoder.decode(raw_bytes)`:
  - Автоматическое распознавание и удаление UTF-8 BOM (`\xef\xbb\xbf`) и UTF-16 LE BOM (`\xff\xfe`).
  - Приоритетная цепочка декодирования: `preferred` -> `utf-8` -> `cp1251` -> `cp866` -> `utf-8 (replace)`.
  - Нормализация CRLF (`\r\n` -> `\n`).
  - Очистка от ANSI escape-последовательностей.

### 2.3. `bridge_core/logger.py` (Атомарный JSONL-аудит и Dev Hyper-Logging)
- Регистрация системного уровня `TRACE` (числовое значение 5, детальнее `DEBUG` 10).
- `AtomicJsonlLogger`:
  - Потоко- и корутинобезопасная запись через `threading.Lock` и `asyncio.Lock`.
  - Гарантированный сброс на диск: `flush()` + `os.fsync(fileno)` для защиты от потери логов при внезапном сбое питания/ОС.
  - Автоматическая ротация по дням: `pocket/logs/YYYY-MM-DD.jsonl`.
  - Чтение и фильтрация с защитой от повреждённых строк (`read_entries`).
- `setup_logging(config)`: форматирование с точностью до миллисекунд и именами файлов/строк в режиме `dev_mode`.

### 2.4. `bridge_core/security.py` (Безопасность и защита от атак)
- `PSKAuthenticator`:
  - HMAC-SHA256 подпись с солью из timestamp и криптографического nonce (`secrets.token_hex(16)`).
  - Защита от Replay-атак: кэширование использованных nonce с автоматической очисткой.
  - Проверка допустимого дрейфа системных часов (`max_clock_skew_sec = 30s`).
  - Сравнение хешей в постоянном времени (`hmac.compare_digest`) для защиты от timing-атак.
- `validate_safe_path(base_dir, relative_path)`: защита «кармана» от Path Traversal (`../../etc/passwd` и абсолютных путей).
- `create_server_ssl_context` / `create_client_ssl_context`: фабрики TLS 1.2+ контекстов.

### 2.5. `bridge_core/heartbeat.py` (Fail-Fast Liveness Heartbeat)
- `HeartbeatManager`:
  - `probe(timeout_sec <= 1.5)`: мгновенная проверка доступности узла перед выполнением команд.
  - Фоновый цикл периодических проверок с настраиваемым интервалом (`interval_sec = 2.0s`).
  - Замер RTT (Round-Trip Time) в миллисекундах.
  - Сохранение метрик агента (CPU, RAM, Uptime).
  - Автоматическая смена состояний: `CONNECTED` <-> `UNREACHABLE` при пропуске ответов без подвисания сокетов.

### 2.6. `bridge_core/transport.py` (Асинхронный TCP/TLS транспорт)
- `AsyncTransportServer`:
  - Приём подключений на базе `asyncio.start_server`.
  - Реестр методов (`register_handler`) и автоматическая маршрутизация JSON-RPC.
  - Корректная обработка `METHOD_NOT_FOUND`, `PARSE_ERROR` и `INTERNAL_ERROR`.
  - Защита от зависаний при остановке: таймауты на закрытие сокетов и отмену задач клиентов.
- `AsyncTransportClient`:
  - Подключение через `asyncio.open_connection` с настраиваемым таймаутом.
  - Метод `call_rpc(request, timeout_sec)`: корреляция ID запросов и ответов, генерация `RpcCallError` при серверных ошибках.

---

## 3. Результаты тестирования

Все модули ядра полностью покрыты тестами:

```
tests/unit/test_config.py                   .................. (17 passed)
tests/unit/test_models.py                   ........................................ (40 passed)
tests/unit/test_codec.py                    .......... (10 passed)
tests/unit/test_protocol.py                 .......... (10 passed)
tests/unit/test_security.py                 ............ (12 passed)
tests/unit/test_logger.py                   ..... (5 passed)
tests/unit/test_smoke.py                    ... (3 passed)
tests/unit/test_transport_and_heartbeat.py  ..... (5 passed)
============================== 104 passed in 1.65s ==============================
```

**Статический анализ и стиль кода:**
- `ruff check src/ tests/`: All checks passed!
- `ruff format --check src/ tests/`: 22 files already formatted!

---

## 4. Выявленные и устранённые краевые случаи

1. **Proxychains и сокеты loopback:**  
   В рабочей среде активен `proxychains` через `LD_PRELOAD`, который по умолчанию перехватывает системный вызов `connect()` и блокирует локальные сокеты `127.0.0.1`. Для тестов локального транспорта используется явный запуск с очисткой `LD_PRELOAD=""`.
2. **Блокировка `StreamWriter.wait_closed()` в Python 3.14:**  
   При разрыве соединения с удалённой стороной вызов `await writer.wait_closed()` может зависать в полузакрытом состоянии TCP. Добавлен `asyncio.wait_for(..., timeout=0.5)` во все блоки завершения соединений клиента и сервера.
3. **Двойная валидация однобайтовых кодировок (CP866 vs CP1251):**  
   Для корректного распознавания DOS-вывода CP866 добавлен параметр `preferred_encoding`, позволяющий вызывающей стороне явно указать ожидаемую кодовую страницу консоли.

---

## 5. Чеклист готовности к Фазе 3 (Definition of Done)

- [x] Бинарный wire protocol framing реализован и протестирован.
- [x] Асинхронный сервер и клиент TCP/TLS работают с корреляцией JSON-RPC.
- [x] Fail-Fast Heartbeat мгновенно определяет падение узла (probe <= 1.5s).
- [x] Атомарный JSONL-логгер сохраняет логи с `fsync` и ротацией по датам.
- [x] Декодер Windows корректно обрабатывает UTF-8, CP1251, CP866, BOM и ANSI.
- [x] Безопасность: PSK + HMAC + Nonce + защита от Path Traversal реализованы.
- [x] Заложена поддержка мульти-нод (`source_node`, `target_node`, `NodeConfig`).
- [x] Все 104 теста зелёные, линтеры чистые.

---

## 6. Следующий шаг: Фаза 3 — Windows Agent & Windows Service Daemon
- Реализация изолированного раннера PowerShell с админ-привилегиями (`bridge_agent_win/executor.py`).
- Реализация Process Tree Killer по таймауту (`bridge_agent_win/process_killer.py`).
- Интеграция с Windows Service Manager / Service Runner (`bridge_agent_win/service.py`).
- Создание легковесного Mock-агента под Linux для полного тестирования всего пайплайна выполнения команд без физической Windows-машины.
