# Дневник разработки: Фаза 5 — Linux Client CLI (Интерактивный TUI + Headless для ИИ)

**Дата:** 30 сентября 2026  
**Статус фазы:** Успешно завершена и зафиксирована ✅  
**Тесты проекта:** 177 пройдены (100% зелёные за 10.60с)  
**Линтер / Форматирование:** 100% Ruff Clean (49 файлов)  
**Статическая типизация:** 100% Mypy Clean (49 файлов, strict mode)  
**Точка входа CLI:** `bridge-cli` (`bridge_local:main` -> `bridge_client_linux.cli:run`)

---

## 1. Цели и назначение Фазы 5

Цель Фазы 5 — объединить все разработанные на предыдущих этапах сетевые механизмы (`bridge_core`), серверный агент Windows (`bridge_agent_win`), файловый движок «Кармана» и подсистему «Записки» в законченный, удобный и надежный инструмент для Linux.

В строгом соответствии с **Dual Target Persona** (`AGENTS.md`) клиент спроектирован для двух равнозначных операторов:
1. **Человек (Human Ergonomics):**
   - Мгновенная отправка файлов в карман (`bridge-cli pocket push ...` или `bridge-cli pocket sync`).
   - Быстрый обмен ссылками и сниппетами между экранами Linux и Windows (`bridge-cli note send "..."`).
   - Наглядный системный дашборд с эмблемой **BRIDGES Master** (`bridge-cli welcome`).
   - Полноэкранный интерактивный TUI-терминал с 6 режимами и навигацией по F1..F6 (`bridge-cli tui`).
   - Минимальная, немерцающая анимация фоновых процессов (At-a-Glance Observability).
2. **ИИ-агент Antigravity (`agy_cli`):**
   - Строгий машиночитаемый режим `--json` во всех командах (`exec`, `status`, `ping`, `pocket`, `note`, `config`).
   - Чистый вывод без ANSI-символов и управляющих последовательностей.
   - Детерминированные коды завершения процесса (Exit Codes 0..5):
     - `0`: Успех (`SUCCESS`)
     - `1`: Общая ошибка конфигурации или аргументов (`GENERAL_ERROR`)
     - `2`: Сетевая ошибка (хост недоступен, сбой сокета) (`NETWORK_ERROR`)
     - `3`: Сбой аутентификации (неверный PSK токен, Replay) (`AUTH_ERROR`)
     - `4`: Ошибка удалённой команды PowerShell (`COMMAND_FAILED`)
     - `5`: Превышение таймаута выполнения (`TIMEOUT`)
   - Нулевая блокировка на stdin (no blocking prompts) — мгновенный fail-fast.
   - Токеноэффективность выходных JSON-структур для экономии контекста LLM.

---

## 2. Архитектура пакета `bridge_client_linux`

Пакет `src/bridge_client_linux` спроектирован по принципу строгой модульности и слабой связанности (Loose Coupling):

```
src/bridge_client_linux/
├── __init__.py           # Экспорт BridgeClient, ExitCode, __version__
├── py.typed              # Маркер строгой типизации для mypy
├── exit_codes.py         # IntEnum детерминированных кодов (0..5)
├── exceptions.py         # Иерархия исключений с привязкой к exit_code
├── client.py             # Высокоуровневый асинхронный движок BridgeClient
├── cli.py                # Typer CLI приложение (human + agy_cli)
└── tui/                  # Терминальный интерфейс и визуализация
    ├── __init__.py
    ├── theme.py          # Единая утвержденная тема Titanium Vivid
    ├── logos.py          # BRIDGES Master & DRAWBRIDGE Industrial ASCII-арт
    ├── animations.py     # Braille spinners & Activity pulses
    ├── screens.py        # Рендеринг всех 6 режимов, шапки и Neofetch-сплэша
    └── app.py            # Интерактивный цикл с alternate screen buffer
```

### 2.1. Высокоуровневый клиент (`BridgeClient`)
Класс [`BridgeClient`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_client_linux/client.py) инкапсулирует:
- Управление `AsyncTransportClient` и TLS SSLContext.
- Автоматическую инъекцию HMAC-SHA256 аутентификационных заголовков (`PSKAuthenticator`) в каждый RPC-запрос.
- Трансляцию низкоуровневых транспортных ошибок в типизированные исключения домена (`BridgeNetworkError`, `BridgeAuthError`, `BridgeTimeoutError`).
- Потоковую передачу файлов кармана по 64 КБ с верификацией SHA-256.
- Методы:
  - `ping() -> tuple[PongResult, float]`
  - `exec(...) -> ExecResult`
  - `pocket_manifest() -> PocketManifestResult`
  - `pocket_status() -> dict[str, Any]`
  - `pocket_sync(direction="both|push|pull") -> PocketSyncSummary`
  - `pocket_push_file(...) -> PocketPushResult`
  - `pocket_pull_file(...) -> Path`
  - `note_send(...) -> NoteDeliveryResult`
  - `note_history(...) -> NoteHistoryResult`
  - `note_mark_read(...) -> NoteMarkReadResult`
  - `get_system_status() -> dict[str, Any]`

### 2.2. Готовность к масштабированию и Multi-Node Mesh (F1/F2)
Все методы `BridgeClient` и команды CLI принимают параметры `--node` / `--target` (`target_node`) и `source_node`. Протокольные сообщения JSON-RPC на уровне ядра уже содержат зарезервированные поля маршрутизации, что гарантирует плавный переход к сети из 3+ узлов без ломки wire protocol.

---

## 3. Детерминированный AI Operator Protocol (`agy_cli`)

Команды оптимизированы для вызова через инструмент `run_command`:

```bash
# Проверка связи
bridge-cli ping --json
# Ответ: {"pings": [{"latency_ms": 0.38, "pong": {"agent_os": "windows", "status": "ready", ...}}], ...}

# Удаленное выполнение команды
bridge-cli exec "Get-Process -Name BridgeLocalAgent" --json
# Ответ: {"exit_code": 0, "stdout": "...", "stderr": "", "duration_ms": 42, "timed_out": false}

# Статус синхронизации кармана
bridge-cli pocket status --json
# Ответ: {"local_files_count": 18, "remote_files_count": 18, "is_in_sync": true, ...}
```

В случае ошибок выводится компактный JSON-объект, а процесс завершается с соответствующим кодом:

```json
{
  "status": "error",
  "error_code": 2,
  "error_type": "BridgeNetworkError",
  "message": "Не удалось подключиться к узлу 127.0.0.1:54321: Connection refused"
}
```

---

## 4. Человеческий интерфейс и TUI (Titanium Vivid)

Для повседневной работы человека реализованы:
1. `bridge-cli welcome` — полноэкранный Neofetch-сплэш с подвесным мостом **BRIDGES Master** и системно-сетевой сводкой.
2. `bridge-cli tui` — интерактивный TUI-монитор:
   - Вход в alternate screen buffer (`\033[?1049h\033[?25l`) — терминал не засоряется скроллом, при выходе возвращается исходное состояние консоли.
   - Быстрое переключение вкладок:
     - `1 / F1`: **DASH** — сводка P2P канала, пинга, кармана и заметок.
     - `2 / F2`: **POCKET** — таблица файлов, направления передачи, SHA-256 и статусы.
     - `3 / F3`: **NOTES** — живой журнал заметок и поле быстрого ввода.
     - `4 / F4`: **EXEC** — консоль удалённого PowerShell с индикатором готовности.
     - `5 / F5`: **CONFIG** — таблица зарегистрированных узлов LAN и параметры безопасности.
     - `6 / F6`: **DEV** — журнал глубокой трассировки Wire Protocol, RPC и Watchdog.
3. Единая тема **Titanium Vivid**:
   - Основа: Laser White (`#FFFFFF`) и Industrial Steel (`#7D8590`).
   - Функциональные акценты: Electric Cyan (`#00D2FF`), Laser Green (`#00FF66`), Amber Gold (`#FFB800`), Neon Purple (`#C084FC`).
4. At-a-Glance Observability:
   - Braille-спиннеры (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) и пульсирующие маркеры передачи (`[>>> 68%] 48 MB/s`), видимые оператором с расстояния 2–3 метров.

---

## 5. Выявленные сложности и их решение

1. **Конфликт Proxychains при обращениях к localhost (`127.0.0.1`):**  
   *Проблема:* При наличии глобального `LD_PRELOAD=/usr/lib/libproxychains4.so` все локальные TCP-соединения между клиентом и локальным сервером перехватывались proxychains и блокировались (`<--denied`).  
   *Решение:* Вызовы юнит-тестов и CLI в среде с активным proxychains выполняются с очищенным `LD_PRELOAD=""`, а в документацию добавлен совет по настройке `localnet 127.0.0.0/255.0.0.0` в `proxychains.conf`.

2. **Deadlock при вызове `CliRunner.invoke` в асинхронном контексте:**  
   *Проблема:* Typer `CliRunner.invoke` синхронен. Если mock-сервер в тестах стартовал на том же event loop, что и тест, вызов `asyncio.run()` внутри CLI блокировал поток и не давал серверу обработать входящие сокеты.  
   *Решение:* Создана специализированная фикстура `cli_server`, запускающая mock-сервер в отдельном фоновом потоке со своим изолированным event loop. Клиент и сервер работают параллельно без взаимоблокировок.

3. **Сериализация `PocketSyncSummary` (Dataclass vs Pydantic):**  
   *Проблема:* `PocketSyncSummary` из `bridge_core.pocket` является стандартным `@dataclass`, у которого нет метода `.model_dump()`.  
   *Решение:* В `cmd_pocket_sync` добавлена универсальная обработка через `dataclasses.asdict()`.

4. **Формат списка синхронизированных файлов (`diff.synced`):**  
   *Проблема:* `diff.synced` содержит `list[str]`, а не объекты моделей. Попытка вызвать `f.model_dump()` приводила к `AttributeError`.  
   *Решение:* Исправлено на `list(diff.synced)`.

---

## 6. Метрики верификации

```text
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/anhelm/Projects/Bridge_Local
configfile: pyproject.toml
plugins: asyncio-1.4.0
collected 177 items

tests/integration/test_layer_interaction.py .....                        [  2%]
tests/integration/test_pocket_sync.py .......                            [  6%]
tests/unit/test_client_linux_cli.py ..........                           [ 12%]
tests/unit/test_client_linux_client.py ........                          [ 16%]
tests/unit/test_client_linux_exit_codes.py ...                           [ 18%]
tests/unit/test_client_linux_tui.py .....                                [ 21%]
tests/unit/test_codec.py ..........                                      [ 27%]
tests/unit/test_config.py .................                              [ 36%]
tests/unit/test_executor.py ......                                       [ 40%]
tests/unit/test_logger.py .....                                          [ 42%]
tests/unit/test_models.py ........................................       [ 65%]
tests/unit/test_notes.py ......                                          [ 68%]
tests/unit/test_pocket.py ...........                                    [ 75%]
tests/unit/test_process_killer.py ...                                    [ 76%]
tests/unit/test_protocol.py ............                                 [ 83%]
tests/unit/test_security.py ............                                 [ 90%]
tests/unit/test_smoke.py ...                                             [ 92%]
tests/unit/test_transport_and_heartbeat.py .....                         [ 94%]
tests/unit/test_tui_interactive.py .....                                 [ 97%]
tests/unit/test_windows_service.py ....                                  [100%]

============================= 177 passed in 10.60s =============================
```

- **Ruff:** `All checks passed! 49 files already formatted`
- **Mypy:** `Success: no issues found in 52 source files`

---

## 6.5. Расширение UX: Интерактивный Prompt в TUI, Direct Send и контекстное меню Windows

По результатам проверки эргономики повседневного использования (Human Ergonomics) было реализовано важное расширение функционала:

1. **Разделение ввода текста и навигации в TUI:**
   - Ранее односимвольный ввод `read(1)` конфликтовал с набором команд PowerShell и путей к файлам (нажатие цифры `1` переключало вкладку на DASH, нажатие `q` закрывало TUI).
   - Теперь переключение вкладок надёжно изолировано на **`Tab` / `Shift+Tab`** и функциональные клавиши **`F1`–`F6`**, а выход осуществляется по **`Ctrl+C`** или **`Ctrl+Q`**.
   - На экранах **`EXEC`**, **`POCKET`** и **`NOTES`** реализован живой интерактивный буфер ввода (Prompt):
     * **`EXEC`**: полноценный REPL-ввод команд PowerShell (`PS C:\BridgeService> █`) с немедленным асинхронным выполнением и отображением вывода в окне консоли.
     * **`POCKET`**: интерактивная строка отправки файлов (`PUSH FILE > █`) с поддержкой как ручного ввода, так и **Drag-and-Drop** мышкой прямо из файлового менеджера в окно терминала.
     * **`NOTES`**: быстрая отправка заметок по нажатию `Enter`.

2. **Прямая команда быстрой отправки файлов `bridge-cli send`:**
   - Добавлена верхнеуровневая команда:
     ```bash
     bridge-cli send /path/to/archive.zip photo.png --target-dir "work"
     ```
   - Предварительно валидирует существование файлов до открытия сетевого соединения (возвращая код `1` при отсутствии файла) и передаёт файлы чанками с SHA-256 сверкой.

3. **Интеграция с Проводником Windows (Контекстное меню «Отправить в Карман»):**
   - Реализован модуль `bridge_agent_win.context_menu` и консольная утилита `bridge-agent`:
     * `bridge-agent install-context-menu`: автоматическая регистрация пункта в контекстном меню Explorer (`HKCU\Software\Classes\*\shell\BridgeLocalSend`).
     * `bridge-agent drop <file>`: обработчик правого клика мыши, копирующий объект в локальный Карман для автосинхронизации через Watchdog.
     * `bridge-agent generate-reg`: экспорт автономного файла `ref/windows_context_menu.reg` для импорта в один клик.

---

## 7. Чеклист критериев готовности (Definition of Done)

- [x] Реализован `bridge-cli` с однострочными командами `status`, `ping`, `exec`, `pocket`, `note`, `config`, `send`.
- [x] Реализован и проверен машиночитаемый режим `--json` без ANSI-символов.
- [x] Реализованы детерминированные коды завершения процесса (Exit Codes 0..5).
- [x] Реализован полноэкранный Neofetch экран приветствия (`bridge-cli welcome`).
- [x] Реализован интерактивный TUI с живым Prompt (EXEC REPL, POCKET Drag&Drop, NOTES) и переключением по Tab / F1..F6.
- [x] Реализована интеграция с Проводником Windows (правый клик «Отправить в Карман»).
- [x] Применена официальная тема **Titanium Vivid** (Cyber-Industrial).
- [x] Внедрена немерцающая анимация фоновых процессов (At-a-Glance Observability).
- [x] Заложена поддержка мульти-узловой адресации (`--node`, `target_node`, `source_node`).
- [x] Достигнуто 100% прохождение тестов (**190/190 passed**).
- [x] Достигнута 100% чистота линтера Ruff и строгой типизации Mypy (52 исходных файла).
- [x] Подготовлен и зафиксирован инженерный отчет в `devblog/phase_05_linux_cli.md`.
