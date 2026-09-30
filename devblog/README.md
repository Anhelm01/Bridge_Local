# Инженерный журнал разработки (devblog/)

В этом каталоге фиксируются отчеты по завершении каждой фазы и ключевой подфазы разработки.  
Девблог ведётся живым языком разработчиков — с описанием хода мыслей, реальных инженерных челленджей, метрик и чеклистов готовности.

---

## [INDEX] Навигатор по фазам проекта

| Фаза | Название | Статус | Отчёт в девблоге | Ключевые результаты |
| :--- | :--- | :---: | :--- | :--- |
| **Фаза 0** | Инициализация и правила | [OK] | [00_init_and_planning.md](file:///home/anhelm/Projects/Bridge_Local/devblog/00_init_and_planning.md) | Репозиторий, uv, pyproject.toml, AGENTS.md, SDLC_PLAN.md |
| **Фаза 1** | Контракты и DTO | [OK] | [phase_01_contracts.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_01_contracts.md) | Pydantic V2 модели, TOML конфиг, 60 тестов |
| **Фаза 2** | Базовое ядро (Bridge Core) | [OK] | [phase_02_core.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_02_core.md) | Длина-префикс протокол, TCP/TLS транспорт, Fail-Fast Heartbeat, JSONL логгер, 104 теста |
| **Фаза 3** | Windows Agent & Служба | [OK] | [phase_03_win_agent.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_03_win_agent.md) | PowerShell Runner (UTF-8), Process Tree Killer, Windows Service Daemon, сквозная интеграция, 122 теста |
| **Фаза 4** | «Карман» и «Записки» | [OK] | [phase_04_pocket_notes.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_04_pocket_notes.md) | Чанковая передача (64 КБ), сверка SHA-256, атомарная запись, Watchdog дебаунс, Notes JSONL, 146 тестов |
| **Подфаза 4.5** | UI/UX & Visual Identity | [OK] | [phase_04_5_ui_ux_identity.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_04_5_ui_ux_identity.md) | Единая тема Titanium Vivid, 2-логотипная система (Master + Industrial), анимации процессов, preview-стенд |
| **Фаза 5** | Linux Client CLI & TUI | [OK] | [phase_05_linux_cli.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_05_linux_cli.md) | Typer CLI, Headless JSON, Exit Codes 0..5, TUI 6 режимов, 177 тестов |
| **Фаза 6** | Отказоустойчивость | [OK] | [phase_06_resilience.md](file:///home/anhelm/Projects/Bridge_Local/devblog/phase_06_resilience.md) | Докачка файлов (.part offset), Windows Sharing Violation retry, Fail-fast сон (1.5с), 286 тестов |
| **Фаза 7** | Релиз и дистрибуция | [IN PROGRESS] *В очереди* | `phase_07_release.md` | PyInstaller standalone .exe, инсталлятор службы, чистая изоляция dev-логов |

---

## Структура каждого отчета
1. **Цель фазы/подфазы:** Что планировалось реализовать.
2. **Выполненные работы:** Перечень созданных модулей, функций, интерфейсов.
3. **Логирование и трассировка (Dev-Mode):** Какие логгеры и точки контроля добавлены.
4. **Результаты тестирования:** Запуск юнит/интеграционных тестов, логи прохождения, время выполнения.
5. **Выявленные сложности и краевые случаи:** Что потребовало корректировки.
6. **Готовность к следующей фазе:** Чеклист критериев приёмки (Definition of Done).
