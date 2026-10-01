# Bridge Local — Руководство оператора Linux (Клиент)

Bridge Local для Linux — это клиентская консольная утилита и интерактивный TUI-интерфейс для прямого взаимодействия с удаленной рабочей станцией Windows по локальной сети (LAN).

---

## 1. Содержимое пакета

- `bridge-cli` — единый скомпилированный автономный исполняемый файл x86_64 (не требует Python).
- `bridge.toml` — файл конфигурации соединения, токена и локального кармана.
- `README.md` — данная инструкция.
- `pocket/` — локальный каталог кармана для быстрого обмена файлами.

---

## 2. Быстрый старт

### Шаг 1: Разрешение на запуск бинарного файла
```bash
chmod +x bridge-cli
```

### Шаг 2: Подключение к машине Windows
Самый быстрый способ подключиться (без ручной правки конфигурационного файла):
```bash
# Прямое указание IP и порта Windows-машины:
./bridge-cli connect 192.168.1.150:9732

# Либо пошаговый интерактивный мастер:
./bridge-cli setup
```
Команда автоматически проверит доступность порта удаленного узла по сокету и атомарно запишет параметры в `bridge.toml`.

### Шаг 3: Проверка соединения
```bash
./bridge-cli ping
```
При успешном соединении агент вернет:
- Статус: ONLINE
- ОС удаленного узла: Windows
- Задержка (RTT): в миллисекундах

---

## 3. Основные режимы использования

### 3.1. Интерактивный TUI (терминальный интерфейс)
Запуск полноэкранной панели управления:
```bash
./bridge-cli tui
```
Навигация в TUI:
- `F1` или `1`: Сводный дашборд и мониторинг соединения.
- `F2` или `2`: Карман (Pocket) — просмотр и скачивание файлов.
- `F3` или `3`: Записки (Notes) — быстрый обмен текстом и ссылками.
- `F4` или `4`: Удаленное выполнение команд PowerShell на Windows.
- `F5` или `5`: Просмотр параметров конфигурации `bridge.toml`.
- `F6` или `6`: Dev-лог и трассировка сетевых вызовов.
- `F7` или `7` или `C`: Быстрая смена IP-адреса и токена узла на лету.
- `Tab`: Переключение между экранами.
- `Q` / `Esc`: Выход.

### 3.2. Отправка файлов в Карман (Direct Drop)
Отправить файл или директорию в Windows-карман в один шаг:
```bash
./bridge-cli send /путь/к/файлу.zip
```

### 3.3. Удаленное выполнение PowerShell
Выполнить команду на Windows с возвратом exit-кода и консольного вывода в кодировке UTF-8:
```bash
./bridge-cli exec "Get-Process | Select-Object -First 10"
./bridge-cli exec "dir C:\\"
```

### 3.4. Отправка быстрых заметок и ссылок
```bash
./bridge-cli note send "https://github.com/Anhelm01/Bridge_Local"
./bridge-cli note history
```

### 3.5. Машиночитаемый режим для ИИ (agy_cli)
Все команды поддерживают флаг `--json`:
```bash
./bridge-cli --json status
./bridge-cli --json exec "whoami"
```
Коды возврата:
- `0` — Успешно
- `1` — Ошибка аргументов / конфигурации
- `2` — Сеть недоступна (Host unreachable)
- `3` — Ошибка авторизации (PSK token mismatch)
- `4` — Удаленная команда завершилась с ненулевым кодом
- `5` — Превышен таймаут выполнения

---

## 4. Фоновая синхронизация (Systemd User Service)

Для непрерывной двусторонней синхронизации каталога `pocket/` можно настроить службу пользователя systemd:
```bash
mkdir -p ~/.config/systemd/user
cat << 'EOF' > ~/.config/systemd/user/bridge-sync.service
[Unit]
Description=Bridge Local Client File Sync Watcher
After=network.target

[Service]
Type=simple
ExecStart=%h/BridgeLocal/bridge-cli pocket sync --direction both
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now bridge-sync.service
```

---

## 5. Устранение неполадок
1. **Host Unreachable (Код 2):**
   - Убедитесь, что на Windows запущена служба (`bridge-agent.exe run` или через SCM).
   - Проверьте, что брандмауэр Windows не блокирует входящий порт 9732.
2. **Auth Failed (Код 3):**
   - Токен `psk_token` в файле `bridge.toml` на Linux должен строго совпадать с токеном на Windows.
   - Проверьте системное время: при расхождении часов более чем на 60 секунд срабатывает защита от replay-атак.
