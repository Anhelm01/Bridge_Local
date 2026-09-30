# Дневник разработки: Фаза 4 — Движок «Кармана» и «Записки» без костылей

**Дата:** 30 сентября 2026  
**Статус фазы:** Завершена успешно [OK]  
**Тесты:** 146 пройдены (24 новых теста: 11 Pocket, 6 Notes, 7 Integration)  
**Линтер / Формат:** 100% Ruff Clean  

---

## 1. О чём эта фаза и почему она особенная

Когда работаешь с двумя машинами — рабочей станцией на Linux и мощным ПК на Windows — больше всего бесит банальщина:
1. **Перекинуть файл:** Включать SMB/Samba на Linux? Танцы с бубном, правами доступа, портами 445 и Windows Network Discovery. Облако (Telegram, Google Drive, Яндекс.Диск)? Медленно, файлы улетают в интернет, нужен логин, ограничения по размеру.
2. **Перекинуть ссылку или сниппет текста:** Открывать браузер или мессенджер только ради того, чтобы закинуть PowerShell-команду или токен? Долго и неудобно.

Фаза 4 решает обе эти проблемы раз и навсегда через **«Карман» (Pocket Storage)** и **«Записки» (Notes)**.
Никаких сторонних сервисов, никаких сетевых папок ОС. Всё идёт по нашему собственному лёгкому протоколу поверх TCP с полным контролем над байтами.

---

## 2. Архитектура под капотом: как мы рассуждали

### 2.1. «Карман» (Pocket Engine): Чанки, SHA-256 и атомарность

Главный страх при передаче файлов по сети — получить недокачанный или битый файл, который перезапишет оригинал.

Вот как мы это спроектировали в [`PocketManager`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py):
1. **Нарезка на чанки по 64 КБ:** Файл любого размера (хоть 10 КБ, хоть 1 ГБ) передаётся блоками по 64 КБ в Base64 через RPC методы `pocket.pull` и `pocket.push`. Память процесса не забивается даже на огромных файлах.
2. **Атомарная запись через `.<filename>.part`:**
   - Пока файл передаётся, данные пишутся во временный скрытый файл `.<filename>.part`.
   - Если передача прервётся на середине, в папке не останется огрызка под видом готового файла.
3. **Строгая сверка SHA-256 перед фиксацией:**
   - С последним чанком (`is_last=True`) клиент отправляет полный ожидаемый хеш `sha256_full`.
   - Сервер локально пересчитывает SHA-256 временного файла.
   - Если хеш совпал тютелька в тютельку — вызывается атомарный системный вызов `os.replace(part_file, target_path)`. Файл появляется в целевой директории мгновенно!
   - Если хеш хоть на один бит отличается (битая сеть, модификация на лету) — временный `.part` немедленно удаляется с диска, операция бракуется с кодом ошибки `POCKET_SYNC_ERROR`, а в аудит-лог пишется алерт об инциденте целостности.

### 2.2. Защита служебных данных (Logs и Notes)

В «Кармане» живут не только файлы пользователя, но и инфраструктура:
- `pocket/logs/YYYY-MM-DD.jsonl` — ежедневные аудит-логи выполнения команд и передачи данных.
- `pocket/.notes/notes.jsonl` — база быстрых заметок.

**Проблема:** Если запустить синхронизацию кармана «в лоб», эти служебные файлы попадут в манифест и начнут бесконечно синхронизироваться и конфликтовать между Linux и Windows!

**Решение:** В [`PocketManager.scan_manifest()`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py) мы жёстко зашили изоляцию:
- Каталоги из списка `DEFAULT_IGNORED_NAMES` (`logs`, `.git`, `.tmp`, `__pycache__`) исключаются на уровне обхода дерева каталогов `os.walk`.
- Любые скрытые папки (начинающиеся с точки, включая `.notes`) и скрытые файлы (включая временные `*.part`) полностью игнорируются сканером манифеста.
- Пользователь видит только свои файлы, а система надёжно изолирована.

### 2.3. Двусторонняя синхронизация и разрешение конфликтов (`sync_pocket`)

Мы реализовали движок дифференциации [`PocketManager.compare_manifests()`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py):
- Файлы сравниваются по относительному пути и SHA-256.
- Если файла нет на удалённом узле — отправляем в `to_push`.
- Если файла нет локально — отправляем в `to_pull`.
- **Конфликт (файл изменён на обоих концах с разным SHA):** автоматически побеждает версия с более свежим временем модификации (`mtime_iso`), сохраняя непрерывность работы.
- А в [`sync_pocket()`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py) мы упаковали всё в одну асинхронную функцию: она запрашивает манифест, вычисляет diff, порционно прокачивает чанки с контролем целостности и возвращает красивую статистику (`PocketSyncSummary`).

### 2.4. Watchdog с дебаунсом (Debounced Watcher)

Когда пользователь или скрипт копирует в карман папку с 50 файлами, события файловой системы сыплются лавиной. Если реагировать на каждое событие сокетом — мы устроим сетевой шторм.
Мы внедрили [`PocketWatcher`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py) на базе `watchdog`:
- Он перехватывает события в фоновом системном потоке, передаёт их в `asyncio`-цикл через `call_soon_threadsafe`.
- Таймер дебаунса (по умолчанию 0.5 сек) сбрасывается при каждом новом чихе в файловой системе.
- И только когда запись на диск затихает — одним вызовом триггерится обработка всего пакета изменённых путей.

### 2.5. «Записки» (Notes Engine)

Быстрые текстовые заметки и ссылки реализованы в [`NotesManager`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/notes.py):
- Хранилище: чистый JSONL в `pocket/.notes/notes.jsonl`.
- Каждая запись — самодостаточный JSON: `note_id` (UUIDv4), `timestamp` (ISO-8601 UTC), `author_os` (`linux` / `windows`), `text`, `status` (`delivered` / `read`).
- Атомарный append с `flush()` и `os.fsync()`.
- Квитирование прочтения (`notes.mark_read`): атомарная перезапись файла через `.tmp` и `os.replace()`.
- Устойчивость к сбоям: если в файл случайно попадёт битая строка, парсер просто аккуратно пропустит её с предупреждением в лог, не ломая чтение остальных записок.

---

## 3. Что добавлено и обновлено в коде

| Модуль | Что делает |
| :--- | :--- |
| [`src/bridge_core/pocket.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/pocket.py) | Ядро «Кармана»: `compute_file_sha256`, `PocketManager` (scan, read/write chunk, compare), `PocketWatcher`, `sync_pocket`. |
| [`src/bridge_core/notes.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/notes.py) | Ядро «Записок»: `NotesManager` (добавление, история с пагинацией/фильтром `since`, квитирование `mark_read`). |
| [`src/bridge_core/models.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/models.py) | Модели DTO: `PocketPullResult`, `PocketPushResult`, `NoteMarkReadParams`, `NoteMarkReadResult`, методы `RpcMethod`. |
| [`src/bridge_core/transport.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/transport.py) | Эргономичный метод `client.call(method, params)` и алиас `client.disconnect()`. |
| [`src/bridge_agent_win/service.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_agent_win/service.py) | Интеграция обработчиков `pocket.*` и `notes.*`, аудит-логирование каждого чиха в JSONL. |
| [`tests/unit/test_pocket.py`](file:///home/anhelm/Projects/Bridge_Local/tests/unit/test_pocket.py) | 11 модульных тестов Pocket: чанки, SHA-256, path traversal, игнор логов, watchdog debounce. |
| [`tests/unit/test_notes.py`](file:///home/anhelm/Projects/Bridge_Local/tests/unit/test_notes.py) | 6 модульных тестов Notes: добавление, история, since-фильтрация, маркер прочтения, параллельные запросы. |
| [`tests/integration/test_pocket_sync.py`](file:///home/anhelm/Projects/Bridge_Local/tests/integration/test_pocket_sync.py) | 7 интеграционных тестов: сквозная передача 512 КБ файла, бидирекшн sync, отлуп поддельного SHA, аудит-лог. |

---

## 4. Результаты тестов

Запуск полного тестового набора (`LD_PRELOAD="" uv run pytest`):
```text
============================= test session starts ==============================
collected 146 items

tests/integration/test_layer_interaction.py .....                        [  3%]
tests/integration/test_pocket_sync.py .......                            [  8%]
tests/unit/test_codec.py ..........                                      [ 15%]
tests/unit/test_config.py .................                              [ 26%]
tests/unit/test_executor.py ......                                       [ 30%]
tests/unit/test_logger.py .....                                          [ 34%]
tests/unit/test_models.py ........................................       [ 61%]
tests/unit/test_notes.py ......                                          [ 65%]
tests/unit/test_pocket.py ...........                                    [ 73%]
tests/unit/test_process_killer.py ...                                    [ 75%]
tests/unit/test_protocol.py ............                                 [ 83%]
tests/unit/test_security.py ............                                 [ 91%]
tests/unit/test_smoke.py ...                                             [ 93%]
tests/unit/test_transport_and_heartbeat.py .....                         [ 97%]
tests/unit/test_windows_service.py ....                                  [100%]

============================= 146 passed in 5.89s ==============================
```

Все 146 тестов пролетают меньше чем за 6 секунд.

---

## 5. Граничные случаи (Edge Cases), которые мы проверили

1. **Попытка Path Traversal при передаче файла:**
   - Передача `path="../../etc/shadow"` или `..\..\windows\system32` немедленно ловится `validate_safe_path()`, операция прерывается с ошибкой и не касается файлов вне кармана.
2. **Файл повреждён при передаче (битый бит или подмена):**
   - Тест `test_write_chunk_corrupted_sha256_rejection` и интеграционный тест `test_integration_pocket_tampered_sha_rejected` подтвердили: сервер сверяет SHA-256 с переданным, стирает временный `.part` файл и возвращает ошибку целостности. На диске не остаётся мусора.
3. **Параллельные запросы к «Запискам»:**
   - Тест `test_concurrent_add_notes` запускает 20 одновременных записей в файл через `asyncio.gather`. Благодаря `asyncio.Lock` и атомарному сбросу буфера ни одна запись не теряется и строки не перепутываются.
4. **Изоляция логов:**
   - Проверено тестом `test_scan_manifest_ignores_logs_and_hidden`: системные папки `logs/`, `.notes/` и временные файлы `*.part` никогда не попадают в синхронизацию.

---

## 6. Чеклист готовности (Definition of Done)

- [x] Потоковая передача файлов чанками по 64 КБ без блокировки сокета.
- [x] Проверка SHA-256 до и после передачи.
- [x] Атомарная запись через `.<filename>.part` и `os.replace()`.
- [x] Полная изоляция каталогов `pocket/logs/` и `pocket/.notes/`.
- [x] Механизм быстрого обмена текстом «Записки» с хранением в JSONL, фильтрацией и отметкой о прочтении.
- [x] Автоматическое отслеживание изменений файловой системы с дебаунсом (Watchdog).
- [x] Регистрация всех RPC методов в службе Windows (`pocket.manifest`, `pocket.pull`, `pocket.push`, `notes.send`, `notes.history`, `notes.mark_read`).
- [x] Сквозной аудит каждого действия в `pocket/logs/YYYY-MM-DD.jsonl`.
- [x] 100% прохождение тестов (146/146).
- [x] Полная чистота линтера и форматтера (`ruff check`, `ruff format`).

Всё готово к переходу на **Фазу 5 (Linux CLI & Terminal UI: `bridge-cli`)**!
