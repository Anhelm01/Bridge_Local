# 04_BINARY_GUIDE_LINUX: Linux Standalone Binary Guide

Полное руководство по развертыванию, конфигурации, оперированию и обслуживанию предварительно скомпилированного / автономного исполняемого файла клиента **`bridge-cli`** на операционной системе Linux (без необходимости установки Python, компиляторов и зависимостей).

---

## 1. Обзор автономного пакета Linux

Автономная сборка Bridge Local для Linux представляет собой единый исполняемый файл или готовый каталог, включающий встроенный рантайм и все библиотеки:
- **Бинарный файл**: `bridge-cli` (ELF 64-bit LSB executable)
- **Консоль управления**: `start.sh` (вспомогательный скрипт автоматизации)
- **Файл настроек**: `bridge.toml`
- **Общий каталог**: `pocket/`

Скомпилированная версия оптимизирована как для живой работы человека в терминале, так и для фоновых демонов и автономных AI-агентов (Antigravity `agy_cli`).

---

## 2. Установка и первичное развертывание

### 2.1 Размещение исполняемого файла
Для установки в пользовательский профиль (не требует прав root):

```bash
# Создание стандартного каталога пользовательских утилит
mkdir -p ~/.local/bin

# Копирование бинарного файла
cp bridge-cli ~/.local/bin/bridge-cli

# Предоставление прав на исполнение
chmod +x ~/.local/bin/bridge-cli
```

### 2.2 Проверка переменной окружения PATH
Убедитесь, что каталог `~/.local/bin` включен в системный `PATH`.
Проверьте вывод команды:
```bash
which bridge-cli
```
Если команда не найдена, добавьте в ваш `~/.bashrc` или `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
И примените изменения: `source ~/.bashrc`.

### 2.3 Общесистемная установка (Опционально)
Если требуется сделать утилиту доступной для всех пользователей системы:
```bash
sudo cp bridge-cli /usr/local/bin/bridge-cli
sudo chmod +x /usr/local/bin/bridge-cli
```

---

## 3. Центральная конфигурация (`bridge.toml`)

Исполняемый файл `bridge-cli` ищет файл конфигурации по следующему приоритету:
1. Явный флаг командной строки: `--config /path/to/bridge.toml`
2. Системная переменная окружения: `export BRIDGE_CONFIG="/custom/path/bridge.toml"`
3. Локальный рабочий каталог: `./bridge.toml`
4. Стандартный каталог конфигураций: `~/.config/bridge_local/bridge.toml`

### 3.1 Создание эталонного конфигурационного файла
Создайте каталог настроек и файл `bridge.toml`:

```bash
mkdir -p ~/.config/bridge_local
nano ~/.config/bridge_local/bridge.toml
```

Вставьте параметры подключения:
```toml
# Переключатель режима разработчика: true (полная трассировка) / false (тихий режим)
dev_mode = false

[node]
name = "linux-workstation"
role = "client"
listen_host = "127.0.0.1"
listen_port = 9733
auth_token = "0123456789abcdef0123456789abcdef"

[network]
heartbeat_interval_sec = 10.0
connect_timeout_sec = 5.0
request_timeout_sec = 30.0

[network.nodes.win-pc]
host = "192.168.1.150"       # IP-адрес вашей Windows-машины
port = 9732                  # Порт агента Bridge Local
role = "agent"

[pocket]
storage_path = "~/Projects/Bridge_Local/pocket"
sync_interval_sec = 3.0
max_file_size_mb = 500
conflict_strategy = "newer_wins"

[notes]
storage_path = "~/Projects/Bridge_Local/pocket/.notes"
max_history_entries = 1000
poll_interval_sec = 5.0

[security]
psk_secret = "0123456789abcdef0123456789abcdef"
allow_unauthenticated = false
```

Защитите файл конфигурации от чтения другими пользователями:
```bash
chmod 600 ~/.config/bridge_local/bridge.toml
```

---

## 4. Быстрый старт через интерактивную консоль (`start.sh`)

Скрипт `start.sh` автоматически распознает скомпилированный бинарник `~/.local/bin/bridge-cli`:

```bash
chmod +x start.sh
./start.sh
```

- **Пункт `[1] QUICK START`**:
  1. Автоматически выполняет сетевой зонд сокета на Windows-узле.
  2. Создает необходимые каталоги Кармана.
  3. Проверяет связь и выводит статус готовности.
- **Пункт `[4] Install Systemd User Service`**:
  В один клик регистрирует бинарный файл как фоновую службу пользователя Linux.

---

## 5. Руководство по командам `bridge-cli`

### 5.1 Проверка состояния узла (`ping`)
```bash
bridge-cli ping
```
*Вывод:*
```text
PONG from win-pc (windows): rtt=13.85ms status=ready cpu=0.0% ram=11769MB
```

#### Машинный вывод JSON (`--json`):
```bash
bridge-cli ping --json
```
```json
{
  "status": "ok",
  "node": "win-pc",
  "os": "windows",
  "rtt_ms": 13.85,
  "cpu_percent": 0.0,
  "ram_mb": 11769
}
```

### 5.2 Удаленный запуск PowerShell (`exec`)
Прямое выполнение команд на удаленном ПК с сохранением рабочей директории между сессиями:

```bash
# Простой запрос
bridge-cli exec "Get-Date; hostname"

# Управление процессами
bridge-cli exec "Get-Process -Name 'bridge-agent' | Select-Object Id, ProcessName, WorkingSet64"

# Запуск с увеличенным таймаутом (по умолчанию 30 сек)
bridge-cli exec --timeout 180 "powershell -File C:\Scripts\heavy-task.ps1"
```

### 5.3 Управление хранилищем Карман (`pocket`)

#### Просмотр текущего статуса и очередей:
```bash
bridge-cli pocket status
```

#### Отправка локального файла на Windows:
```bash
bridge-cli pocket push my_project_archive.tar.gz
```

#### Скачивание файла с Windows в локальный карман:
```bash
bridge-cli pocket pull screenshot.png
```

#### Однократная полная синхронизация:
```bash
bridge-cli pocket sync
```

#### Непрерывный мониторинг и синхронизация в реальном времени:
```bash
bridge-cli pocket sync --watch --interval 3.0
```

### 5.4 Обмен записками и ссылками (`note`)

#### Мгновенная отправка заметки на Windows:
```bash
bridge-cli note send "https://github.com/Anhelm01/Bridge_Local"
bridge-cli note send "Тестовая заметка с экрана Linux"
```

#### Просмотр полученных и отправленных заметок:
```bash
bridge-cli note list
```

#### Отметка заметок как прочитанных:
```bash
bridge-cli note read <ID_ЗАПИСКИ>
```

### 5.5 Графический интерфейс терминала (`tui`)
```bash
bridge-cli tui
```
Полноэкранный дашборд с мониторингом каналов связи, файлов Кармана и журнала заметок.

---

## 6. Протокол для AI-агентов (Antigravity `agy_cli`)

Бинарный файл полностью соответствует регламенту работы автономных AI-операторов:
- Все команды поддерживают флаг `--json`.
- Нулевой вывод мусорных ANSI-последовательностей и спиннеров при перенаправлении вывода (`stdout`).
- Детерминированные коды завершения процесса:

| Код | Символьное имя | Описание |
|---|---|---|
| `0` | `SUCCESS` | Команда выполнена успешно |
| `1` | `GENERAL_ERROR` | Неверные аргументы или внутренняя ошибка приложения |
| `2` | `NETWORK_ERROR` | Целевой хост недоступен, сокет сброшен, отказ в соединении |
| `3` | `AUTH_ERROR` | Несовпадение PSK-токена, ошибка HMAC, атака повторного воспроизведения |
| `4` | `COMMAND_FAILED` | Процесс PowerShell на Windows завершился с ненулевым кодом |
| `5` | `TIMEOUT` | Превышен лимит времени ожидания ответа узла |

---

## 7. Фоновая служба Linux (`systemd --user`)

Для обеспечения постоянной синхронизации файлов Кармана в фоновом режиме:

1. Создайте юнит `~/.config/systemd/user/bridge-pocket-sync.service`:
   ```ini
   [Unit]
   Description=Bridge Local Pocket Continuous Sync Daemon
   After=network.target

   [Service]
   Type=simple
   ExecStart=%h/.local/bin/bridge-cli pocket sync --watch --interval 3.0
   Restart=always
   RestartSec=5
   Environment=BRIDGE_CONFIG=%h/.config/bridge_local/bridge.toml

   [Install]
   WantedBy=default.target
   ```

2. Управление службой:
   ```bash
   # Загрузка и активация автозапуска
   systemctl --user daemon-reload
   systemctl --user enable --now bridge-pocket-sync.service

   # Просмотр статуса
   systemctl --user status bridge-pocket-sync.service

   # Чтение живого журнала
   journalctl --user -u bridge-pocket-sync.service -f
   ```

---

## 8. Обновление и обслуживание

Для обновления бинарника:
1. Остановите фоновую службу:
   ```bash
   systemctl --user stop bridge-pocket-sync.service
   ```
2. Замените исполняемый файл:
   ```bash
   cp new_bridge-cli ~/.local/bin/bridge-cli
   chmod +x ~/.local/bin/bridge-cli
   ```
3. Запустите службу снова:
   ```bash
   systemctl --user start bridge-pocket-sync.service
   ```

---

## 9. Диагностика и устранение проблем

1. **Проверка физической связи сокета:**
   ```bash
   nc -zvw3 192.168.1.150 9732
   ```
   Если порт закрыт, убедитесь, что агент запущен на Windows и порт 9732 TCP открыт в Брандмауэре Windows.

2. **Несоответствие токена авторизации (`AUTH_ERROR`):**
   Убедитесь, что строка `auth_token` в `~/.config/bridge_local/bridge.toml` в точности соответствует `bridge.toml` на машине Windows.

3. **Рассинхронизация часов:**
   Если разница между часами Linux и Windows больше 60 секунд, пакеты отклоняются защитой от повторов (Replay Protection).
   Синхронизируйте время:
   ```bash
   sudo systemctl restart systemd-timesyncd
   ```
