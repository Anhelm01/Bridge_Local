# Руководство оператора Linux: Команды и глобальный запуск из любого каталога

Данный документ содержит полное пошаговое руководство по настройке утилиты **Bridge Local (`bridge-cli`)** на Linux для работы из произвольного каталога файловой системы по умолчанию, а также детальный справочник всех консольных команд.

---

## 1. Архитектура конфигурации и поиск путей (Config Discovery)

При вызове команды `bridge-cli` из случайной папки (например, `/tmp` или `~/Downloads`), утилита должна однозначно определить два критических параметра:
1. Где находится файл настроек сетевого подключения (`bridge.toml`).
2. В какой именно каталог сохранять и откуда забирать синхронизируемые файлы («Карман»).

### 1.1. Алгоритм поиска конфигурационного файла

Ядро `bridge_core.config.BridgeConfig.load()` ищет `bridge.toml` строго в следующем порядке приоритета:

1. **Явный флаг командной строки:** `--config /путь/к/bridge.toml` (наивысший приоритет).
2. **Переменная окружения:** `BRIDGE_CONFIG` (если задана в системе или сессии).
3. **Текущий рабочий каталог:** `./bridge.toml` (папка, из которой запущена команда).
4. **Каталог исполняемого файла:** `$(dirname $(which bridge-cli))/bridge.toml`.
5. **Родительский каталог бинарника:** `$(dirname $(which bridge-cli))/../bridge.toml`.
6. **Каталог репозитория разработки:** путь к корню исходного кода (в dev-режиме).
7. **Стандартный системный путь пользователя (XDG):**
   `~/.config/bridge-local/bridge.toml`
8. **Каталог распаковки PyInstaller:** внутри временного окружения сборки `_MEIPASS`.

Если файл не найден ни по одному из путей, утилита стартует со значениями по умолчанию (`127.0.0.1:9732`).

### 1.2. Разрешение пути к каталогу «Карман» (`pocket.path`)

В секции `[pocket]` файла `bridge.toml` параметр `path` определяет хранилище файлов:
- **Относительный путь (например, `path = "./pocket"`):**
  Разрешается относительно каталога, где лежит найденный `bridge.toml`. Если конфиг лежит в `~/.config/bridge-local/bridge.toml`, карман окажется в `~/.config/bridge-local/pocket`.
- **Абсолютный путь (рекомендуется для глобальной работы):**
  Например, `path = "~/BridgeLocal/pocket"` или `path = "/home/username/pocket"`.
  При использовании символа тильды `~` или абсолютного пути карман всегда привязан к одной и той же точке в системе, независимо от текущей директории терминала.

---

## 2. Единый интерактивный центр управления (`./start.sh`)

Для максимального удобства и мгновенной смены целевого устройства (IP-адреса, порта, токена) в корне проекта поставляется интерактивная консоль **`./start.sh`**.

Запуск мастера:
```bash
./start.sh
```

### Возможности консоли `./start.sh`:
- **Живой мониторинг статуса в шапке:** отображает активный конфиг-файл, целевой узел Windows, быстрый сокет-зонд (`ONLINE` / `OFFLINE` с замером миллисекунд), статус глобального wrapper'а, переменную `PATH` и службу `systemd`.
- **`[1] БЫСТРЫЙ СТАРТ ПОД КЛЮЧ`:** пошаговый мастер запрашивает IP Windows, порт, токен и путь к карману, автоматически создает `~/.config/bridge-local/bridge.toml`, генерирует wrapper `~/.local/bin/bridge-cli` с защитой от `proxychains`, проверяет `PATH`, тестирует связь и предлагает запустить TUI.
- **`[2] СМЕНИТЬ ЦЕЛЕВОЕ УСТРОЙСТВО / СЕТЬ`:** мгновенная смена целевого хоста (например, `192.168.1.150:9732` или `10.0.0.5`) в один клик с проверкой пинга сокета без ручной правки файлов TOML.
- **`[3] НАСТРОЙКА ГЛОБАЛЬНОГО ДОСТУПА ПО УМОЛЧАНИЮ`:** развертывание wrapper'а и добавление в `~/.bashrc` / `~/.zshrc`.
- **`[4] ЗАПУСТИТЬ ОПЕРАТИВНЫЙ TUI ДАШБОРД`:** вход в полноэкранный интерфейс оператора (F1–F8).
- **`[5] ДИАГНОСТИКА И СТАТУС СЕТИ`:** серия Heartbeat-пингов и сводный отчет.
- **`[6] ВЫПОЛНИТЬ КОМАНДУ НА WINDOWS`:** интерактивная командная строка PowerShell с сохранением рабочей директории.
- **`[7] УПРАВЛЕНИЕ КАРМАНОМ`:** отправка, скачивание файлов, список и запуск синхронизации.
- **`[8] ОПЕРАТИВНЫЕ ЗАМЕТКИ`:** отправка и просмотр заметок.
- **`[9] ФОНОВАЯ СЛУЖБА SYSTEMD`:** установка, запуск, просмотр журнала `journalctl` и удаление службы.
- **`[10] СБОРКА АВТОНОМНОГО БИНАРНИКА`:** сборка `dist/bridge-cli` через PyInstaller.
- **`[11] ПОЛНАЯ ОЧИСТКА И УДАЛЕНИЕ`:** безопасное удаление глобальных ссылок и служб.

---

## 3. Ручная пошаговая настройка глобального доступа (для серверов и CI/CD)

Если требуется настроить систему вручную или в скриптах автоматизации:

### Шаг 1: Размещение исполняемого файла в системном PATH

Выберите один из двух вариантов в зависимости от формата установки:

#### Вариант A: Автономный скомпилированный бинарник (рекомендуется)
Если собран бинарный файл `dist/bridge-cli`:
```bash
# 1. Создать пользовательскую директорию бинарников (если отсутствует)
mkdir -p ~/.local/bin

# 2. Скопировать исполняемый файл
cp /home/anhelm/Projects/Bridge_Local/dist/bridge-cli ~/.local/bin/bridge-cli
chmod +x ~/.local/bin/bridge-cli
```

#### Вариант B: Установка через менеджер пакетов uv (разработка / editable)
```bash
cd /home/anhelm/Projects/Bridge_Local
uv tool install --editable .
```
Команда `uv tool install` автоматически создаст символические ссылки в `~/.local/bin/bridge-cli`.

### Шаг 2: Проверка переменной окружения PATH

Убедитесь, что каталог `~/.local/bin` включен в переменную `PATH`.
Проверьте вывод:
```bash
echo $PATH | grep -q "$HOME/.local/bin" && echo "PATH настроен" || echo "Требуется настройка PATH"
```

Если каталога нет в `PATH`, добавьте его в конфигурационный файл вашей командной оболочки (`~/.bashrc` или `~/.zshrc`):
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Шаг 3: Создание центрального конфигурационного файла

Создайте постоянную конфигурацию в стандартном каталоге XDG (`~/.config/bridge-local/`):
```bash
# 1. Создать каталог конфигурации
mkdir -p ~/.config/bridge-local

# 2. Скопировать рабочий bridge.toml
cp /home/anhelm/Projects/Bridge_Local/bridge.toml ~/.config/bridge-local/bridge.toml
```

Отредактируйте `~/.config/bridge-local/bridge.toml`, указав постоянные абсолютные пути:
```toml
[connection]
host = "192.168.100.2"   # IP-адрес целевого хоста Windows в локальной сети
port = 9732              # Порт агента Windows
timeout_sec = 5.0
psk_token = "BridgeLocalSecretKey_Anhelm_2026_Secure"

[heartbeat]
interval_sec = 2.0
timeout_sec = 1.5
max_missed = 3
reconnect_delay_sec = 5.0

[pocket]
# ВАЖНО: укажите абсолютный путь к единому карману
path = "/home/anhelm/BridgeLocal/pocket"
logs_subdir = "logs"
sync_watch = true
max_chunk_size = 65536
log_max_days = 30

[exec]
default_timeout_sec = 30.0
max_timeout_sec = 300.0
powershell_path = "powershell.exe"
encoding = "utf-8"
```

Создайте сам каталог кармана:
```bash
mkdir -p /home/anhelm/BridgeLocal/pocket
```

### Шаг 4: Настройка системного обхода Proxychains (LD_PRELOAD)

Если на машине используется `proxychains` или глобальный перехват сокетов через `LD_PRELOAD`, локальные сетевые пакеты к Windows (подсеть `192.168.x.x` или прямой кабель) могут блокироваться или уходить в прокси.

Для решения создайте скрипт-обертку `/home/anhelm/.local/bin/bridge-cli`:
```bash
cat << 'EOF' > ~/.local/bin/bridge-cli
#!/usr/bin/env bash
# Обертка для очистки LD_PRELOAD и фиксации конфигурации по умолчанию
export BRIDGE_CONFIG="${BRIDGE_CONFIG:-$HOME/.config/bridge-local/bridge.toml}"

# Сброс перехватчиков сокетов для локальной P2P-сети
if [[ -f "/home/anhelm/Projects/Bridge_Local/dist/bridge-cli" ]]; then
    LD_PRELOAD="" exec "/home/anhelm/Projects/Bridge_Local/dist/bridge-cli" "$@"
else
    LD_PRELOAD="" exec uv --project "/home/anhelm/Projects/Bridge_Local" run bridge-cli "$@"
fi
EOF

chmod +x ~/.local/bin/bridge-cli
```

### Шаг 5: Проверка работы из произвольной папки

Перейдите во временный каталог `/tmp` и выполните проверочные команды:
```bash
cd /tmp

# 1. Проверка пути используемой конфигурации
bridge-cli config path
# Ожидаемый вывод: /home/anhelm/.config/bridge-local/bridge.toml

# 2. Проверка пути кармана
bridge-cli pocket path
# Ожидаемый вывод: /home/anhelm/BridgeLocal/pocket

# 3. Проверка связи с Windows
bridge-cli ping
```

---

## 3. Фоновая служба Systemd (Опционально)

Чтобы на Linux непрерывно работал автоматический синхронизатор кармана (watchdog) без необходимости держать открытый терминал, настройте пользовательскую службу systemd:

```bash
# 1. Создать каталог пользовательских юнитов
mkdir -p ~/.config/systemd/user

# 2. Скопировать unit-файл
cp /home/anhelm/Projects/Bridge_Local/scripts/systemd/bridge-local.service ~/.config/systemd/user/

# 3. Перечитать конфигурацию systemd и активировать службу
systemctl --user daemon-reload
systemctl --user enable --now bridge-local.service

# 4. Проверить статус службы
systemctl --user status bridge-local.service
```

Журнал фоновой службы доступен командой:
```bash
journalctl --user -u bridge-local.service -f
```

---

## 4. Справочник команд Linux (`bridge-cli`)

Утилита поддерживает как человеческий интерактивный вывод, так и строгий машиночитаемый вывод для ИИ-агентов (`--json`).

### 4.1. Диагностика и статус

#### `bridge-cli status`
Формирует сводный отчет о состоянии всех ключевых подсистем: качество сетевого соединения, пинг (RTT), параметры удаленного узла (CPU, RAM, Uptime), статистика файлов в кармане и непрочитанные заметки.
```bash
bridge-cli status
bridge-cli status --json
```

#### `bridge-cli ping`
Отправка контрольных зондов (Heartbeat Ping) на агент Windows с замером времени отклика.
```bash
# Одиночный пинг
bridge-cli ping

# Серия из 5 запросов
bridge-cli ping --count 5

# Формат JSON для скриптов
bridge-cli ping --json
```

#### `bridge-cli tui`
Полноэкранный интерактивный дашборд оператора с поддержкой переключения вкладок функциональными клавишами F1–F8:
```bash
bridge-cli tui
```
- **F1 (DASH):** Общий статус системы, пинг и сетевые метрики.
- **F2 (POCKET):** Список файлов в кармане, проверка SHA-256 хэшей.
- **F3 (NOTES):** Журнал оперативных заметок между машинами.
- **F4 (EXEC):** Интерактивная удаленная консоль PowerShell.
- **F5 (CONFIG):** Таблица узлов и параметры сети.
- **F6 (LOGS):** Поток логов Dev-Mode (RPC + Wire + Proxy).
- **F7 (CONNECT):** Быстрая смена IP-адреса и порта подключения.
- **F8 (SPLASH):** Полноэкранный экран Neofetch с логотипом BRIDGES Master.
- **Q / Esc:** Выход из TUI.

---

### 4.2. Удаленное выполнение команд (`bridge-cli exec`)

Выполняет команды в среде Windows PowerShell на удаленном узле. Команда исполняется в UTF-8 (`chcp 65001`), завершается с возвратом реального exit-кода процесса.

```bash
# Получить список служб на Windows
bridge-cli exec "Get-Service BridgeLocalAgent"

# Проверить нагрузку на процессор
bridge-cli exec "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"

# Выполнение с нестандартным таймаутом (в секундах)
bridge-cli exec "Start-Sleep -Seconds 10; Write-Output 'Done'" --timeout 15

# Машиночитаемый режим для ИИ-оператора
bridge-cli exec "whoami" --json
```

Формат JSON-ответа команды `exec`:
```json
{
  "exit_code": 0,
  "stdout": "win-workstation\\admin\n",
  "stderr": "",
  "duration_ms": 32,
  "started_at": "2026-10-02T12:00:00.000000Z",
  "completed_at": "2026-10-02T12:00:00.032000Z",
  "timed_out": false,
  "encoding_detected": "utf-8"
}
```

---

### 4.3. Управление общим хранилищем «Карман» (`bridge-cli pocket`)

Подсистема гарантирует поблочную передачу файлов с валидацией целостности SHA-256.

#### `bridge-cli pocket drop <путь_к_файлу>`
Быстрая отправка локального файла или каталога в карман:
```bash
# Отправить файл из текущего каталога
bridge-cli pocket drop archive.zip

# Отправить файл по абсолютному пути
bridge-cli pocket drop /var/log/syslog
```

#### `bridge-cli pocket list`
Отображение содержимого кармана со статусом синхронизации и SHA-256 хэшами:
```bash
bridge-cli pocket list
bridge-cli pocket list --json
```

#### `bridge-cli pocket sync`
Принудительная двусторонняя синхронизация (сверка манифестов и докачка отсутствующих файлов):
```bash
# Двусторонняя синхронизация
bridge-cli pocket sync

# Только отправка измененных локальных файлов на Windows
bridge-cli pocket sync --direction push

# Только скачивание новых файлов с Windows на Linux
bridge-cli pocket sync --direction pull
```

#### `bridge-cli pocket path`
Выводит абсолютный путь к активному каталогу кармана:
```bash
bridge-cli pocket path
```

---

### 4.4. Журнал оперативных заметок (`bridge-cli note`)

Позволяет обмениваться короткими текстовыми сообщениями, ссылками и сниппетами кода без создания файлов на диске.

#### `bridge-cli note send "<текст>"`
Отправить заметку на Windows:
```bash
bridge-cli note send "Сборка ядра завершена успешно"
bridge-cli note send "https://github.com/owner/repo/pull/42"
```

#### `bridge-cli note list`
Просмотр журнала последних заметок:
```bash
# Последние 20 заметок
bridge-cli note list

# Ограничить вывод 5 записями
bridge-cli note list --limit 5

# JSON-вывод
bridge-cli note list --json
```

#### `bridge-cli note clear`
Очистить историю заметок:
```bash
bridge-cli note clear
```

---

### 4.5. Управление конфигурацией (`bridge-cli config`)

#### `bridge-cli config show`
Отображение текущих активных настроек:
```bash
bridge-cli config show
bridge-cli config show --json
```

#### `bridge-cli config set`
Изменение параметров подключения без ручного редактирования файла:
```bash
# Смена IP-адреса и порта
bridge-cli config set --host 192.168.100.5 --port 9732

# Обновление токена безопасности
bridge-cli config set --token "NewSecretToken_2026"
```

#### `bridge-cli config path`
Выводит путь к файлу конфигурации, который используется в данный момент:
```bash
bridge-cli config path
```

---

## 5. Стандарты для автоматизации и ИИ-агентов (`agy_cli`)

При вызове из скриптов автоматизации или ИИ-агентов обязательно передавайте флаг `--json`.

### Таблица кодов возврата (Exit Codes)
| Код | Имя константы | Описание ситуации |
|:---:|:---|:---|
| **`0`** | `SUCCESS` | Команда успешно выполнена. |
| **`1`** | `GENERAL_ERROR` | Ошибка параметров, повреждение конфигурации или внутренний сбой. |
| **`2`** | `NETWORK_ERROR` | Целевой хост Windows недоступен, порт закрыт, сетевой таймаут. |
| **`3`** | `AUTH_ERROR` | Несовпадение PSK-токена, ошибка HMAC-подписи или попытка replay. |
| **`4`** | `COMMAND_FAILED` | Процесс PowerShell на Windows завершился с ненулевым кодом выхода. |
| **`5`** | `TIMEOUT` | Превышен лимит времени выполнения команды или ответа RPC. |

### Пример безопасного вызова в Bash-скрипте:
```bash
#!/usr/bin/env bash
set -euo pipefail

RESPONSE=$(bridge-cli exec "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'" --json)
EXIT_CODE=$(echo "$RESPONSE" | jq -r '.exit_code')

if [[ "$EXIT_CODE" -eq 0 ]]; then
    REMOTE_TIME=$(echo "$RESPONSE" | jq -r '.stdout' | tr -d '\r\n')
    echo "Время на Windows: $REMOTE_TIME"
else
    STDERR=$(echo "$RESPONSE" | jq -r '.stderr')
    echo "Ошибка выполнения: $STDERR" >&2
    exit 1
fi
```
