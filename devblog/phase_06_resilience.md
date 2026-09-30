# Фаза 6: Отказоустойчивость, краевые случаи и самовосстановление (Resilience & Self-Healing)

**Дата:** 30 сентября 2026  
**Статус:** Завершена [OK]  
**Тесты:** 286 пройдены (100% green)  
**Линтер / Форматирование:** 100% Ruff Clean  
**Статическая типизация:** 100% Mypy Clean (strict mode, 30 исходных файлов)  

---

## 1. Цели и задачи Фазы 6

Фаза 6 превращает Bridge_local из прототипа в промышленно-надежную платформу межмашинного взаимодействия, устойчивую к:
1. Внезапным обрывам сети (Wi-Fi drop, физический кабель, смена IP, дрожание MTU).
2. Уходу Windows в сон или гибернацию (Sleep/Hibernate) с мгновенным (<= 1.5 сек) fail-fast обнаружением на стороне Linux CLI.
3. Докачке частично переданных файлов (Resumable Transfers) без повторной отправки уже полученных байтов.
4. Коллизиям совместного доступа к файлам в Windows (Windows Sharing Violation, `WinError 32: ERROR_SHARING_VIOLATION`, `EBUSY`, файловые блокировки антивирусов и индексаторов).

---

## 2. Архитектурные решения и компоненты

### 2.1. Механизм повторов с экспоненциальным бэкоффом (`bridge_core.retry`)
Создан специализированный модуль [`src/bridge_core/retry.py`](../src/bridge_core/retry.py):
* **Детектор коллизий (`is_sharing_violation`):** Распознает `PermissionError`, `OSError` с `winerror == 32`, `errno.EBUSY`, `errno.EACCES` и строковые маркеры блокировок другими процессами.
* **Синхронный и асинхронный бэкофф (`retry_with_backoff`, `async_retry_with_backoff`):** Выполняет операцию с постепенным увеличением задержки (initial_delay=0.02s, backoff_factor=2.0, max_delay=1.0s, max_retries=5) и Dev-логированием попыток `[WARN] / [OK]`.
* **Интеграция в движки:**
  * В [`src/bridge_core/pocket.py`](../src/bridge_core/pocket.py) операции чтения чанков, записи в `.part` и финального `os.replace` обернуты в `retry_with_backoff`.
  * В [`src/bridge_core/logger.py`](../src/bridge_core/logger.py) ротация и запись строк аудита в JSONL защищены от перехвата сторонними процессами.

### 2.2. Протокол и механизм докачки файлов (Resumable Chunk Transfers)
* **Контракт DTO:** В [`src/bridge_core/models.py`](../src/bridge_core/models.py) добавлены модели `PocketOffsetParams` и `PocketOffsetResult`.
* **RPC-метод `pocket.offset`:**
  * Зарегистрирован в [`src/bridge_agent_win/service.py`](../src/bridge_agent_win/service.py).
  * Позволяет клиенту запросить точный размер существующего временного файла `.<filename>.part` на удаленном узле.
* **Двунаправленная докачка в клиенте (`src/bridge_client_linux/client.py`):**
  * `pocket_push_file(..., resume=True)`: перед отправкой проверяет удаленный `.part`. Если файл частично загружен, смещение `offset` сдвигается на имеющееся количество байт, и чтение локального файла начинается с `seek(offset)`.
  * `pocket_pull_file(..., resume=True)`: проверяет локальный `.part`. При наличии открывает файл в режиме `r+b` со смещения `stat().st_size` и запрашивает у сервера чанки с этого места.
  * После завершения любого трансфера выполняется строгая верификация полного SHA-256 хеша.

### 2.3. Fail-Fast мониторинг сна и обрыва связи (Heartbeat Probe <= 1.5s)
* Модуль [`src/bridge_core/heartbeat.py`](../src/bridge_core/heartbeat.py) обеспечивает быстрый опрос узла перед выполнением длительных операций.
* При зависании удаленного узла (уход в сон без закрытия TCP-сессии) таймер сокета срабатывает за 1.5 секунды (`probe_timeout_sec=1.5`), не дожидаясь многоминутного таймаута TCP Keepalive операционной системы.
* Linux CLI мгновенно переводит узел в состояние `UNREACHABLE` и возвращает детерминированный код `ExitCode.NETWORK_ERROR (2)`.

---

## 3. Разработанный комплекс тестирования

### 3.1. Интеграционное тестирование отказоустойчивости (`tests/integration/test_resilience_simulation.py`)
14 специализированных сценариев:
1. `test_simulated_socket_drop_and_resume_push`: Имитация обрыва соединения на середине трансфера и успешная докачка с сохранением SHA-256.
2. `test_pocket_offset_params_and_result_validation`: Строгая валидация Pydantic контрактов смещения.
3. `test_pocket_manager_partial_file_detection`: Проверка детекции и отдачи смещения частичных файлов.
4. `test_high_level_client_resumable_push`: Сквозная докачка большого файла клиентом через реальный RPC-сокет.
5. `test_high_level_client_resumable_pull`: Сквозное возобновление скачивания клиентом из удаленного кармана.
6. `test_corrupted_partial_file_fails_sha256_and_cleans_up`: Защита от поврежденных `.part` файлов (при несовпадении SHA-256 временный файл стирается, атомарная замена блокируется).
7. `test_is_sharing_violation_detection`: Идентификация `WinError 32`, `EBUSY`, `PermissionError`.
8. `test_retry_loop_recovers_after_temporary_sharing_violation`: Успешное снятие временной блокировки через 2 попытки бэкоффа.
9. `test_retry_loop_exhausts_and_raises_on_permanent_lock`: Корректный выброс исключения при перманентной блокировке.
10. `test_atomic_jsonl_logger_recovers_from_sharing_violation`: Восстановление записи аудита при коллизии.
11. `test_pocket_manager_write_chunk_recovers_from_sharing_violation`: Устойчивость записи чанка к занятости файла.
12. `test_heartbeat_manager_probe_fail_fast_when_node_hangs`: Срабатывание таймаута probe за <= 1.5 сек.
13. `test_high_level_client_ping_fail_fast_timeout`: Мгновенный возврат ошибки клиентом при недоступности узла.
14. `test_heartbeat_probe_immediate_failure_on_closed_port`: Мгновенный сбой при закрытом порте.

### 3.2. Фаззинг и стресс-тестирование транспорта (`tests/unit/test_transport_and_storage_fuzzing.py`)
10 стресс-сценариев:
* Побайтовая передача фреймов через `StreamReader` и loopback сокеты ядра ОС.
* Стресс 500 параллельных заметок через `asyncio.gather` с `os.fsync`.
* Параллельная передача 10 файлов (от 1 байта до 5 МБ) с изоляцией сбоев.

---

## 4. Результаты верификации

* Полный сьют тестов: **286 passed** [OK]
* Время прогона: ~13.5 сек (локально)
* Линтер / Форматирование: Ruff 100% clean [OK]
* Типизация: Mypy 100% clean (30 исходных файлов, strict mode) [OK]

Фаза 6 полностью завершена. Платформа Bridge_local готова к финальной Фазе 7 (Сборка, упаковка и релиз).
