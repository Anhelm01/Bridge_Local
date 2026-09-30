# Фаза 7: Сборка, упаковка и развертывание (Packaging & Production Deployment)

**Дата:** 30 сентября 2026  
**Статус:** Завершена [OK]  
**Тесты:** 311 пройден (100% green)  
**Линтер / Форматирование:** 100% Ruff Clean (81 файл проверен и отформатирован)  
**Статическая типизация:** 100% Mypy Clean (strict mode, 33 исходных файла)  

---

## 1. Цели и задачи Фазы 7

Финальная Фаза 7 SDLC переводит кодовую базу Bridge Local в состояние полноценного готового дистрибутива, готового к промышленному развертыванию на узлах оператора (Linux) и удаленного исполнителя (Windows):
1. **Упаковка Windows-агента:**
   - Разработка спецификации автономной сборки PyInstaller (`bridge-agent.spec`) и скрипта автоматической компиляции `scripts/build-windows-agent.ps1` в единый бинарник `bridge-agent.exe`.
   - Поддержка нативной системной службы Windows SCM (`win32serviceutil.ServiceFramework`) в `bridge_agent_win.service` с командами управления `bridge-agent service [install|start|stop|remove]`.
   - Разработка скрипта автоматического развертывания `scripts/install-service.ps1`: регистрация службы `BridgeLocalAgent` в SCM, настройка автозапуска, настройка политики автоматического восстановления (`sc.exe failure`), добавление исключений Windows Defender (`Add-MpPreference`), отключение индексирования Windows Search на каталоге `pocket` (устранение файловых коллизий `WinError 32`), настройка правила брандмауэра (`New-NetFirewallRule`).
   - Скрипт безопасной деинсталляции `scripts/uninstall-service.ps1`: штатная остановка (`Stop-Service`), удаление службы из реестра SCM, очистка Defender и правил брандмауэра.
2. **Пакетирование и дистрибуция Linux-клиента:**
   - Настройка многопакетной сборки wheel-дистрибутива (`pyproject.toml`) с включением всех четырех компонентов платформы (`bridge_core`, `bridge_agent_win`, `bridge_client_linux`, `bridge_local`).
   - Точки входа `bridge-cli` и `bridge-agent`, модульный запуск через `python -m <package>`.
   - Проверка чистой установки через `uv tool install .` и `pip install dist/*.whl` в изолированном виртуальном окружении.
3. **Разделение Dev-Mode Hyper-Logging и Release Clean Mode:**
   - Гарантированное переключение режимов через `bridge.toml`: при `dev_mode = false` логирование автоматически переключается на чистый уровень `INFO`, строковый формат очищается от микросекундных таймстемпов и номеров строк кода, а детальные побайтовые дампы сетевых фреймов, дампы чанков иfsync-метрики полностью подавляются.
   - При `dev_mode = true` сохраняется глубокая TRACE-диагностика с микросекундным разрешением.
4. **Эксплуатационная документация и шаблоны systemd:**
   - Исчерпывающее руководство администратора `docs/DEPLOYMENT.md`.
   - Шаблоны системных юнитов `scripts/systemd/bridge-client-sync.service` и `scripts/systemd/bridge-agent.service`.
   - Обновление `README.md` и `docs/SDLC_PLAN.md`.

---

## 2. Реализованные компоненты и архитектурные решения

### 2.1. Спецификация PyInstaller и автономный бинарник (`bridge-agent.spec`)
* Создан файл спецификации PyInstaller `bridge-agent.spec` для компиляции Windows-агента в автономный исполняемый файл `bridge-agent.exe`.
* Спецификация включает все внутренние подсистемы (`bridge_core`, `bridge_agent_win`, `pydantic`, `watchdog`, `psutil`, `win32*`) и исключает клиентские Linux-зависимости (Typer, Rich, Pytest).
* Создан PowerShell скрипт сборки `scripts/build-windows-agent.ps1` с очисткой временных каталогов, расчетом размера и SHA-256 хеша готового бинарника.

### 2.2. Системная служба Windows SCM и скрипты PowerShell (`scripts/`)
* **Класс `BridgeLocalAgentWindowsService`:** В `src/bridge_agent_win/service.py` реализован наследник `win32serviceutil.ServiceFramework`, позволяющий агенту работать как полноценная служба Windows до входа пользователя в систему, корректно реагируя на события `SERVICE_CONTROL_STOP` и `SHUTDOWN`.
* **Скрипт `scripts/install-service.ps1`:**
  - UAC Elevation: проверка прав Администратора с fail-fast остановкой.
  - Автопоиск бинарного файла: проверяет переданный путь, каталог установки, dist/ или `bridge-agent` на PATH, с fallback на `python.exe -m bridge_agent_win run`.
  - Генерация релизной конфигурации `bridge.toml` (`dev_mode = false`, `level = "INFO"`).
  - Исключения Windows Defender: `Add-MpPreference -ExclusionPath` для каталога установки и кармана, `Add-MpPreference -ExclusionProcess` для бинарного процесса.
  - Устранение коллизий Windows Search: рекурсивная установка атрибута `[System.IO.FileAttributes]::NotContentIndexed` на каталог `pocket` — ликвидирует захват дескрипторов файлов процессом `SearchIndexer.exe` и ошибки `WinError 32: ERROR_SHARING_VIOLATION`.
  - Брандмауэр Windows: создание входящего правила `Bridge Local Daemon (TCP-In)` для порта 9732 TCP.
  - Регистрация в SCM: создание службы `New-Service` с автоматическим типом запуска (`Automatic`) и настройкой политики перезапуска при сбоях `sc.exe failure reset= 86400 actions= restart/5000/restart/10000/restart/60000`.
  - Запуск и проверка статуса службы.
* **Скрипт `scripts/uninstall-service.ps1`:**
  - Корректная остановка службы с тайм-аутом (`Stop-Service -Force`).
  - Удаление регистрации службы из SCM (`sc.exe delete`).
  - Очистка исключений Windows Defender (`Remove-MpPreference`).
  - Удаление правила брандмауэра (`Remove-NetFirewallRule`).

### 2.3. Пакетирование Wheel и поддержка `uv tool install`
* В ходе аудита Фазы 7 была выявлена и устранена критическая особенность стандартного бекенда: при сборке проекта с именем `bridge-local` в архив по умолчанию попадал только подпакет `bridge_local`, пропуская `bridge_core`, `bridge_client_linux` и `bridge_agent_win`.
* Конфигурация сборки в `pyproject.toml` была скорректирована для включения всех 4 пакетов:
  `packages = ["src/bridge_core", "src/bridge_agent_win", "src/bridge_client_linux", "src/bridge_local"]`.
* В `dependencies` добавлены кросс-платформенные зависимости интерфейса (`typer`, `rich`, `psutil`) и платформа-маркер `pywin32>=310; sys_platform == 'win32'`.
* Добавлены модульные точки входа `__main__.py` во все пакеты:
  - `src/bridge_local/__main__.py`
  - `src/bridge_client_linux/__main__.py`
  - `src/bridge_agent_win/__main__.py`
* Успешно проверена сквозная установка собранного wheel-пакета в абсолютно чистый временный virtualenv с запуском `bridge-cli --help`.

### 2.4. Релизный режим логирования (Release Clean Mode)
* В `src/bridge_core/logger.py`:
  - Функция `setup_logging` при `dev_mode = false` автоматически понижает уровень логирования по умолчанию с TRACE до чистого `INFO` и переключает формат логов на лаконичный: `YYYY-MM-DD HH:MM:SS | LEVEL | Сообщение` (без микросекундных хвостов и строк кода).
  - В `AtomicJsonlLogger` добавлен параметр `dev_logging`: при отключенном режиме отладки логгер не формирует подробные отладочные сообщения с микросекундами fsync.
  - В `WindowsBridgeService` параметр `self.config.logging.dev_mode` транслируется во все внутренние подсистемы: сокет-транспорт, файловый менеджер кармана, менеджер заметок и исполнитель команд.

### 2.5. Устранение эффекта перехвата waitpid в process_killer
* При интеграции `psutil` для сбора системных метрик было обнаружено, что метод `psutil.wait_procs` внутри `kill_process_tree` вызывал `os.waitpid` на дочерних процессах, перехватывая их код завершения у родительского `subprocess.Popen`. В результате `Popen.wait()` возвращал код `0` вместо сигнального кода `-9`.
* Поведение было исправлено без использования `wait_procs`: теперь `kill_process_tree` отслеживает статус `proc.is_running()` и `STATUS_ZOMBIE`, не перехватывая `os.waitpid`, что сохраняет корректный код завершения у вызывающего процесса.

---

## 3. Результаты тестирования

Создан комплекс тестов упаковки и развертывания [`tests/unit/test_packaging_and_deployment.py`](../tests/unit/test_packaging_and_deployment.py) (24 теста) и расширены тесты надежности уничтожения процессов в [`tests/unit/test_process_killer.py`](../tests/unit/test_process_killer.py):
* Проверка структуры и метаданных `pyproject.toml` (консольные скрипты, зависимости, wheel пакеты).
* Проверка импортируемости и работоспособности `__main__.py` всех трех пакетов.
* Проверка AST-синтаксиса и директив спецификации `bridge-agent.spec`.
* Проверка PowerShell скриптов `install-service.ps1`, `uninstall-service.ps1`, `build-windows-agent.ps1` на наличие всех обязательных параметров, команд SCM (`service-run`), Defender, Firewall, Search Indexing и полное отсутствие эмодзи.
* Проверка валидности системных юнитов `systemd`.
* Проверка переключения режимов логирования: установка уровня TRACE и микросекундного формата при `dev_mode=True`, чистого уровня INFO без микросекунд при `dev_mode=False`.
* Проверка CLI-команд агента `bridge-agent` (`run`, `service-run`, `service`, `generate-reg`, `drop`).
* Проверка передачи аргументов в `win32serviceutil.HandleCommandLine` с сохранением имени программы в `argv[0]`.
* Проверка инициализации SCM диспетчера `servicemanager.StartServiceCtrlDispatcher`.
* Проверка жизненного цикла системной службы `BridgeLocalAgentWindowsService` (`SERVICE_RUNNING`, `SERVICE_STOP_PENDING`, `SERVICE_STOPPED`).
* Проверка разрешения путей конфигурации `BridgeConfig.load` (переменная окружения `BRIDGE_CONFIG`, fallback-пути).
* Проверка уничтожения дерева процессов (родитель + дочерние ветви) без перехвата `os.waitpid`.

### Общий прогон тестов проекта
```
tests/integration/test_layer_interaction.py .....                        [  1%]
tests/integration/test_pocket_sync.py .......                            [  3%]
tests/integration/test_resilience_simulation.py ..............           [  8%]
tests/unit/test_adams_family_edge_cases.py ............................. [ 17%]
...........................................                              [ 31%]
tests/unit/test_client_linux_cli.py .............                        [ 35%]
tests/unit/test_client_linux_client.py ........                          [ 38%]
tests/unit/test_client_linux_exit_codes.py ...                           [ 39%]
tests/unit/test_client_linux_tui.py ......                               [ 41%]
tests/unit/test_codec.py ..........                                      [ 44%]
tests/unit/test_config.py .................                              [ 49%]
tests/unit/test_executor.py ......                                       [ 51%]
tests/unit/test_logger.py .....                                          [ 53%]
tests/unit/test_models.py ........................................       [ 66%]
tests/unit/test_notes.py ......                                          [ 68%]
tests/unit/test_packaging_and_deployment.py ........................     [ 75%]
tests/unit/test_pocket.py ...........                                    [ 79%]
tests/unit/test_process_killer.py ....                                   [ 80%]
tests/unit/test_protocol.py ............                                 [ 84%]
tests/unit/test_security.py ............                                 [ 88%]
tests/unit/test_smoke.py ...                                             [ 89%]
tests/unit/test_transport_and_heartbeat.py .....                         [ 90%]
tests/unit/test_transport_and_storage_fuzzing.py ..........              [ 94%]
tests/unit/test_tui_interactive.py .....                                 [ 95%]
tests/unit/test_win_context_menu.py .........                            [ 98%]
tests/unit/test_windows_service.py ....                                  [100%]

============================= 311 passed in 14.31s =============================
```

* **Ruff linter:** All checks passed (81 файл).
* **Ruff format:** 81 файл отформатирован.
* **Mypy strict:** Success: no issues found in 33 source files.

---

## 4. Чеклист готовности (Definition of Done)

- [x] Автономная сборка агента Windows описана в `bridge-agent.spec` и автоматизирована в `scripts/build-windows-agent.ps1`.
- [x] Системная служба Windows SCM (`win32serviceutil.ServiceFramework`) интегрирована в `bridge_agent_win.service` с поддержкой `service-run`, корректным оповещением SCM (`SERVICE_RUNNING` / `SERVICE_STOPPED`) и автоопределением SCM.
- [x] Производственные скрипты `install-service.ps1` и `uninstall-service.ps1` созданы, протестированы и содержат настройку SCM (`service-run`), автозапуска, Defender exclusions, отключения Windows Search Indexing и правил брандмауэра.
- [x] Сборка wheel-пакета проверена: все 4 подпакета (`bridge_core`, `bridge_agent_win`, `bridge_client_linux`, `bridge_local`) включены в дистрибутив.
- [x] Чистая установка пакета через `uv tool` и `pip` проверена в изолированном venv.
- [x] Разделение Dev-Mode Hyper-Logging и Release Clean Mode реализовано и покрыто тестами.
- [x] Полное руководство администратора составлено в `docs/DEPLOYMENT.md`.
- [x] `README.md` и `docs/SDLC_PLAN.md` актуализированы.
- [x] 311 тестов пройдены (100% green), 0 ошибок Ruff, 0 ошибок Mypy.
- [x] Правило Invariant Rule 9 соблюдено: git commit и git push не выполнялись, все изменения сохранены в локальном рабочем каталоге.
