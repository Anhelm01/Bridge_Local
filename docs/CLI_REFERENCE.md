# Справочник интерфейса командной строки Bridge_local (CLI & TUI)

Данный документ содержит полное описание консольных интерфейсов платформы **Bridge_local**: клиентской утилиты оператора `bridge-cli` и утилиты управления агентом Windows `bridge-agent`.

---

## 1. Коды завершения процессов (Exit Codes)

Все консольные команды платформы возвращают детерминированные целочисленные коды возврата (`sys.exit(code)`):

| Код | Символическое имя | Описание |
|:---:|:---|:---|
| **`0`** | `SUCCESS` | Команда успешно выполнена. |
| **`1`** | `GENERAL_ERROR` | Неверные аргументы командной строки, синтаксическая ошибка конфигурации или внутреннее исключение. |
| **`2`** | `NETWORK_ERROR` | Целевой узел недоступен, соединение отклонено (Connection Refused), сокет сброшен операционной системой. |
| **`3`** | `AUTH_ERROR` | Несовпадение секретного ключа PSK, ошибка проверки контрольной подписи HMAC-SHA256, превышение дрейфа часов или повторная атака Nonce. |
| **`4`** | `COMMAND_FAILED` | Дочерний процесс PowerShell на узле Windows завершился с ненулевым кодом выхода. |
| **`5`** | `TIMEOUT` | Превышен установленный лимит времени ожидания выполнения команды PowerShell или ответа удаленного RPC-сервера. |

---

## 2. Стандарт для ИИ-агентов (`--json` режим)

Любая команда `bridge-cli` поддерживает флаг `--json` (или `-j`):
- **Чистый поток данных:** Никаких ANSI-последовательностей, цветных кодов или псевдографических рамок в `stdout`.
- **Строгая схема:** Ответ представляет собой валидный JSON-объект.
- **Отсутствие интерактивных блокировок:** Утилита никогда не запрашивает ввод из `stdin`.

Пример успешного выполнения:
```json
{
  "exit_code": 0,
  "stdout": "BridgeLocalAgent Running\n",
  "stderr": "",
  "duration_ms": 32,
  "started_at": "2026-09-30T21:00:00.000000Z",
  "completed_at": "2026-09-30T21:00:00.032000Z",
  "timed_out": false,
  "encoding_detected": "utf-8"
}
```

Пример ошибки в JSON-режиме:
```json
{
  "status": "error",
  "error_code": 2,
  "error_type": "BridgeNetworkError",
  "message": "Connection refused to 192.168.1.100:9732"
}
```

---

## 3. Клиент оператора: `bridge-cli`

### 3.1. Глобальные опции
- `--json`, `-j`: Включение строгого машиночитаемого вывода JSON.
- `--version`, `-v`: Вывод версии платформы и используемого ядра.
- `--config`, `-c <path>`: Явное указание пути к конфигурационному файлу `bridge.toml`.
- `--host`, `-h <ip>`: Переопределение IP-адреса удаленного узла.
- `--port`, `-p <port>`: Переопределение сетевого порта.
- `--token`, `-t <psk>`: Переопределение секретного токена PSK.
- `--node`, `-n <name>`: Переопределение имени целевого узла.

---

### 3.2. Базовые команды состояния

#### `bridge-cli status`
Сводный статус всей системы: состояние сетевого канала, RTT пинга, нагрузка на CPU и RAM удаленного узла, баланс файлов кармана и количество непрочитанных заметок.
```bash
bridge-cli status
bridge-cli status --json
```

#### `bridge-cli ping`
Heartbeat-проверка физической доступности агента с измерением сетевой задержки (RTT).
```bash
bridge-cli ping --count 3
bridge-cli ping --json
```
- `--count`, `-n <int>`: Количество отправляемых проб (от 1 до 10, по умолчанию: 1).

---

### 3.3. Удаленное выполнение: `bridge-cli exec`

Выполнение скриптов и команд PowerShell на узле Windows.

```bash
bridge-cli exec "Get-Process -Name BridgeLocalAgent"
bridge-cli exec "Stop-Service -Name Wuauserv" --no-admin
bridge-cli exec "dir" --timeout 15 --json
```

**Опции:**
- `<command>` (позиционный аргумент): Строка команды PowerShell.
- `--timeout`, `-T <int>`: Таймаут выполнения в секундах (по умолчанию 30). При превышении таймаута дочернее дерево процессов принудительно уничтожается, команда завершается с кодом 5.
- `--admin / --no-admin`: Запуск с повышенными правами Администратора (по умолчанию `--admin`).
- `--dir`, `-d <path>`: Рабочий каталог на диске Windows для выполнения команды.

---

### 3.4. Быстрая отправка файлов: `bridge-cli send`

Мгновенная передача одного или нескольких файлов в карман на стороне Windows (Direct File Drop).

```bash
# Отправка одного файла:
bridge-cli send archive.zip

# Отправка нескольких файлов с помещением во вложенную папку:
bridge-cli send photo1.png photo2.png --target-dir "screenshots"
```

**Опции:**
- `<files...>` (позиционные аргументы): Один или более путей к локальным файлам.
- `--target-dir`, `-d <string>`: Относительный подкаталог в удаленном кармане.

---

### 3.5. Управление хранилищем: `bridge-cli pocket`

Команды управления синхронизацией и передачей файлов общего кармана.

#### `bridge-cli pocket status`
Отображает локальный путь, количество файлов на локальном и удаленном узле, размеры и списки файлов в очереди на скачивание (PULL) или отдачу (PUSH).
```bash
bridge-cli pocket status
bridge-cli pocket status --json
```

#### `bridge-cli pocket sync`
Запуск пакетной синхронизации файлов между узлами.
```bash
bridge-cli pocket sync --direction both
bridge-cli pocket sync --direction push
bridge-cli pocket sync --direction pull
```
- `--direction`, `-d`: Направление синхронизации (`both`, `push`, `pull`). По умолчанию `both`.

#### `bridge-cli pocket push <file>`
Загрузка конкретного локального файла в удаленный карман.
```bash
bridge-cli pocket push ./build/dist.tar.gz --target "releases/dist.tar.gz"
```

#### `bridge-cli pocket pull <remote_file>`
Скачивание конкретного файла из удаленного кармана на локальную машину.
```bash
bridge-cli pocket pull "logs/agent.log" --dest ./local_agent.log
```

---

### 3.6. Подсистема заметок: `bridge-cli note`

Быстрый обмен текстовыми фрагментами, кодом и ссылками.

#### `bridge-cli note send <text>`
Отправка заметки на удаленный узел.
```bash
bridge-cli note send "https://github.com/Anhelm01/Bridge_Local/issues/42"
```

#### `bridge-cli note list`
Просмотр журнала заметок с временными метками и статусами прочтения.
```bash
bridge-cli note list --limit 10
bridge-cli note list --unread-only
```
- `--limit`, `-l <int>`: Максимальное количество выводимых заметок (по умолчанию 20).
- `--unread`, `-u`: Показывать только новые непрочитанные заметки.

#### `bridge-cli note read <note_id...>`
Отметка одной или нескольких заметок как прочитанных.
```bash
bridge-cli note read "e9a03bc2-44df-4416-8f3a-cb28646b1a11"
```

---

### 3.7. Интерактивный TUI: `bridge-cli tui`

Полноэкранный терминальный графический интерфейс с навигацией по вкладкам и цветовой схемой Titanium Vivid.

```bash
bridge-cli tui
bridge-cli tui --mode NOTES
```

**Горячие клавиши TUI:**
- `F1` или `1`: Монитор состояния (DASH).
- `F2` или `2`: Файловый карман (POCKET).
- `F3` или `3`: Журнал заметок (NOTES).
- `F4` или `4`: Консоль выполнения PowerShell (EXEC).
- `F5` или `5`: Просмотр конфигурации (CONFIG).
- `F6` или `6`: Диагностический экран разработчика (DEV).
- `Tab`: Переключение фокуса элементов.
- `q` / `Esc`: Выход из полноэкранного режима.

---

### 3.8. Вспомогательные команды
- `bridge-cli welcome`: Отрисовка фирменного экрана приветствия BRIDGES Master с неофетч-информацией о системе.
- `bridge-cli config show`: Вывод текущей активной конфигурации в формате TOML или JSON.

---

## 4. Управление агентом Windows: `bridge-agent`

Консольная утилита администрирования на стороне Windows.

```powershell
bridge-agent [команда]
```

### 4.1. Доступные команды
- `bridge-agent run`: Запуск агента в текущем терминале Windows (консольный режим для тестирования и отладки). Прерывается по `Ctrl+C`.
- `bridge-agent service-run`: Запуск процесса в качестве управляемой системной службы Windows Service Control Manager (SCM).
- `bridge-agent service [install|start|stop|remove]`: Управление регистрацией службы Windows.
- `bridge-agent drop <file_or_dir>`: Ручное копирование файла или папки в каталог кармана.
- `bridge-agent install-context-menu`: Регистрация пункта контекстного меню Проводника Windows (Explorer) в ветке реестра `HKCU\Software\Classes\*\shell\BridgeDrop`.
- `bridge-agent uninstall-context-menu`: Удаление записи контекстного меню из реестра.
- `bridge-agent generate-reg [out.reg]`: Экспорт настроек реестра в `.reg` файл для ручного применения без прав администратора.
