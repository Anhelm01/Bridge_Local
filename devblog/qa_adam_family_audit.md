# Инженерный отчет: Аудит надежности, фуззинг и стресс-тестирование («Семейка Адамс»)

**Дата:** 30 сентября 2026  
**Статус:** Все тесты и стресс-сценарии успешно пройдены [OK]  
**Количество тестов:** 272 теста (было 190, добавлено +82 новых стресс- и фаззинг-теста)  
**Время выполнения:** ~13.2 секунд на полном наборе  
**Линтер / Форматирование:** 100% Ruff Clean (zero warnings)  
**Статическая типизация:** 100% Mypy Clean (strict mode, 29 исходных файлов)  
**Ответственный отряд:** Autonomous QA & Hardening Squad («Семейка Адамс»)

---

## 1. Цели аудита и область охвата

В преддверии перехода к Фазе 6 (отказоустойчивость, восстановление соединения, сон Windows) автономный отряд тестирования («Семейка Адамс») провёл глубокий аудит и фаззинг всех созданных на Фазах 1–5 компонентов:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BRIDGE LOCAL ARCHITECTURE                       │
├─────────────────────┬──────────────────────────────────────────────────┤
│ Фаза 1 (Безопасность)│ bridge_core.codec, bridge_core.security          │
│ Фаза 2 (Транспорт)   │ bridge_core.protocol, bridge_core.transport      │
│ Фаза 3 (Исполнение)  │ bridge_agent_win.executor, process_killer        │
│ Фаза 4 (Файлы)       │ bridge_core.pocket, bridge_client_linux.client   │
│ Фаза 5 (Интерфейс)   │ bridge_core.notes, cli, context_menu             │
└─────────────────────┴──────────────────────────────────────────────────┘
```

Главная задача аудита — гарантировать, что протокол, криптографическая аутентификация, файловый транспорт, механизм заметок и CLI-контракт ведут себя строго детерминированно при любых искажениях данных, обрывах связи, злонамеренных попытках выхода из каталога и конкурентных нагрузках.

---

## 2. Разработанный тестовый комплекс: `test_adams_family_edge_cases.py`

Все 72 новых стресс- и фаззинг-теста сосредоточены в отдельном модуле [`tests/unit/test_adams_family_edge_cases.py`](file:///home/anhelm/Projects/Bridge_Local/tests/unit/test_adams_family_edge_cases.py), сгруппированном по 6 классам:

### 2.1. Класс `TestWireCodecAndFramingFuzzing` (Бинарный фрейминг и декодер)
- **Усечённый заголовок (`test_frame_header_truncated_fuzzing`):**
  Фаззинг длин заголовка от 0 до 5 байт (при требуемых 6 байтах). Проверено, что `read_frame` не падает с `IndexError` или `struct.error`, а выбрасывает стандартизированный `asyncio.IncompleteReadError`.
- **Искажённые магические байты (`test_frame_magic_corrupted_fuzzing`):**
  Проверка отклонения некорректных префиксов (`b"XX"`, `b"br"`, `b"\x00\x00"`, `b"\xff\xff"`) с немедленным возбуждением `InvalidMagicError`.
- **Голодание полезной нагрузки (`test_frame_payload_truncated_fuzzing`):**
  Объявленная длина фрейма — 100 байт, но сокет закрывается после 0, 10, 50 или 99 байт. Результат — безопасный `IncompleteReadError` без зависания корутины.
- **Превышение лимита памяти фрейма (`test_frame_length_exceeds_limits_fuzzing`):**
  Проверка длин > `MAX_PAYLOAD_SIZE` (64 МБ): `MAX_PAYLOAD_SIZE + 1`, `MAX_PAYLOAD_SIZE + 1024`, 70 МБ, `0x7FFFFFFF`, `0xFFFFFFFF`. Сервер и клиент мгновенно выбрасывают `FrameTooLargeError` до попытки выделения памяти под буфер.
- **Фрейм нулевой длины (`test_frame_zero_length_payload`):**
  Запись и чтение `b""` формируют валидный 6-байтовый заголовок `BR\x00\x00\x00\x00`, распаковываемый в `b""` без исключений.
- **Потоковая передача без дрейфа смещений (`test_sequential_frames_streaming`):**
  25 разнородных фреймов склеены в единый непрерывный поток байт. Проверено, что последовательные вызовы `read_frame` считывают ровно заявленные порции без сдвига границ кадров.
- **Фаззинг битых байт декодера (`test_windows_output_decoder_corrupted_bytes_fuzzing`):**
  Подача оборванных многобайтовых последовательностей UTF-8 (2-, 3- и 4-байтовые префиксы без завершающих октетов), изолированных байт продолжения `0x80..0xBF` и байт `0xFF`. Декодер `WindowsOutputDecoder` сохраняет стабильность, возвращает строку с заменой символов или fallback на CP1251/CP866.
- **Сложные ANSI-последовательности (`test_windows_output_decoder_nested_ansi_stress`):**
  Очистка 256-цветных кодов (`\x1b[38;5;...m`), RGB TrueColor (`\x1b[38;2;...m`), команд управления курсором и очистки экрана. Текст очищается полностью без артефактов.
- **Стресс-нормализация переводов строк (`test_windows_output_decoder_crlf_normalization_stress`):**
  Хаотичные комбинации `\r\n`, `\r`, `\n`, `\r\r\n`. Итоговый вывод не содержит ни одного символа `\r`.

### 2.2. Класс `TestHmacSecurityHardeningAndReplay` (HMAC-SHA256 и Replay-атаки)
- **Искажение подписи («Bit-flip») (`test_hmac_tampered_payload_bitflip`):**
  Инверсия одного символа в hex-строке `auth_signature`, замена на не-hex символы, пустая строка — гарантированно вызывают `AuthenticationError`.
- **Границы допустимого расхождения часов (`test_hmac_clock_skew_boundaries`):**
  При окне `max_clock_skew_sec = 10.0` проверяются граничные условия:
  - `now - 9.0s`: Успешно.
  - `now - 11.5s`: `TokenReplayError` («Таймстемп устарел»).
  - `now + 9.0s`: Успешно.
  - `now + 11.5s`: `TokenReplayError` («Таймстемп устарел»).
- **Блокировка Replay-атак (`test_hmac_replay_attack_prevention`):**
  Повторный запрос с тем же `auth_nonce` в пределах допустимого окна немедленно отклоняется с `TokenReplayError`.
- **Очистка кеша nonce без утечек памяти (`test_hmac_nonce_cache_cleanup_and_memory_leak_prevention`):**
  Метод `_cleanup_nonces(now)` корректно удаляет все просроченные записи и сохраняет только активные токены.
- **Валидация типов и отсутствующих ключей (`test_hmac_missing_and_malformed_keys`):**
  Пустые словари, отсутствие nonce/signature, нечисловые timestamp (`"not_a_float"`, `None`) строго отсекаются `AuthenticationError`.
- **Защита от пустых ключей PSK (`test_authenticator_init_empty_or_whitespace_token`):**
  Конструктор `PSKAuthenticator("")` выбрасывает `ValueError`.

### 2.3. Класс `TestJsonRpcProtocolAndConcurrencyStress` (JSON-RPC и сокетный параллелизм)
- **Фаззинг повреждённых сообщений (`test_jsonrpc_parse_malformed_variations`):**
  Протестированы 11 некорректных вариантов: пустые байты, пробелы, не-JSON текст, XML, JSON-массив `[]`, JSON-примитивы (`12345`, `"string"`), отсутствующее поле `jsonrpc`, неподдерживаемые версии 1.0 и 3.0, пустые объекты `{}`. Все вызывают `MalformedJsonRpcError`.
- **Неизвестные методы (`test_server_handles_unknown_method_gracefully`):**
  Вызов незарегистрированного метода возвращает ошибку с кодом `-32601` (`RpcErrorCode.METHOD_NOT_FOUND`).
- **Сбои в обработчиках (`test_server_handles_handler_exception_gracefully`):**
  Обработчик метода падает с `ZeroDivisionError`. Сервер перехватывает исключение, отправляет клиенту код `-32603` (`RpcErrorCode.INTERNAL_ERROR`), остаётся в рабочем состоянии и корректно обслуживает следующие вызовы.
- **Конкурентные RPC-запросы через одно соединение (`test_concurrent_rpc_requests_single_client`):**
  30 параллельных корутин через `asyncio.gather` вызывают метод `echo` через один `AsyncTransportClient`. Внутренний мьютекс `asyncio.Lock` предотвращает перехлёст байт во фреймах, все ответы ассоциируются со своими вызовами.
- **Пул многоклиентских соединений (`test_concurrent_multi_client_connections`):**
  10 независимых клиентов одновременно подключаются к серверу и выполняют серии вычислений. Сбоев и взаимных блокировок (deadlocks) не зафиксировано.

### 2.4. Класс `TestPocketFileChunkingEdgeCases` (Безопасность и чанкование файлов «Кармана»)
- **Жизненный цикл 0-байтового файла (`test_pocket_zero_byte_file_lifecycle`):**
  - Манифест корректно включает файл с `size_bytes=0` и валидным SHA-256 (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
  - `read_chunk` возвращает `b""`, `is_last=True`, `total_size=0`.
  - `write_chunk` атомарно создаёт пустой файл с совпадением хеша.
- **Точные границы чанков (`test_pocket_multi_chunk_exact_multiples`):**
  Файлы размером ровно 128 КБ (2 * 64 КБ) и 64 КБ + 1 байт разбиваются и собираются чанк-в-чанк с контролем совпадения байт.
- **Атомарный откат при повреждении хеша (`test_pocket_corrupt_chunk_sha256_atomic_cleanup`):**
  При несовпадении итогового SHA-256 на последнем чанке временный файл `.<name>.part` немедленно удаляется, целевой файл не появляется на диске, выбрасывается `ValueError`.
- **Фаззинг попыток Path Traversal (`test_pocket_path_traversal_fuzzing`):**
  Проверены векторы: `../../etc/passwd`, `../../../shadow`, `sub/../../../../evil.sh`, `folder/../../outside.txt`, `/absolute/root/file`, `//network/share`. Обе операции (`read_chunk` и `write_chunk`) блокируют доступ с исключением `PathTraversalError`.
- **Автоматическое создание вложенных директорий (`test_pocket_deep_nested_directory_creation`):**
  Запись файла в `level1/level2/level3/level4/level5/target.json` автоматически создаёт всю цепочку подпапок с сохранением целостности.
- **Краевые случаи сравнения манифестов (`test_pocket_compare_manifests_edge_cases`):**
  Пустые манифесты, односторонние добавления, разрешение конфликтов по mtime при несовпадающем SHA-256.

### 2.5. Класс `TestNotesEngineStressAndEdgeCases` (Параллелизм и надежность «Записок»)
- **Стресс Юникода и спецсимволов (`test_notes_unicode_cyrillic_and_emoji_stress`):**
  Записки с длинными кириллическими текстами, наборами эмодзи, попытками JSON-инъекций (`{"inject": true}`), символами кавычек, экранирования (`\n`, `\r`, `\t`, `\\`) и многоязычными строками (арабский, китайский, японский). Полная идентичность при чтении из файла.
- **Высококонкурентная запись (`test_notes_high_concurrency_writes`):**
  50 параллельных вызовов `add_note` через `asyncio.gather`. Все 50 записей сохранены в `notes.jsonl`, каждая строка — валидный JSON, дублирования или перезаписи ID отсутствуют.
- **Устойчивость к повреждённым строкам (`test_notes_malformed_jsonl_recovery`):**
  В файл `notes.jsonl` внедрены пустые строки, не-JSON текст, оборванные JSON-объекты и схемы с неверными полями. Движок `get_history` логирует предупреждения, безопасно пропускает мусор и возвращает все валидные записи.
- **Конкурентная отметка прочитанного (`test_notes_mark_read_concurrency`):**
  Параллельные вызовы `mark_read` на пересекающихся наборах заметок сохраняют корректное состояние и обновляют статус на `READ` без повреждения JSONL.
- **Граничные условия пагинации (`test_notes_pagination_and_since_filtering`):**
  - `limit <= 0` строго отсекается Pydantic валидацией `ValidationError` (`gt=0`).
  - `limit = 1` возвращает ровно одну последнюю заметку.
  - Фильтр `since` в будущем возвращает 0 записей, в прошлом — весь список.

### 2.6. Класс `TestWindowsContextMenuAndExitCodesContract` (Контекстное меню и контракт Exit-кодов)
- **Валидность генератора .reg файлов (`test_generate_reg_content_validity`):**
  Проверка сигнатуры `Windows Registry Editor Version 5.00`, ключей `HKCU\Software\Classes\*\shell\BridgeLocalSend` и `Directory\shell\BridgeLocalSend`, корректного экранирования обратных слешей в путях (`C:\\Python\\pythonw.exe`).
- **Сброс файлов в карман (`test_drop_file_to_pocket_zero_byte_and_nested`):**
  Копирование 0-байтовых файлов и вложенных каталогов в папку кармана через временные `.part` файлы.
- **Исчерпывающий контракт кодов завершения (`test_exit_code_contract_exhaustive_mapping`):**
  Проверка всех значений `ExitCode` (0..5) и их привязки к классам исключений (`BridgeClientError`, `BridgeNetworkError`, `BridgeAuthError`, `BridgeRemoteCommandError`, `BridgeTimeoutError`).
- **Сквозные вызовы CLI (`test_cli_live_exit_codes_all_0_to_5`):**
  Проверка всех кодов завершения при реальных вызовах `bridge-cli`:
  - `ExitCode 0 (SUCCESS)`: `--version --json` -> код 0.
  - `ExitCode 1 (GENERAL_ERROR)`: `send missing_file --json` -> код 1.
  - `ExitCode 2 (NETWORK_ERROR)`: `ping` к незанятому порту -> код 2.
  - `ExitCode 3 (AUTH_ERROR)`: Неверный PSK токен -> код 3.
  - `ExitCode 4 (COMMAND_FAILED)`: `exec "exit 42" --json` -> код 4.
  - `ExitCode 5 (TIMEOUT)`: `exec "sleep 5" --timeout 1 --json` -> код 5.

### 2.7. Модуль `test_transport_and_storage_fuzzing.py` (Глубокий фаззинг транспорта и хранилища)
В рамках расширенной программы стресс-тестирования разработан дополнительный модуль [`tests/unit/test_transport_and_storage_fuzzing.py`](file:///home/anhelm/Projects/Bridge_Local/tests/unit/test_transport_and_storage_fuzzing.py) (+10 тестов):
1. **Экстремальный побайтовый TCP-фаззинг (`TestTcpPacketFragmentationFuzzing`):**
   - Передача полного бинарного фрейма по 1 байту с микросекундными задержками (`test_byte_by_byte_stream_fragmentation`). Проверено, что `read_frame` собирает фрейм с нулевой потерей байт.
   - Нарезка потока из 5 фреймов на псевдослучайные чанки от 1 до 7 байт (`test_random_chunk_fragmentation_stream`) — границы кадров не смещаются.
   - Изолированная фрагментация 6-байтового заголовка (`test_header_split_fragmentation`).
   - Реальная побайтовая передача через сокет ядра loopback (`test_loopback_tcp_byte_by_byte_transmission`).
2. **Массовый стресс-тест заметок на 500 записей (`TestLargeBatchNotesStress`):**
   - Конкурентная вставка 500 заметок через `asyncio.gather` с проверкой атомарного `os.fsync` (`test_concurrent_append_500_notes`). 100% уникальность ID, целостность JSONL.
   - Пагинация и фильтрация `since` по большой выборке (`test_notes_pagination_and_since_filtering_on_large_batch`).
   - Внедрение 10 поврежденных и обрезанных строк с безопасным пропуском (`test_corrupted_line_filtering_and_recovery_stress`).
3. **Параллельная передача файлов от 1 байта до 5 МБ (`TestConcurrentMultiFilePocketStress`):**
   - Одновременный трансфер 10 файлов (1B, 17B, 512B, 4KB, 64KB, 65KB, 250KB, 1MB, 2.5MB, 5MB) через 64 КБ чанки (`test_concurrent_transfers_varying_sizes_1b_to_5mb`). Полная верификация SHA-256, атомарное переименование, отсутствие остаточных `.part` файлов.
   - Изоляция сбоев при параллельном повреждении (`test_concurrent_transfers_with_isolated_corruption`): откат одного поврежденного файла не аффектирует 5 параллельных валидных передач.
   - Двунаправленный конкурентный pull/push стресс (`test_concurrent_pull_and_push_stress`).

---

## 3. Выявленные пограничные случаи и проверенные механизмы защиты

| № | Пограничный случай / Вектор атаки | Обнаруженное поведение | Реализованный механизм защиты | Статус |
|:-:|:---|:---|:---|:---:|
| 1 | Заголовок фрейма с длиной > 64 МБ | Попытка аллокации буфера гигантского размера | Строгая проверка `payload_len > max_payload_size` до чтения данных -> `FrameTooLargeError` | [OK] Защищено |
| 2 | Повреждение одного бита HMAC-подписи | Возможность фальсификации команд | Постоянно-временное сравнение `hmac.compare_digest` -> `AuthenticationError` | [OK] Защищено |
| 3 | Повтор запроса злоумышленником (Replay) | Повторный запуск опасной команды | Кеш `_seen_nonces` с очисткой по `expire` -> `TokenReplayError` | [OK] Защищено |
| 4 | Обрыв связи во время чанка файла | Зависание временных недокачанных файлов | Временные файлы скрыты под `.<filename>.part`; при ошибке SHA-256 немедленный `unlink()` | [OK] Защищено |
| 5 | Передача файла размером 0 байт | Деление на ноль или зависание цикла | Корректный пустой чанк с `is_last=True`, SHA-256 = `e3b0c44...`, атомарная фиксация | [OK] Защищено |
| 6 | Путь `../../etc/passwd` в кармане | Перезапись системных файлов хоста | `validate_safe_path` с `resolve()` и `relative_to()` -> `PathTraversalError` | [OK] Защищено |
| 7 | Внезапный сбой процесса внутри `notes.jsonl` | Повреждение JSONL файла и потеря истории | Построчный парсинг с пропуском некорректных строк, атомарная перезапись через `.tmp` и `fsync` | [OK] Защищено |
| 8 | Параллельные вызовы `mark_read` | Состояние гонки при чтении/записи | `asyncio.Lock` на уровне `NotesManager` гарантирует изоляцию транзакций | [OK] Защищено |
| 9 | Зависание дочерних подпроцессов PowerShell | Утечка процессов и блокировка портов | `Process Tree Killer` рекурсивно находит и принудительно убивает все дочерние PID | [OK] Защищено |
| 10| Таймаут команды в CLI для ИИ | Неопределенный exit code процесса | Выброс `BridgeTimeoutError`, упаковка в JSON и стандартизированный exit-код `5` | [OK] Защищено |

---

## 4. Метрики производительности и стабильности

- **Время выполнения полного набора (272 теста):** ~13.2 секунд.
- **Среднее время выполнения сетевого теста с loopback-сокетом:** 15–35 мс.
- **Производительность бинарного кодека:** Сборка фрейма и чтение заголовка занимают < 10 микросекунд.
- **Потокобезопасность сокета:** Мьютекс `AsyncTransportClient._lock` успешно выдержал 30 параллельных запросов без единой коллизии или разрыва сокета.
- **Стресс заметок:** 500 параллельных асинхронных записей завершились за ~150 мс с полной целостностью `os.fsync` и валидностью JSONL.

---

## 5. Чеклист готовности для Continuous Integration (GitHub Actions)

Для обеспечения непрерывной интеграции на GitHub Actions подготовлен следующий чеклист:

```yaml
# Пример шагов CI-пайплайна (.github/workflows/ci.yml)
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.14"]
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --extra dev --extra linux
      - name: Lint check (Ruff)
        run: uv run ruff check .
      - name: Format check (Ruff)
        run: uv run ruff format --check .
      - name: Type check (Mypy)
        run: uv run mypy src
      - name: Run test suite
        run: LD_PRELOAD="" uv run pytest -v
```

### Критерии приёмки (Acceptance Criteria):
- [x] Все 272 теста проходят со статусом `PASSED`.
- [x] Отсутствие предупреждений и ошибок линтера `ruff check .`.
- [x] 100% покрытие типов в строгом режиме `mypy` (strict mode, no issues).
- [x] Защита от перехвата loopback-трафика через переменную `LD_PRELOAD=""`.
- [x] Архитектурная готовность к разработке Фазы 6 (Resilience & Auto-Reconnect).

---

## 6. Заключение

Автономный аудит отряда «Семейка Адамс» подтвердил исключительную надежность фундамента Bridge Local. Все критические интерфейсы Phases 1–5 защищены от переполнения буферов, подмены криптографических подписей, атак повторного воспроизведения, атак выхода из каталога и конкурентных гонок.

**Проект полностью стабилизирован и готов к началу работ над Фазой 6!**
