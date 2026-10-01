# Портал документации Bridge_local

Добро пожаловать в центральный репозиторий технической документации и руководств платформы **Bridge_local**.

Платформа представляет собой модульную, масштабируемую систему межмашинного взаимодействия и агентной оркестрации между узлами под управлением Linux и Windows.

---

## Навигация по документации

### 1. Для разработчика и оператора (Обучалка и быстрый старт)
- [**Обучалка по dev-взаимодействию (Пошаговый гид простыми словами)**](file:///home/anhelm/Projects/Bridge_Local/docs/DEV_GUIDE_FOR_HUMANS.md)
  *Пошаговое руководство по настройке, первому запуску, повседневному использованию, отладке, dev-режиму и решению проблем без сложной терминологии.*

### 2. Системные руководства
- [**Руководство по развертыванию и администрированию (DEPLOYMENT.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/DEPLOYMENT.md)
  *Установка Windows SCM службы, настройка Windows Defender и Брандмауэра, интеграция в контекстное меню Explorer, системные юниты systemd на Linux.*
- [**Справочник по конфигурации (CONFIGURATION.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/CONFIGURATION.md)
  *Подробное описание всех секций `bridge.toml`: [node], [network], [security], [pocket], [notes], [executor], [logging], каскадный поиск и переменные окружения.*
- [**Справочник интерфейса командной строки (CLI_REFERENCE.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/CLI_REFERENCE.md)
  *Полный каталог команд `bridge-cli` и `bridge-agent`, флаги, детерминированный `--json` режим, коды завершения (Exit Codes) и горячие клавиши TUI.*

### 3. Архитектура и спецификации
- [**Архитектурный обзор платформы (ARCHITECTURE.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/ARCHITECTURE.md)
  *Слоистая модель, принципы модульности, автономность `bridge_core`, потоковая передача файлов, изоляция процессов и многоузловая топология.*
- [**Спецификация сетевого протокола (PROTOCOL_SPEC.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/PROTOCOL_SPEC.md)
  *Бинарный фрейминг (длина + JSON-RPC 2.0), конверты безопасности HMAC-SHA256, каталог удаленных методов (RPC), схемы DTO и обработка ошибок.*
- [**План разработки и вехи (SDLC_PLAN.md)**](file:///home/anhelm/Projects/Bridge_Local/docs/SDLC_PLAN.md)
  *Фазы жизненного цикла проекта от контрактов (Фаза 1) до развертывания (Фаза 7) и дорожной карты многоузловой сети (Фазы F1-F2).*
---

## Архитектурные принципы платформы

```
+------------------------------------------------------------------------+
|                        BRIDGE_LOCAL PLATFORM                           |
+---------------------+--------------------------------------------------+
| Security Layer      | HMAC-SHA256, Nonce Replay Cache, Clock Skew Sync |
| Wire Protocol       | 6-byte Magic Framing ('BR'), Length-Prefix Codec |
| Transport & RPC     | Asyncio TCP Streaming, JSON-RPC 2.0 Dispatcher   |
| Execution Engine    | PowerShell Runner, Process Tree Killer, UTF-8    |
| Pocket Storage      | 64 KB Chunk Streaming, SHA-256 Verify, Atomic    |
| Notes Subsystem     | Persistent JSONL Engine, Filter & Acknowledgment |
| Operator Layer      | Human TUI (Titanium Vivid) + AI Headless --json  |
+---------------------+--------------------------------------------------+
```

1. **Строгая модульность и взаимозаменяемость:** Ядро `bridge_core` не зависит от платформо-специфичного кода Windows или Linux и может быть извлечено как автономная библиотека.
2. **Безопасность первого класса:** Никакой незашифрованной передачи команд без криптографической проверки подписи (HMAC-SHA256) и защиты от атак повторного воспроизведения (Anti-replay nonce cache).
3. **Двойная персона оператора:** Человеческий интерфейс ориентирован на мгновенное действие в одну команду (`send`, `note`, `tui`), а интерфейс для ИИ-агентов (`agy_cli`) гарантирует строгий машиночитаемый JSON и детерминированные коды завершения.
