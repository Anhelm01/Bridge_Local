#!/usr/bin/env bash
# ==============================================================================
# BRIDGE LOCAL — ЕДИНЫЙ ЦЕНТР УПРАВЛЕНИЯ И НАСТРОЙКИ (LINUX CLIENT)
# Интерактивная консоль для быстрого старта, глобальной настройки и смены узлов
# ==============================================================================
# Интерактивная консоль — без set -e

# Определение каталогов
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"
cd "${REPO_ROOT}"

# Цветовая палитра терминала (ANSI 256 / TrueColor)
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_DIM="\033[2m"
C_RED="\033[38;5;196m"
C_GREEN="\033[38;5;82m"
C_YELLOW="\033[38;5;220m"
C_BLUE="\033[38;5;39m"
C_MAGENTA="\033[38;5;213m"
C_CYAN="\033[38;5;51m"
C_WHITE="\033[38;5;255m"
C_GRAY="\033[38;5;245m"

# Функция запуска bridge-cli с чистым LD_PRELOAD
run_bridge() {
    if [[ -x "$HOME/.local/bin/bridge-cli" ]]; then
        LD_PRELOAD="" "$HOME/.local/bin/bridge-cli" "$@"
    elif [[ -x "$REPO_ROOT/dist/bridge-cli" ]]; then
        LD_PRELOAD="" "$REPO_ROOT/dist/bridge-cli" "$@"
    else
        LD_PRELOAD="" uv --project "$REPO_ROOT" run bridge-cli "$@"
    fi
}

# Функция извлечения параметров из конфига
get_config_info() {
    local py_cmd=""
    if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        py_cmd="${REPO_ROOT}/.venv/bin/python"
    elif command -v uv >/dev/null 2>&1; then
        py_cmd="uv --project ${REPO_ROOT} run python"
    fi

    if [[ -n "$py_cmd" ]]; then
        LD_PRELOAD="" $py_cmd -c "
try:
    from bridge_core.config import BridgeConfig
    cfg = BridgeConfig.load()
    p_path = str(cfg._config_path.resolve()) if cfg._config_path else 'bridge.toml'
    p_host = cfg.connection.host
    p_port = str(cfg.connection.port)
    p_tok = cfg.connection.psk_token or ''
    p_pocket = str(cfg.get_pocket_dir())
    print(f'{p_path}|{p_host}|{p_port}|{p_tok}|{p_pocket}')
except Exception:
    print('bridge.toml|192.168.100.2|9732||./pocket')
" 2>/dev/null
    else
        echo "bridge.toml|192.168.100.2|9732||./pocket"
    fi
}

# Функция быстрого зонда сокета Windows (таймаут 0.4 сек)
probe_socket() {
    local target_host="$1"
    local target_port="$2"
    LD_PRELOAD="" python3 -c "
import socket, time, sys
t0 = time.perf_counter()
try:
    s = socket.create_connection(('${target_host}', int('${target_port}')), timeout=0.4)
    s.close()
    ms = (time.perf_counter() - t0) * 1000
    print(f'ONLINE:{ms:.1f}')
except Exception:
    print('OFFLINE')
" 2>/dev/null || echo "OFFLINE"
}

# Отрисовка шапки статуса
render_header() {
    clear
    echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"
    echo -e "         ${C_BOLD}${C_WHITE}BRIDGE LOCAL — ЕДИНЫЙ ЦЕНТР УПРАВЛЕНИЯ (LINUX CLIENT)${C_RESET}"
    echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"

    # Чтение текущей конфигурации
    IFS="|" read -r CFG_FILE CFG_HOST CFG_PORT CFG_TOK CFG_POCKET < <(get_config_info)
    
    # Проверка связи
    PROBE_RES=$(probe_socket "$CFG_HOST" "$CFG_PORT")
    if [[ "$PROBE_RES" =~ ^ONLINE:(.*) ]]; then
        PING_MS="${BASH_REMATCH[1]}"
        NET_STATUS="${C_GREEN}● ONLINE${C_RESET} ${C_GRAY}(отклик ${PING_MS} мс)${C_RESET}"
    else
        NET_STATUS="${C_RED}○ OFFLINE${C_RESET} ${C_GRAY}(узел Windows недоступен)${C_RESET}"
    fi

    # Проверка глобального wrapper
    if [[ -x "$HOME/.local/bin/bridge-cli" ]]; then
        CLI_STATUS="${C_GREEN}Установлен${C_RESET} ${C_GRAY}(~/.local/bin/bridge-cli)${C_RESET}"
    else
        CLI_STATUS="${C_YELLOW}Не установлен${C_RESET} ${C_GRAY}(только через uv run)${C_RESET}"
    fi

    # Проверка PATH
    if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
        PATH_STATUS="${C_GREEN}Настроен${C_RESET}"
    else
        PATH_STATUS="${C_YELLOW}Не найден в PATH${C_RESET} ${C_GRAY}(~/.local/bin отсутствует)${C_RESET}"
    fi

    # Проверка службы systemd
    if systemctl --user is-active --quiet bridge-client-sync.service 2>/dev/null; then
        SVC_STATUS="${C_GREEN}Активна (Running)${C_RESET}"
    elif systemctl --user is-enabled --quiet bridge-client-sync.service 2>/dev/null; then
        SVC_STATUS="${C_YELLOW}Включена (Stopped)${C_RESET}"
    else
        SVC_STATUS="${C_GRAY}Не установлена${C_RESET}"
    fi

    # Токен превью
    if [[ -n "$CFG_TOK" ]]; then
        TOK_PREVIEW="${CFG_TOK:0:8}..."
    else
        TOK_PREVIEW="${C_DIM}(не задан)${C_RESET}"
    fi

    echo -e " ${C_BOLD}Целевой узел Windows:${C_RESET} ${C_CYAN}${CFG_HOST}:${CFG_PORT}${C_RESET} ──► Статус: ${NET_STATUS}"
    echo -e " ${C_BOLD}Активный конфиг:${C_RESET}     ${C_WHITE}${CFG_FILE}${C_RESET}"
    echo -e " ${C_BOLD}Каталог кармана:${C_RESET}     ${C_WHITE}${CFG_POCKET}${C_RESET}"
    echo -e " ${C_BOLD}Ключ безопасности:${C_RESET}   ${C_WHITE}${TOK_PREVIEW}${C_RESET}"
    echo -e " ${C_BOLD}Глобальный CLI:${C_RESET}      ${CLI_STATUS} | PATH: ${PATH_STATUS}"
    echo -e " ${C_BOLD}Фоновый синхронизатор:${C_RESET} ${SVC_STATUS}"
    echo -e "${C_CYAN}──────────────────────────────────────────────────────────────────────────────${C_RESET}"
}

# Подпрограмма: Быстрый старт под ключ
action_quick_start() {
    echo -e "\n${C_BOLD}${C_GREEN}═══ [1] БЫСТРЫЙ СТАРТ ПОД КЛЮЧ ═══${C_RESET}"
    echo -e "${C_GRAY}Мастер полностью настроит систему для работы с любого терминала и папки.${C_RESET}\n"

    IFS="|" read -r CFG_FILE CFG_HOST CFG_PORT CFG_TOK CFG_POCKET < <(get_config_info)

    # 1. Запрос IP целевого узла
    read -rp "1/4. Введите IP-адрес или имя Windows хоста [Enter = ${CFG_HOST}]: " INPUT_HOST
    INPUT_HOST="${INPUT_HOST:-$CFG_HOST}"

    # 2. Запрос порта
    read -rp "2/4. Введите TCP-порт [Enter = ${CFG_PORT}]: " INPUT_PORT
    INPUT_PORT="${INPUT_PORT:-$CFG_PORT}"

    # 3. Запрос токена
    read -rp "3/4. Введите PSK-токен [Enter = сохранить текущий]: " INPUT_TOK
    INPUT_TOK="${INPUT_TOK:-$CFG_TOK}"

    # 4. Запрос пути к карману
    DEFAULT_POCKET="$HOME/BridgeLocal/pocket"
    read -rp "4/4. Абсолютный путь к единому карману [Enter = ${DEFAULT_POCKET}]: " INPUT_POCKET
    INPUT_POCKET="${INPUT_POCKET:-$DEFAULT_POCKET}"
    INPUT_POCKET="${INPUT_POCKET/#\~/$HOME}"

    echo -e "\n${C_CYAN}[1/5] Создание каталога кармана...${C_RESET}"
    mkdir -p "${INPUT_POCKET}"
    echo -e "${C_GREEN}[OK] Каталог кармана готов: ${INPUT_POCKET}${C_RESET}"

    echo -e "\n${C_CYAN}[2/5] Настройка центрального конфига ~/.config/bridge-local/bridge.toml...${C_RESET}"
    mkdir -p "$HOME/.config/bridge-local"
    TARGET_CFG="$HOME/.config/bridge-local/bridge.toml"
    
    # Сохраняем в центральный конфиг
    cat << EOF > "${TARGET_CFG}"
[node]
name = "workstation-linux"
display_name = "Linux Host"

[connection]
host = "${INPUT_HOST}"
port = ${INPUT_PORT}
timeout_sec = 5.0
psk_token = "${INPUT_TOK}"

[heartbeat]
interval_sec = 2.0
timeout_sec = 1.5
max_missed = 3
reconnect_delay_sec = 5.0

[pocket]
path = "${INPUT_POCKET}"
logs_subdir = "logs"
sync_watch = true
max_chunk_size = 65536
log_max_days = 30

[exec]
default_timeout_sec = 30
run_as_admin = true
force_utf8 = true

[logging]
level = "TRACE"
dev_mode = true
console_output = true
file_output = ""
EOF
    echo -e "${C_GREEN}[OK] Центральный конфиг сохранён: ${TARGET_CFG}${C_RESET}"

    # Также обновим репозиторный bridge.toml для удобства разработки
    if [[ -f "${REPO_ROOT}/bridge.toml" ]]; then
        run_bridge config set --host "${INPUT_HOST}" --port "${INPUT_PORT}" --token "${INPUT_TOK}" --config "${REPO_ROOT}/bridge.toml" >/dev/null 2>&1 || true
    fi

    echo -e "\n${C_CYAN}[3/5] Создание глобального wrapper ~/.local/bin/bridge-cli...${C_RESET}"
    mkdir -p "$HOME/.local/bin"
    cat << 'WRAPPER_EOF' > "$HOME/.local/bin/bridge-cli"
#!/usr/bin/env bash
# Bridge Local Global CLI Wrapper with LD_PRELOAD bypass
export BRIDGE_CONFIG="${BRIDGE_CONFIG:-$HOME/.config/bridge-local/bridge.toml}"

REPO_DIR="REPO_PLACEHOLDER"

if [[ -f "${REPO_DIR}/dist/bridge-cli" ]]; then
    LD_PRELOAD="" exec "${REPO_DIR}/dist/bridge-cli" "$@"
elif command -v uv >/dev/null 2>&1 && [[ -d "${REPO_DIR}" ]]; then
    LD_PRELOAD="" exec uv --project "${REPO_DIR}" run bridge-cli "$@"
else
    echo "[ERROR] Не удалось запустить bridge-cli: ни dist/bridge-cli, ни uv не найдены" >&2
    exit 1
fi
WRAPPER_EOF
    sed -i "s|REPO_PLACEHOLDER|${REPO_ROOT}|g" "$HOME/.local/bin/bridge-cli"
    chmod +x "$HOME/.local/bin/bridge-cli"
    echo -e "${C_GREEN}[OK] Wrapper создан: ~/.local/bin/bridge-cli${C_RESET}"

    echo -e "\n${C_CYAN}[4/5] Проверка переменной PATH...${C_RESET}"
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo -e "${C_YELLOW}[!] ~/.local/bin отсутствует в текущем PATH.${C_RESET}"
        if [[ -f "$HOME/.bashrc" ]] && ! grep -q 'HOME/.local/bin' "$HOME/.bashrc"; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
            echo -e "${C_GREEN}[OK] Строка добавления в PATH внесена в ~/.bashrc${C_RESET}"
        fi
        if [[ -f "$HOME/.zshrc" ]] && ! grep -q 'HOME/.local/bin' "$HOME/.zshrc"; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
            echo -e "${C_GREEN}[OK] Строка добавления в PATH внесена в ~/.zshrc${C_RESET}"
        fi
    else
        echo -e "${C_GREEN}[OK] PATH уже содержит ~/.local/bin${C_RESET}"
    fi

    echo -e "\n${C_CYAN}[5/5] Тестовое подключение к Windows (${INPUT_HOST}:${INPUT_PORT})...${C_RESET}"
    TEST_PROBE=$(probe_socket "${INPUT_HOST}" "${INPUT_PORT}")
    if [[ "$TEST_PROBE" =~ ^ONLINE:(.*) ]]; then
        echo -e "${C_GREEN}════════════════════════════════════════════════════════════════${C_RESET}"
        echo -e "${C_GREEN}  [SUCCESS] Соединение установлено! Отклик: ${BASH_REMATCH[1]} мс${C_RESET}"
        echo -e "${C_GREEN}════════════════════════════════════════════════════════════════${C_RESET}"
    else
        echo -e "${C_YELLOW}════════════════════════════════════════════════════════════════${C_RESET}"
        echo -e "${C_YELLOW}  [WARN] Узел Windows пока не отвечает на порту ${INPUT_PORT}.${C_RESET}"
        echo -e "${C_YELLOW}  Убедитесь, что на Windows запущен start.bat или служба Windows!${C_RESET}"
        echo -e "${C_YELLOW}════════════════════════════════════════════════════════════════${C_RESET}"
    fi

    echo ""
    read -rp "Открыть TUI Дашборд прямо сейчас? [Y/n]: " LAUNCH_TUI
    LAUNCH_TUI="${LAUNCH_TUI:-y}"
    if [[ "$LAUNCH_TUI" =~ ^[YyДд]$ ]]; then
        run_bridge tui
    fi
}

# Подпрограмма: Смена целевого устройства
action_change_target() {
    echo -e "\n${C_BOLD}${C_CYAN}═══ [2] СМЕНИТЬ ЦЕЛЕВОЕ УСТРОЙСТВО / СЕТЬ ═══${C_RESET}"
    echo -e "${C_GRAY}Быстрое переключение IP-адреса хоста Windows без редактирования файлов.${C_RESET}\n"

    IFS="|" read -r CFG_FILE CFG_HOST CFG_PORT CFG_TOK CFG_POCKET < <(get_config_info)

    echo -e "Текущая цель: ${C_WHITE}${CFG_HOST}:${CFG_PORT}${C_RESET}"
    echo ""
    echo -e "Введите новый адрес в формате ${C_CYAN}IP:PORT${C_RESET} или просто ${C_CYAN}IP${C_RESET}:"
    read -rp "--> [Enter = оставить ${CFG_HOST}:${CFG_PORT}]: " RAW_INPUT

    if [[ -z "$RAW_INPUT" ]]; then
        echo -e "${C_GRAY}Адрес не изменен.${C_RESET}"
    else
        if [[ "$RAW_INPUT" == *":"* ]]; then
            NEW_HOST="${RAW_INPUT%%:*}"
            NEW_PORT="${RAW_INPUT##*:}"
        else
            NEW_HOST="$RAW_INPUT"
            read -rp "Введите TCP-порт [Enter = ${CFG_PORT}]: " NEW_PORT
            NEW_PORT="${NEW_PORT:-$CFG_PORT}"
        fi

        read -rp "Обновить PSK-токен? [Enter = оставить текущий]: " NEW_TOK
        NEW_TOK="${NEW_TOK:-$CFG_TOK}"

        echo -e "\n${C_CYAN}Сохранение настроек...${C_RESET}"
        run_bridge config set --host "$NEW_HOST" --port "$NEW_PORT" --token "$NEW_TOK"
        
        # Если есть глобальный конфиг, обновим и его
        if [[ -f "$HOME/.config/bridge-local/bridge.toml" ]]; then
            run_bridge config set --host "$NEW_HOST" --port "$NEW_PORT" --token "$NEW_TOK" --config "$HOME/.config/bridge-local/bridge.toml" >/dev/null 2>&1 || true
        fi

        echo -e "${C_GREEN}[OK] Настройки обновлены на ${NEW_HOST}:${NEW_PORT}!${C_RESET}"

        # Проверка отклика
        echo -e "${C_CYAN}Проверка сокета...${C_RESET}"
        TEST_PROBE=$(probe_socket "${NEW_HOST}" "${NEW_PORT}")
        if [[ "$TEST_PROBE" =~ ^ONLINE:(.*) ]]; then
            echo -e "${C_GREEN}● [ONLINE] Узел доступен! Пинг: ${BASH_REMATCH[1]} мс${C_RESET}"
        else
            echo -e "${C_RED}○ [OFFLINE] Узел ${NEW_HOST}:${NEW_PORT} пока не отвечает.${C_RESET}"
        fi
    fi

    echo ""
    read -rp "Нажмите Enter для возврата в меню..." _
}

# Подпрограмма: Глобальная настройка
action_setup_global() {
    echo -e "\n${C_BOLD}${C_CYAN}═══ [3] НАСТРОЙКА ГЛОБАЛЬНОГО ДОСТУПА ПО УМОЛЧАНИЮ ═══${C_RESET}"
    echo -e "${C_GRAY}Установка bridge-cli в ~/.local/bin/ для запуска из любой папки.${C_RESET}\n"

    mkdir -p "$HOME/.local/bin" "$HOME/.config/bridge-local"
    DEFAULT_POCKET="$HOME/BridgeLocal/pocket"
    mkdir -p "$DEFAULT_POCKET"

    # Wrapper
    cat << 'WRAPPER_EOF' > "$HOME/.local/bin/bridge-cli"
#!/usr/bin/env bash
export BRIDGE_CONFIG="${BRIDGE_CONFIG:-$HOME/.config/bridge-local/bridge.toml}"

REPO_DIR="REPO_PLACEHOLDER"

if [[ -f "${REPO_DIR}/dist/bridge-cli" ]]; then
    LD_PRELOAD="" exec "${REPO_DIR}/dist/bridge-cli" "$@"
elif command -v uv >/dev/null 2>&1 && [[ -d "${REPO_DIR}" ]]; then
    LD_PRELOAD="" exec uv --project "${REPO_DIR}" run bridge-cli "$@"
else
    echo "[ERROR] Не удалось запустить bridge-cli: ни dist/bridge-cli, ни uv не найдены" >&2
    exit 1
fi
WRAPPER_EOF
    sed -i "s|REPO_PLACEHOLDER|${REPO_ROOT}|g" "$HOME/.local/bin/bridge-cli"
    chmod +x "$HOME/.local/bin/bridge-cli"
    echo -e "${C_GREEN}[OK] Создан исполняемый wrapper: ~/.local/bin/bridge-cli${C_RESET}"

    # Копирование bridge.toml в ~/.config/bridge-local если там его нет
    if [[ ! -f "$HOME/.config/bridge-local/bridge.toml" ]] && [[ -f "${REPO_ROOT}/bridge.toml" ]]; then
        cp "${REPO_ROOT}/bridge.toml" "$HOME/.config/bridge-local/bridge.toml"
        echo -e "${C_GREEN}[OK] Создан шаблон конфигурации: ~/.config/bridge-local/bridge.toml${C_RESET}"
    fi

    # Проверка PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo -e "${C_YELLOW}[!] Каталог ~/.local/bin отсутствует в вашем переменной PATH.${C_RESET}"
        read -rp "Добавить ~/.local/bin в ~/.bashrc? [Y/n]: " ADD_PATH
        ADD_PATH="${ADD_PATH:-y}"
        if [[ "$ADD_PATH" =~ ^[YyДд]$ ]]; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
            [[ -f "$HOME/.zshrc" ]] && echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
            echo -e "${C_GREEN}[OK] Строка добавлена в конфигурацию командной оболочки.${C_RESET}"
        fi
    else
        echo -e "${C_GREEN}[OK] PATH настроен корректно.${C_RESET}"
    fi

    # Тест
    echo -e "\n${C_CYAN}Тестовый вызов из /tmp...${C_RESET}"
    (cd /tmp && "$HOME/.local/bin/bridge-cli" --help >/dev/null 2>&1) && \
        echo -e "${C_GREEN}[OK] Команда bridge-cli успешно вызывается из любого каталога!${C_RESET}" || \
        echo -e "${C_YELLOW}[WARN] Вызов завершился с предупреждением (проверьте uv или dist).${C_RESET}"

    echo ""
    read -rp "Нажмите Enter для возврата в меню..." _
}

# Подпрограмма: Пинг и сводный статус
action_ping_and_status() {
    echo -e "\n${C_BOLD}${C_CYAN}═══ [5] ДИАГНОСТИКА И СТАТУС СЕТИ ═══${C_RESET}\n"
    echo -e "${C_CYAN}1. Выполнение серии Heartbeat-пингов (3 зонда)...${C_RESET}"
    run_bridge ping --count 3 || true
    echo ""
    echo -e "${C_CYAN}2. Запрос сводного статуса всех подсистем...${C_RESET}"
    run_bridge status || true
    echo ""
    read -rp "Нажмите Enter для возврата в меню..." _
}

# Подпрограмма: Удаленный PowerShell
action_remote_exec() {
    echo -e "\n${C_BOLD}${C_CYAN}═══ [6] ИНТЕРАКТИВНАЯ КОНСОЛЬ POWERSHELL (WINDOWS) ═══${C_RESET}"
    echo -e "${C_GRAY}Команды выполняются на удаленной машине Windows. Рабочая директория сохраняется.${C_RESET}"
    echo -e "${C_GRAY}Для возврата в меню введите: exit или q${C_RESET}\n"

    while true; do
        read -rp "PS Win> " REMOTE_CMD
        [[ -z "$REMOTE_CMD" ]] && continue
        if [[ "$REMOTE_CMD" == "exit" || "$REMOTE_CMD" == "q" || "$REMOTE_CMD" == "quit" ]]; then
            break
        fi
        run_bridge exec "$REMOTE_CMD" || true
        echo ""
    done
}

# Подпрограмма: Карман
action_pocket_menu() {
    while true; do
        clear
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"
        echo -e "                   ${C_BOLD}${C_WHITE}УПРАВЛЕНИЕ КАРМАНОМ (POCKET STORAGE)${C_RESET}"
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}\n"
        echo -e "   ${C_BOLD}[1]${C_RESET} Показать список файлов в Кармане"
        echo -e "   ${C_BOLD}[2]${C_RESET} Отправить файл в Карман Windows (Drop / Send)"
        echo -e "   ${C_BOLD}[3]${C_RESET} Скачать файл из Кармана Windows (Pull)"
        echo -e "   ${C_BOLD}[4]${C_RESET} Принудительная двусторонняя синхронизация (Sync)"
        echo -e "   ${C_BOLD}[5]${C_RESET} Открыть каталог Кармана в файловом менеджере"
        echo -e "   ${C_BOLD}[0]${C_RESET} Назад в главное меню\n"
        read -rp "Выберите действие [0-5]: " POCKET_CHOICE
        case "$POCKET_CHOICE" in
            1)
                echo ""
                run_bridge pocket list
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            2)
                echo ""
                read -rp "Введите путь к файлу для отправки: " FILE_TO_SEND
                FILE_TO_SEND="${FILE_TO_SEND/#\~/$HOME}"
                if [[ -f "$FILE_TO_SEND" ]]; then
                    run_bridge pocket drop "$FILE_TO_SEND"
                else
                    echo -e "${C_RED}[ERROR] Файл '$FILE_TO_SEND' не найден!${C_RESET}"
                fi
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            3)
                echo ""
                read -rp "Введите относительное имя файла в удаленном кармане: " FILE_TO_PULL
                if [[ -n "$FILE_TO_PULL" ]]; then
                    run_bridge pocket pull "$FILE_TO_PULL"
                fi
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            4)
                echo ""
                echo -e "${C_CYAN}Запуск двусторонней синхронизации файлов...${C_RESET}"
                run_bridge pocket sync
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            5)
                IFS="|" read -r _ _ _ _ CFG_POCKET < <(get_config_info)
                mkdir -p "$CFG_POCKET"
                xdg-open "$CFG_POCKET" >/dev/null 2>&1 &
                echo -e "${C_GREEN}[OK] Открыт каталог: ${CFG_POCKET}${C_RESET}"
                sleep 1
                ;;
            0)
                break
                ;;
            *)
                echo -e "${C_RED}Неверный ввод!${C_RESET}"
                sleep 1
                ;;
        esac
    done
}

# Подпрограмма: Заметки
action_notes_menu() {
    while true; do
        clear
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"
        echo -e "                     ${C_BOLD}${C_WHITE}ОПЕРАТИВНЫЕ ЗАМЕТКИ (NOTES ENGINE)${C_RESET}"
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}\n"
        echo -e "   ${C_BOLD}[1]${C_RESET} Отправить быструю заметку / ссылку на Windows"
        echo -e "   ${C_BOLD}[2]${C_RESET} Показать последние заметки"
        echo -e "   ${C_BOLD}[3]${C_RESET} Очистить журнал заметок"
        echo -e "   ${C_BOLD}[0]${C_RESET} Назад в главное меню\n"
        read -rp "Выберите действие [0-3]: " NOTES_CHOICE
        case "$NOTES_CHOICE" in
            1)
                echo ""
                read -rp "Введите текст заметки или ссылку: " NOTE_TEXT
                if [[ -n "$NOTE_TEXT" ]]; then
                    run_bridge note send "$NOTE_TEXT"
                fi
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            2)
                echo ""
                run_bridge note list
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            3)
                echo ""
                run_bridge note clear
                echo -e "${C_GREEN}[OK] Журнал заметок очищен.${C_RESET}"
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            0)
                break
                ;;
            *)
                echo -e "${C_RED}Неверный ввод!${C_RESET}"
                sleep 1
                ;;
        esac
    done
}

# Подпрограмма: Фоновая служба Systemd
action_systemd_menu() {
    while true; do
        clear
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"
        echo -e "             ${C_BOLD}${C_WHITE}ФОНОВАЯ СЛУЖБА SYSTEMD (USER DAEMON / SYNC)${C_RESET}"
        echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}\n"
        
        if systemctl --user is-active --quiet bridge-client-sync.service 2>/dev/null; then
            CURRENT_SVC="${C_GREEN}● РАБОТАЕТ (Active)${C_RESET}"
        else
            CURRENT_SVC="${C_RED}○ ОСТАНОВЛЕНА / НЕ НАСТРОЕНА${C_RESET}"
        fi
        echo -e "Текущий статус службы: ${CURRENT_SVC}\n"

        echo -e "   ${C_BOLD}[1]${C_RESET} Установить и активировать службу (Auto-Sync Pocket)"
        echo -e "   ${C_BOLD}[2]${C_RESET} Запустить службу"
        echo -e "   ${C_BOLD}[3]${C_RESET} Остановить службу"
        echo -e "   ${C_BOLD}[4]${C_RESET} Показать статус службы (systemctl status)"
        echo -e "   ${C_BOLD}[5]${C_RESET} Просмотр живого журнала логов (journalctl -f)"
        echo -e "   ${C_BOLD}[6]${C_RESET} Удалить службу из системы"
        echo -e "   ${C_BOLD}[0]${C_RESET} Назад в главное меню\n"
        read -rp "Выберите действие [0-6]: " SVC_CHOICE
        case "$SVC_CHOICE" in
            1)
                echo -e "\n${C_CYAN}Регистрация пользовательской службы systemd...${C_RESET}"
                mkdir -p "$HOME/.config/systemd/user"
                cat << 'SVC_EOF' > "$HOME/.config/systemd/user/bridge-client-sync.service"
[Unit]
Description=Bridge Local Client — Background Pocket File Sync Watcher
Documentation=https://github.com/Anhelm01/Bridge_Local
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/bridge-cli pocket sync --watch --interval 3.0
Restart=always
RestartSec=5s
Environment=PYTHONUNBUFFERED=1
Environment=LD_PRELOAD=

[Install]
WantedBy=default.target
SVC_EOF
                systemctl --user daemon-reload
                systemctl --user enable --now bridge-client-sync.service
                echo -e "${C_GREEN}[OK] Служба зарегистрирована и запущена!${C_RESET}"
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            2)
                systemctl --user start bridge-client-sync.service
                echo -e "${C_GREEN}[OK] Команда запуска отправлена.${C_RESET}"
                sleep 1
                ;;
            3)
                systemctl --user stop bridge-client-sync.service
                echo -e "${C_YELLOW}[OK] Служба остановлена.${C_RESET}"
                sleep 1
                ;;
            4)
                echo ""
                systemctl --user status bridge-client-sync.service --no-pager || true
                echo ""
                read -rp "Нажмите Enter..." _
                ;;
            5)
                echo -e "\n${C_CYAN}Вывод журнала службы (для выхода нажмите Ctrl+C)...${C_RESET}\n"
                journalctl --user -u bridge-client-sync.service -f || true
                ;;
            6)
                echo -e "\n${C_YELLOW}Удаление службы...${C_RESET}"
                systemctl --user stop bridge-client-sync.service 2>/dev/null || true
                systemctl --user disable bridge-client-sync.service 2>/dev/null || true
                rm -f "$HOME/.config/systemd/user/bridge-client-sync.service"
                systemctl --user daemon-reload
                echo -e "${C_GREEN}[OK] Служба успешно удалена.${C_RESET}"
                sleep 1
                ;;
            0)
                break
                ;;
            *)
                echo -e "${C_RED}Неверный ввод!${C_RESET}"
                sleep 1
                ;;
        esac
    done
}

# Подпрограмма: Сборка PyInstaller
action_build_binary() {
    echo -e "\n${C_BOLD}${C_CYAN}═══ [10] СБОРКА АВТОНОМНОГО БИНАРНИКА (DIST) ═══${C_RESET}\n"
    if [[ -f "${REPO_ROOT}/scripts/build-linux-client.sh" ]]; then
        bash "${REPO_ROOT}/scripts/build-linux-client.sh"
    else
        echo -e "${C_RED}[ERROR] Скрипт scripts/build-linux-client.sh не найден!${C_RESET}"
    fi
    echo ""
    read -rp "Нажмите Enter для возврата в меню..." _
}

# Подпрограмма: Удаление и очистка
action_uninstall() {
    echo -e "\n${C_BOLD}${C_RED}═══ [11] ПОЛНАЯ ОЧИСТКА И УДАЛЕНИЕ ═══${C_RESET}"
    echo -e "${C_YELLOW}Вы собираетесь удалить глобальные настройки Bridge Local на этой машине.${C_RESET}\n"
    read -rp "Вы уверены? [y/N]: " CONFIRM_UNINSTALL
    if [[ "$CONFIRM_UNINSTALL" =~ ^[YyДд]$ ]]; then
        systemctl --user stop bridge-client-sync.service 2>/dev/null || true
        systemctl --user disable bridge-client-sync.service 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/bridge-client-sync.service"
        systemctl --user daemon-reload 2>/dev/null || true
        rm -f "$HOME/.local/bin/bridge-cli"
        echo -e "${C_GREEN}[OK] Wrapper ~/.local/bin/bridge-cli и служба удалены.${C_RESET}"
        
        read -rp "Удалить также конфигурацию ~/.config/bridge-local/? [y/N]: " DEL_CFG
        if [[ "$DEL_CFG" =~ ^[YyДд]$ ]]; then
            rm -rf "$HOME/.config/bridge-local"
            echo -e "${C_GREEN}[OK] Каталог ~/.config/bridge-local удален.${C_RESET}"
        fi
    else
        echo -e "${C_GRAY}Отмена очистки.${C_RESET}"
    fi
    echo ""
    read -rp "Нажмите Enter для возврата в меню..." _
}

# Главный цикл меню
while true; do
    render_header
    echo -e "   ${C_BOLD}${C_GREEN}[1] БЫСТРЫЙ СТАРТ ПОД КЛЮЧ (Рекомендуется)${C_RESET}"
    echo -e "       ${C_GRAY}--> Интерактивная смена цели, создание wrapper, PATH, конфига и запуск${C_RESET}\n"
    echo -e "   ${C_BOLD}[2]${C_RESET} Сменить целевое устройство / сеть ${C_CYAN}(IP, Порт, Токен)${C_RESET}"
    echo -e "   ${C_BOLD}[3]${C_RESET} Настроить глобальный доступ по умолчанию ${C_GRAY}(~/.local/bin/bridge-cli)${C_RESET}"
    echo -e "   ${C_BOLD}[4]${C_RESET} Запустить оперативный ${C_MAGENTA}TUI Дашборд${C_RESET} (F1-F8)"
    echo -e "   ${C_BOLD}[5]${C_RESET} Диагностика и проверка связи (Ping & Status)"
    echo -e "   ${C_BOLD}[6]${C_RESET} Выполнить команду на Windows ${C_YELLOW}(Remote PowerShell Exec)${C_RESET}"
    echo -e "   ${C_BOLD}[7]${C_RESET} Управление Карманом (Отправка, Скачивание, Синхронизация)"
    echo -e "   ${C_BOLD}[8]${C_RESET} Оперативные заметки и ссылки (Notes Engine)"
    echo -e "   ${C_BOLD}[9]${C_RESET} Фоновая служба синхронизации (Systemd User Service)"
    echo -e "   ${C_BOLD}[10]${C_RESET} Пересобрать автономный бинарник (dist/bridge-cli)"
    echo -e "   ${C_BOLD}[11]${C_RESET} Полная очистка и удаление глобальных настроек\n"
    echo -e "   ${C_BOLD}[0]${C_RESET} Выход\n"
    echo -e "${C_CYAN}══════════════════════════════════════════════════════════════════════════════${C_RESET}"
    read -rp "Выберите действие [по умолчанию: 1]: " MAIN_CHOICE
    MAIN_CHOICE="${MAIN_CHOICE:-1}"

    case "$MAIN_CHOICE" in
        1) action_quick_start ;;
        2) action_change_target ;;
        3) action_setup_global ;;
        4) run_bridge tui ;;
        5) action_ping_and_status ;;
        6) action_remote_exec ;;
        7) action_pocket_menu ;;
        8) action_notes_menu ;;
        9) action_systemd_menu ;;
        10) action_build_binary ;;
        11) action_uninstall ;;
        0) echo -e "\n${C_GREEN}До встречи!${C_RESET}\n"; exit 0 ;;
        *) echo -e "${C_RED}Неверный ввод!${C_RESET}"; sleep 1 ;;
    esac
done
