# Развертывание и сборка Bridge Local с 0

Пошаговая инструкция по сборке, установке и запуску платформы Bridge Local на Linux и Windows без лишней теории.

---

## Вариант 1. Запуск из готовых релизных архивов (Быстрый старт)

Релизные архивы скачиваются со страницы GitHub Releases (`BridgeLocal-Windows-x64.zip` и `BridgeLocal-Linux-x64.zip`).

### Часть 1: Настройка Windows (Серверный агент)

1. Распакуйте `BridgeLocal-Windows-x64.zip` в любую папку (например, `C:\BridgeLocal`).
2. Запустите двойным кликом `setup_connection.bat`:
   - Мастер автоматически определит локальные IPv4-адреса сетевых карт (например, `192.168.1.150`).
   - Подтвердите порт по умолчанию (`9732`) и секретный токен PSK.
   - Нажмите Enter. Настройки сохранятся в `bridge.toml`, и на экране появится строка подключения для Linux.
3. Выберите способ запуска:
   - **Для отладки в окне консоли:** Запустите `run_agent.bat`.
   - **Для постоянной работы в фоне:** Кликните правой кнопкой по `install_service.bat` -> **«Запуск от имени администратора»**. Это зарегистрирует службу Windows `BridgeLocalAgent` с автозапуском и добавит пункт «Отправить в Карман» в контекстное меню Проводника.

### Часть 2: Настройка Linux (Клиент и TUI)

1. Распакуйте `BridgeLocal-Linux-x64.zip` в удобный каталог:
   ```bash
   unzip BridgeLocal-Linux-x64.zip -d ~/BridgeLocal
   cd ~/BridgeLocal
   chmod +x bridge-cli
   ```
2. Подключитесь к машине Windows (укажите IP из шага 2 на Windows):
   ```bash
   ./bridge-cli connect 192.168.1.150:9732
   ```
3. Проверьте связь:
   ```bash
   ./bridge-cli ping
   ```
4. Запустите интерактивную панель управления:
   ```bash
   ./bridge-cli tui
   ```

---

## Вариант 2. Сборка бинарных пакетов из исходного кода с 0

### Требования к окружению

- **Linux:** Python 3.12+ или пакетный менеджер `uv`, утилита `zip`.
- **Windows:** Python 3.12+ (или `uv`), PowerShell 5.1+.
- **Репозиторий:**
  ```bash
  git clone git@github.com:Anhelm01/Bridge_Local.git
  cd Bridge_Local
  ```

---

### Сборка на Linux (Клиент `bridge-cli` и ZIP)

Выполните один скрипт в корне репозитория:
```bash
./scripts/build-linux-client.sh
```

Что делает скрипт:
1. Собирает Python-пакет и wheel через `uv build`.
2. Запускает PyInstaller по спецификации `bridge-cli.spec`.
3. Создает автономный ELF-бинарник `dist/bridge-cli` (~21 МБ).
4. Упаковывает релизный архив `dist/BridgeLocal-Linux-x64.zip` (бинарник, `bridge.toml`, `pocket/`, документация `README.md` и systemd-юниты).

Проверка сборки:
```bash
./dist/bridge-cli --help
```

---

### Сборка на Windows (Агент `bridge-agent.exe` и ZIP)

1. Откройте PowerShell в корне репозитория и установите зависимости сборщика:
   ```powershell
   pip install --upgrade pip
   pip install pyinstaller pywin32 psutil pydantic watchdog typer rich
   pip install -e .
   ```

2. Скомпилируйте исполняемый файл:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-agent.ps1
   ```
   Результат: автономный файл `dist\bridge-agent.exe`.

3. Соберите релизный ZIP-дистрибутив:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\package-windows-dist.ps1
   ```
   Результат: архив `dist\BridgeLocal-Windows-x64.zip` (бинарник `bridge-agent.exe`, конфигурация `bridge.toml`, батники `setup_connection.bat`, `run_agent.bat`, `install_service.bat`, `uninstall_service.bat`, каталог `pocket\` и `README.md`).

---

## Вариант 3. Запуск напрямую из исходников (Для разработчиков без компиляции)

### На Windows:
```powershell
# 1. Установка зависимостей в виртуальное окружение:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[windows,dev]"

# 2. Интерактивная настройка:
python -m bridge_agent_win.cli setup

# 3. Запуск агента:
python -m bridge_agent_win.cli run
```

### На Linux:
```bash
# 1. Синхронизация зависимостей через uv:
uv sync --extra dev --extra linux

# 2. Быстрое подключение к Windows:
uv run bridge-cli connect 192.168.1.150:9732

# 3. Запуск TUI:
uv run bridge-cli tui
```

---

## Шпаргалка по портам и брандмауэру

- **Порт:** `9732` (TCP).
- Если Windows блокирует подключения от Linux, выполните в PowerShell от имени Администратора:
  ```powershell
  New-NetFirewallRule -DisplayName "Bridge Local" -Direction Inbound -LocalPort 9732 -Protocol TCP -Action Allow
  ```
- Для удаления службы Windows выполните от имени Администратора:
  ```cmd
  uninstall_service.bat
  ```
