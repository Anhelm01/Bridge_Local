# Руководство разработчика платформы Bridge_local

Данный документ содержит стандарты разработки, правила архитектурной изоляции, инструкции по запуску тестов, статических анализаторов и пошаговый алгоритм расширения функциональности платформы **Bridge_local**.

---

## 1. Архитектурные инварианты платформы

Каждый разработчик или агент, вносящий изменения в репозиторий, обязан строго соблюдать ключевые инварианты из [`AGENTS.md`](file:///home/anhelm/Projects/Bridge_Local/AGENTS.md):

1. **Модульность и взаимная независимость:**
   Пакет `bridge_core` не должен импортировать модули из `bridge_agent_win` или `bridge_client_linux`. Ядро должно оставаться на 100% автономным и кроссплатформенным.
2. **Контрактный подход (Pydantic V2):**
   Любое взаимодействие между слоями и узлами описывается типизированными моделями DTO в [`src/bridge_core/models.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/models.py). Никаких нетипизированных словарей в публичных API.
3. **Отсутствие смайликов (Zero Emojis):**
   В кодовой базе, тестах, строках документации, коммитах и ответах категорически запрещены смайлики (эмодзи). Используются строгие технические маркеры: `[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`, `[SERVICE]`.
4. **Правило 9: Контроль Git-релиза:**
   Автономные коммиты и отправка в удаленный репозиторий (`git push`) без прямого подтверждения или приказа пользователя категорически запрещены.

---

## 2. Настройка среды разработки

Для изоляции зависимостей и управления виртуальным окружением используется пакетный менеджер **uv**:

```bash
# Клонирование репозитория
git clone git@github.com:Anhelm01/Bridge_Local.git
cd Bridge_Local

# Синхронизация зависимостей и инструментов сборки/тестирования
uv sync --all-extras
```

---

## 3. Запуск автоматических тестов

Тестовый набор включает 311+ модульных, интеграционных и стресс-тестов:

```bash
# Запуск полного набора тестов
LD_PRELOAD="" uv run pytest

# Запуск с подробным выводом и остановкой на первой ошибке (-x)
LD_PRELOAD="" uv run pytest -v -x

# Запуск только интеграционных тестов
LD_PRELOAD="" uv run pytest tests/integration/
```

### Важное примечание: Зачем нужен `LD_PRELOAD=""`?
Если на вашей рабочей станции активен системный проксификатор (например, `proxychains-ng`), его разделяемая библиотека перехватывает системные вызовы `connect()`, `bind()` и `socket()` для локальных loopback-адресов (`127.0.0.1`), что нарушает работу тестов интеграционного взаимодействия. Префикс `LD_PRELOAD=""` очищает предварительную загрузку и направляет сетевые вызовы напрямую через ядро операционной системы.

---

## 4. Контроль качества кода (Quality Gates)

Перед отправкой изменений на ревью или включением в релиз обязательно прохождение трех уровней статического контроля:

```bash
# 1. Линтер и поиск потенциальных багов (Ruff)
uv run ruff check .

# 2. Проверка стиля и форматирования кода (Ruff Format)
uv run ruff format --check .

# 3. Строгий статический анализ типов (Mypy)
uv run mypy
```

Автоматическое форматирование кода:
```bash
uv run ruff format .
uv run ruff check --fix .
```

---

## 5. Добавление нового RPC-метода (Пошаговый алгоритм)

Если вам необходимо расширить возможности платформы новым удаленным вызовом (например, `system.reboot` или `clipboard.sync`), следуйте следующей процедуре:

### Шаг 1: Определение DTO моделей контракта
В файле [`src/bridge_core/models.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_core/models.py):
1. Добавьте константу в класс `RpcMethod`:
   ```python
   class RpcMethod:
       ...
       SYSTEM_REBOOT = "system.reboot"
   ```
2. Создайте классы параметров и результата:
   ```python
   class SystemRebootParams(BaseModel):
       delay_seconds: int = Field(default=5, ge=0)
       force: bool = Field(default=False)


   class SystemRebootResult(BaseModel):
       scheduled: bool
       message: str
   ```

### Шаг 2: Реализация обработчика на агенте (Windows)
В файле [`src/bridge_agent_win/service.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_agent_win/service.py):
1. Добавьте метод обработки в диспетчер:
   ```python
   async def handle_system_reboot(self, params: dict[str, Any]) -> dict[str, Any]:
       req = SystemRebootParams.model_validate(params)
       # Логика выполнения команды...
       return SystemRebootResult(
           scheduled=True, message=f"Reboot in {req.delay_seconds}s"
       ).model_dump()
   ```
2. Зарегистрируйте имя метода `RpcMethod.SYSTEM_REBOOT` в таблице диспетчера запросов.

### Шаг 3: Реализация клиентского метода (Linux)
В файле [`src/bridge_client_linux/client.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_client_linux/client.py):
1. Добавьте строго типизированный публичный метод:
   ```python
   async def system_reboot(self, delay_seconds: int = 5, force: bool = False) -> SystemRebootResult:
       params = SystemRebootParams(delay_seconds=delay_seconds, force=force)
       res = await self.call(RpcMethod.SYSTEM_REBOOT, params.model_dump())
       return SystemRebootResult.model_validate(res)
   ```

### Шаг 4: Вывод команды в интерфейс CLI
В файле [`src/bridge_client_linux/cli.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_client_linux/cli.py):
1. Зарегистрируйте команду Typer с поддержкой флагов `--json` и детерминированных кодов выхода.

### Шаг 5: Покрытие тестами
Создайте модульный тест в `tests/unit/` и интеграционный сквозной тест в `tests/integration/` с проверкой передачи параметров, валидации HMAC и обработки сетевых ошибок.

---

## 6. Кроссплатформенная разработка и мокирование Windows

Поскольку разработка и прогон CI часто происходят на Linux, системные модули Windows (`win32service`, `servicemanager`, `winreg`) абстрагированы:
- В [`src/bridge_agent_win/service.py`](file:///home/anhelm/Projects/Bridge_Local/src/bridge_agent_win/service.py) реализован fallback-класс `_BaseServiceFramework`.
- В тестах импорты Windows подменяются через словарь `sys.modules`:
  ```python
  from unittest.mock import MagicMock, patch

  mock_servicemanager = MagicMock()
  mock_win32service = MagicMock()

  with patch.dict("sys.modules", {
      "servicemanager": mock_servicemanager,
      "win32service": mock_win32service,
      "win32serviceutil": MagicMock(),
  }):
      # Тестирование логики Windows-службы на Linux...
  ```

---

## 7. Стандарт логирования Dev-Mode Hyper-Logging

При разработке и отладке низкоуровневых протоколов:
- Каждое сетевое событие логируется с микросекундным таймстампом (`_now_us()`).
- В лог заносятся сырые шестнадцатеричные байты фрейма, контрольные суммы чанков и PID создаваемых подпроцессов.
- Логирование выносится на уровни `TRACE` и `DEBUG`, позволяя полностью отключать отладочный мусор в промышленной эксплуатации установкой флага `dev_mode = false` в `bridge.toml`.
