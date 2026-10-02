"""
bridge_client_linux.tui.app — Интерактивный цикл TUI приложения Bridge Local.

Реализует:
  - Безопасную инициализацию alternate screen buffer (исключает повреждение терминала).
  - Навигацию по вкладкам через Tab и Shift+Tab:
    (SPLASH, DASH, POCKET, NOTES, EXEC, CONFIG, DEV, CONNECT).
  - Честный неблокирующий опрос доступности Windows-агента (OFFLINE / ONLINE).
  - Однопроходный режим для неинтерактивных сред / CI / тестов.
  - Чистое восстановление настроек терминала при завершении.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import select
import socket
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from bridge_client_linux.tui.screens import render_current_mode
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

console = Console()

MODES_ORDER = [
    "SPLASH",
    "DASH",
    "POCKET",
    "NOTES",
    "EXEC",
    "CONFIG",
    "DEV",
    "CONNECT",
]

F_KEY_MAP: dict[str, str] = {
    # F1: SPLASH
    "\x1bOP": "SPLASH",
    "\x1b[[A": "SPLASH",
    "\x1b[11~": "SPLASH",
    # F2: DASH
    "\x1bOQ": "DASH",
    "\x1b[[B": "DASH",
    "\x1b[12~": "DASH",
    # F3: POCKET
    "\x1bOR": "POCKET",
    "\x1b[[C": "POCKET",
    "\x1b[13~": "POCKET",
    # F4: NOTES
    "\x1bOS": "NOTES",
    "\x1b[[D": "NOTES",
    "\x1b[14~": "NOTES",
    # F5: EXEC
    "\x1b[15~": "EXEC",
    # F6: CONFIG
    "\x1b[17~": "CONFIG",
    # F7: DEV
    "\x1b[18~": "DEV",
    # F8: CONNECT
    "\x1b[19~": "CONNECT",
}

NUM_KEY_MAP: dict[str, str] = {
    "1": "SPLASH",
    "2": "DASH",
    "3": "POCKET",
    "4": "NOTES",
    "5": "EXEC",
    "6": "CONFIG",
    "7": "DEV",
    "8": "CONNECT",
}

ALT_NUM_KEY_MAP: dict[str, str] = {
    "\x1b1": "SPLASH",
    "\x1b2": "DASH",
    "\x1b3": "POCKET",
    "\x1b4": "NOTES",
    "\x1b5": "EXEC",
    "\x1b6": "CONFIG",
    "\x1b7": "DEV",
    "\x1b8": "CONNECT",
}

PAGE_SIZES: dict[str, int] = {
    "POCKET": 10,
    "NOTES": 6,
    "EXEC": 4,
    "DEV": 8,
}


def read_terminal_key(stream: Any = sys.stdin, timeout_sec: float = 0.04) -> str:
    """
    Надежно считывает один символ или полную escape-последовательность из потока ввода.
    Исключает обрезание последовательностей и зависания.
    """
    ch = str(stream.read(1) or "")
    if not ch or ch != "\x1b":
        return ch

    # Проверка наличия продолжения escape-последовательности
    def _data_ready() -> bool:
        if hasattr(stream, "fileno"):
            try:
                r, _, _ = select.select([stream], [], [], timeout_sec)
                return bool(r)
            except (io.UnsupportedOperation, OSError, ValueError):
                pass
        if hasattr(stream, "tell") and hasattr(stream, "getvalue"):
            pos = int(stream.tell())
            val_len = len(str(stream.getvalue()))
            return bool(pos < val_len)
        return False

    if not _data_ready():
        return "\x1b"

    seq = "\x1b"
    while _data_ready():
        next_ch = str(stream.read(1) or "")
        if not next_ch:
            break
        seq += next_ch

        # Alt+1..Alt+8 (например, \x1b1 .. \x1b8)
        if len(seq) == 2 and seq[1] in "12345678":
            break
        # SS3 последовательности (например, \x1bOP для F1)
        if seq.startswith("\x1bO") and len(seq) >= 3:
            break

        # Linux console функциональные клавиши \x1b[[A ... \x1b[[D
        if seq.startswith("\x1b[[") and len(seq) >= 4:
            break
        # CSI последовательности, оканчивающиеся на '~' (\x1b[15~, \x1b[5~, etc.)
        if seq.startswith("\x1b[") and seq.endswith("~"):
            break
        # CSI последовательности со стандартным буквенным окончанием (\x1b[A, \x1b[Z, etc.)
        if (
            len(seq) >= 3
            and seq.startswith("\x1b[")
            and not seq.startswith("\x1b[[")
            and seq[-1].isalpha()
        ):
            break
        if len(seq) >= 16:
            break

    return seq


def handle_scroll_action(
    key: str,
    mode: str,
    state: dict[str, Any],
    page_size: int | None = None,
    total_items: int | None = None,
) -> bool:
    """
    Обрабатывает клавиши навигации по скроллу (Arrow Up/Down, Page Up/Down, Home, End).
    Обновляет state["scroll_offsets"][mode].
    Возвращает True, если была обработана клавиша скролла, иначе False.
    """
    k = key.lower()
    is_up = k in ("\x1b[a", "up", "arrow_up")
    is_down = k in ("\x1b[b", "down", "arrow_down")
    is_pgup = k in ("\x1b[5~", "page_up", "pageup", "pgup")
    is_pgdn = k in ("\x1b[6~", "page_down", "pagedown", "pgdn")
    is_home = k in ("\x1b[h", "\x1b[1~", "home")
    is_end = k in ("\x1b[f", "\x1b[4~", "end")

    if not (is_up or is_down or is_pgup or is_pgdn or is_home or is_end):
        return False

    offsets = state.setdefault("scroll_offsets", {})
    cur_offset = offsets.get(mode, 0)
    actual_page_size = page_size or PAGE_SIZES.get(mode, 10)

    if total_items is None:
        if mode == "POCKET":
            total_items = len(state.get("pocket_files", []))
        elif mode == "NOTES":
            total_items = len(state.get("notes_list", []))
        elif mode == "EXEC":
            total_items = len(state.get("exec_history", []))
        elif mode == "DEV":
            total_items = len(state.get("dev_logs", []))
        else:
            total_items = 0

    max_offset = max(0, total_items - actual_page_size) if total_items is not None else 9999

    if is_home:
        new_offset = 0
    elif is_end:
        new_offset = max_offset
    elif is_up:
        new_offset = max(0, cur_offset - 1)
    elif is_down:
        new_offset = min(max_offset, cur_offset + 1)
    elif is_pgup:
        new_offset = max(0, cur_offset - actual_page_size)
    elif is_pgdn:
        new_offset = min(max_offset, cur_offset + actual_page_size)
    else:
        new_offset = cur_offset

    offsets[mode] = new_offset
    return True


def probe_target_socket(host: str, port: int, timeout_sec: float = 0.5) -> tuple[bool, float]:
    """
    Быстрая неблокирующая проверка доступности сокета целевого узла.

    Возвращает (is_online, latency_ms). При недоступности возвращает (False, 0.0).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    t0 = time.perf_counter()
    try:
        err = s.connect_ex((host, port))
        if err == 0:
            latency = (time.perf_counter() - t0) * 1000.0
            return True, round(latency, 2)
        _, writable, _ = select.select([], [s], [], timeout_sec)
        if writable:
            sock_err = s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if sock_err == 0:
                latency = (time.perf_counter() - t0) * 1000.0
                return True, round(latency, 2)
        return False, 0.0
    except Exception:
        return False, 0.0
    finally:
        s.close()


def handle_key_action(key: str, current_mode: str) -> tuple[str, bool]:
    """
    Обрабатывает нажатую клавишу и возвращает кортеж:
      (новый_режим, продолжать_ли_цикл)

    Внимание: Буквенные клавиши ('w', 'q', 'r', 'c', 'a' и т.д.) НЕ переключают режимы
    и НЕ вызывают выход из программы!
    """
    k = key.lower()

    # 1. Выход: только Ctrl+C (\x03), Ctrl+Q (\x11) и строковые команды
    if key in ("\x03", "\x11") or k in ("quit", "exit", ":q", ":quit"):
        return current_mode, False

    # 2. Прямая адресация по цифрам 1..8
    if key in NUM_KEY_MAP:
        return NUM_KEY_MAP[key], True

    # 3. Alt+1..Alt+8
    if key in ALT_NUM_KEY_MAP:
        return ALT_NUM_KEY_MAP[key], True

    # 4. Функциональные клавиши F1..F8 (fallback)
    if key in F_KEY_MAP:
        return F_KEY_MAP[key], True

    f_map_str = {
        "f1": "SPLASH",
        "f2": "DASH",
        "f3": "POCKET",
        "f4": "NOTES",
        "f5": "EXEC",
        "f6": "CONFIG",
        "f7": "DEV",
        "f8": "CONNECT",
    }
    if k in f_map_str:
        return f_map_str[k], True

    # 5. Стрелки Влево (←) и Вправо (→) / скобки [ / ]
    order = MODES_ORDER
    norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
    cur_idx = order.index(norm_mode) if norm_mode in order else 1

    if key in ("\x1b[D", "\x1b[1;5D", "\x1b[1;3D", "\x1bOD", "left", "left_arrow", "["):
        prev = order[(cur_idx - 1) % len(order)]
        return prev, True

    if key in ("\x1b[C", "\x1b[1;5C", "\x1b[1;3C", "\x1bOC", "right", "right_arrow", "]"):
        nxt = order[(cur_idx + 1) % len(order)]
        return nxt, True

    # 6. Полные имена режимов и двоеточия
    if k in ("welcome", "splash", ":1", ":w", ":welcome", ":splash"):
        return "SPLASH", True
    if k in ("dash", ":2", ":dash"):
        return "DASH", True
    if k in ("pocket", ":3", ":pocket"):
        return "POCKET", True
    if k in ("notes", ":4", ":notes"):
        return "NOTES", True
    if k in ("exec", ":5", ":exec"):
        return "EXEC", True
    if k in ("config", ":6", ":config", ":cfg"):
        return "CONFIG", True
    if k in ("dev", "logs", ":7", ":dev"):
        return "DEV", True
    if k in ("connect", "setup", ":8", ":connect", ":setup", ":conn"):
        return "CONNECT", True

    # 7. Tab / Shift+Tab — циклическое переключение вкладок
    if k in ("\t", "tab"):
        nxt = order[(cur_idx + 1) % len(order)]
        return nxt, True

    if k in ("\x1b[z", "\x1b[Z", "shift+tab"):
        prev = order[(cur_idx - 1) % len(order)]
        return prev, True

    return current_mode, True


def dispatch_tui_action(
    mode: str,
    text: str,
    state: dict[str, Any],
    client: Any | None = None,
) -> None:
    """Выполняет действие ввода в зависимости от активного режима TUI."""
    cmd = text.strip()
    if not cmd:
        return

    if client is None:
        from bridge_client_linux.client import BridgeClient

        client = BridgeClient()

    if mode == "EXEC":
        try:

            async def _run_exec() -> Any:
                async with client:
                    cur_cwd = state.get("current_dir")
                    target_dir = cur_cwd if cur_cwd and cur_cwd != "C:\\BridgeService" else None
                    return await client.exec(command=cmd, timeout_sec=15, working_dir=target_dir)

            res = asyncio.run(_run_exec())
            if res.current_working_dir:
                state["current_dir"] = res.current_working_dir

            out = res.stdout if res.stdout else res.stderr
            cur_dir = state.get("current_dir") or "C:\\BridgeService"
            state["exec_history"].append((cmd, out or "", res.exit_code, cur_dir))
            state["status_msg"] = f"[bold green][OK] Команда выполнена (код {res.exit_code})[/]"
            state["is_online"] = True
        except Exception as e:
            state["is_online"] = False
            cur_dir = state.get("current_dir") or "C:\\BridgeService"
            state["exec_history"].append((cmd, f"[СБОЙ СЕТИ / ОШИБКА] {e}", 2, cur_dir))
            state["status_msg"] = f"[bold red][ОШИБКА СВЯЗИ][/] {e}"

    elif mode == "POCKET":
        clean_path = cmd.strip("'\"")
        file_path = Path(clean_path).expanduser().resolve()
        if not file_path.is_file():
            state["status_msg"] = f"[bold red][ERROR] Файл не найден:[/] {clean_path}"
            return

        try:

            async def _run_push() -> Any:
                async with client:
                    return await client.pocket_push_file(file_path)

            file_size = file_path.stat().st_size
            res = asyncio.run(_run_push())
            state["status_msg"] = (
                f"[bold green][OK] Файл {file_path.name} ({file_size} B) отправлен в Карман![/]"
            )
            state["is_online"] = True
            sha_preview = (res.sha256[:8] + "...") if res.sha256 else "[OK]"
            state["pocket_files"].insert(
                0,
                {
                    "name": file_path.name,
                    "size": f"{file_size} B",
                    "direction": "LNX --> WIN",
                    "sha": f"[OK] {sha_preview}",
                    "status": "SYNCED",
                },
            )
        except Exception as e:
            state["is_online"] = False
            state["status_msg"] = f"[bold red][ОШИБКА СЕТИ][/] {e}"

    elif mode == "NOTES":
        try:

            async def _run_note() -> Any:
                async with client:
                    return await client.note_send(text=cmd)

            res = asyncio.run(_run_note())
            from datetime import datetime

            now_time = datetime.now().strftime("%H:%M:%S")
            state["notes_list"].append(
                {
                    "time": now_time,
                    "author": "LINUX (agy_cli)",
                    "text": cmd,
                }
            )
            state["is_online"] = True
            state["status_msg"] = f"[bold green][OK] Заметка отправлена[/] (id: {res.note_id[:8]})"
        except Exception as e:
            state["is_online"] = False
            state["status_msg"] = f"[bold red][ОШИБКА СЕТИ][/] {e}"

    elif mode == "DASH":
        if cmd.startswith("send "):
            file_arg = cmd[5:].strip()
            dispatch_tui_action("POCKET", file_arg, state, client)
        elif cmd.startswith("exec "):
            cmd_arg = cmd[5:].strip()
            dispatch_tui_action("EXEC", cmd_arg, state, client)
        elif cmd in ("refresh", "r"):
            tgt_host = state.get("tgt_host", "192.168.100.2")
            tgt_port = state.get("tgt_port", 9732)
            is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.35)
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None
            if is_online:
                state["status_msg"] = (
                    f"[bold green][ОНЛАЙН] Узел доступен (пинг {latency:.2f} мс)[/]"
                )
            else:
                state["status_msg"] = (
                    f"[bold red][ОФФЛАЙН] Узел {tgt_host}:{tgt_port} не отвечает.[/]"
                )
        else:
            state["status_msg"] = f"[dim]Команда: {cmd}[/]"

    elif mode in ("CONNECT", "SETUP"):
        from bridge_core.config import BridgeConfig

        cur_port = int(state.get("tgt_port", 9732))
        cur_host = str(state.get("tgt_host", "127.0.0.1"))
        raw_cmd = cmd.strip()

        # 1. Проверка связи (ping / test / check / r / refresh / connect без аргументов)
        if raw_cmd.lower() in ("test", "ping", "check", "r", "refresh", "connect", ""):
            is_online, latency = probe_target_socket(cur_host, cur_port, timeout_sec=0.5)
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None
            if is_online:
                state["status_msg"] = (
                    f"[bold green][ОНЛАЙН] Узел {cur_host}:{cur_port} "
                    f"доступен (пинг {latency:.2f} мс)[/]"
                )
            else:
                state["status_msg"] = (
                    f"[bold red][ОФФЛАЙН] Сокет {cur_host}:{cur_port} не отвечает[/]"
                )
            return

        # 2. Обновление PSK токена безопасности
        if raw_cmd.lower().startswith(("token ", "psk ", "key ")):
            prefix_len = raw_cmd.find(" ") + 1
            new_tok = raw_cmd[prefix_len:].strip()
            try:
                cfg = BridgeConfig.load()
                cfg.update_connection(psk_token=new_tok)
                if client is not None and hasattr(client, "update_target"):
                    client.update_target(psk_token=new_tok)
                cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
                state["status_msg"] = f"[bold green][OK] Ключ безопасности сохранен в {cfg_name}[/]"
            except Exception as e:
                state["status_msg"] = f"[bold red][ОШИБКА СОХРАНЕНИЯ ТОКЕНА][/] {e}"
            return

        # 3. Сброс на значения по умолчанию (default / localhost / reset)
        if raw_cmd.lower() in ("default", "localhost", "reset", "local"):
            new_host = "127.0.0.1"
            new_port = 9732
            is_online, latency = probe_target_socket(new_host, new_port, timeout_sec=0.5)
            state["tgt_host"] = new_host
            state["tgt_port"] = new_port
            state["tgt_address"] = f"{new_host}:{new_port}"
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None
            try:
                cfg = BridgeConfig.load()
                cfg.update_connection(host=new_host, port=new_port)
                if client is not None and hasattr(client, "update_target"):
                    client.update_target(host=new_host, port=new_port)
                cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
                state["status_msg"] = (
                    f"[bold green][OK] Сброшено на 127.0.0.1:9732 и записано в {cfg_name}[/]"
                )
            except Exception as e:
                state["status_msg"] = f"[bold red][ОШИБКА СОХРАНЕНИЯ ТОМЛ][/] {e}"
            return

        # 4. Разбор IP и порта
        target_str = raw_cmd
        for prefix in ("connect ", "target ", "host ", "set ", "ip "):
            if target_str.lower().startswith(prefix):
                target_str = target_str[len(prefix) :].strip()
                break

        target_str = target_str.replace("http://", "").replace("https://", "").strip()
        new_host = cur_host
        new_port = cur_port

        if target_str.isdigit():
            # Только порт, например '9732'
            new_port = int(target_str)
        elif target_str.startswith(":"):
            # Порт с двоеточием, например ':9735'
            with contextlib.suppress(ValueError):
                new_port = int(target_str[1:].strip())
        elif ":" in target_str:
            # IP:порт, например '192.168.1.150:9732'
            parts = target_str.split(":", 1)
            new_host = parts[0].strip()
            with contextlib.suppress(ValueError):
                new_port = int(parts[1].strip())
        elif " " in target_str:
            # IP порт через пробел, например '192.168.1.150 9732'
            parts = target_str.split(None, 1)
            new_host = parts[0].strip()
            with contextlib.suppress(ValueError):
                new_port = int(parts[1].strip())
        else:
            # Только хост / IP, например '192.168.1.150'
            new_host = target_str

        if new_host.lower() == "localhost":
            new_host = "127.0.0.1"

        is_online, latency = probe_target_socket(new_host, new_port, timeout_sec=0.5)
        state["tgt_host"] = new_host
        state["tgt_port"] = new_port
        state["tgt_address"] = f"{new_host}:{new_port}"
        state["is_online"] = is_online
        state["latency_ms"] = latency if is_online else None

        try:
            cfg = BridgeConfig.load()
            cfg.update_connection(host=new_host, port=new_port)
            if client is not None and hasattr(client, "update_target"):
                client.update_target(host=new_host, port=new_port)
            cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
            if is_online:
                state["status_msg"] = (
                    f"[bold green][УСПЕШНО] Подключено к {new_host}:{new_port}! "
                    f"ОНЛАЙН ({latency:.2f} мс). {cfg_name} обновлен.[/]"
                )
            else:
                state["status_msg"] = (
                    f"[bold amber][СОХРАНЕНО] Адрес {new_host}:{new_port} записан в {cfg_name}. "
                    f"Узел ОФФЛАЙН (проверьте запуск агента на Windows).[/]"
                )
        except Exception as e:
            state["status_msg"] = f"[bold red][ОШИБКА СОХРАНЕНИЯ ТОМЛ][/] {e}"


def run_interactive_tui(
    theme: PaletteTheme = OFFICIAL_THEME,
    initial_mode: str = "WELCOME",
    data: dict[str, Any] | None = None,
    single_pass: bool = False,
    client: Any | None = None,
) -> None:
    """
    Запускает полноэкранный интерактивный TUI-интерфейс.

    Если stdin не является TTY или передан single_pass=True,
    отрисовывает заданный режим однократно и завершается.
    """
    state: dict[str, Any] = dict(data or {})
    state.setdefault("exec_history", [])
    state.setdefault("pocket_files", [])
    state.setdefault("notes_list", [])
    state.setdefault("scroll_offsets", {"POCKET": 0, "NOTES": 0, "DEV": 0, "EXEC": 0})
    state.setdefault("input_buffer", "")
    state.setdefault("status_msg", "")
    state.setdefault("current_dir", "C:\\BridgeService")

    if client is None:
        with contextlib.suppress(Exception):
            from bridge_client_linux.client import BridgeClient

            client = BridgeClient()

    try:
        from bridge_core.config import BridgeConfig

        cfg = BridgeConfig.load()
        tgt_host = cfg.connection.host
        tgt_port = cfg.connection.port
    except Exception:
        tgt_host = "192.168.100.2"
        tgt_port = 9732

    state["tgt_host"] = tgt_host
    state["tgt_port"] = tgt_port

    # Честный опрос удаленного узла
    if "is_online" not in state:
        is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.5)
        state["is_online"] = is_online
        state["latency_ms"] = latency if is_online else None
        if not is_online and not state.get("status_msg"):
            state["status_msg"] = (
                f"[bold red][ОФФЛАЙН] Windows-агент не запущен на {tgt_host}:{tgt_port}. "
                f"Нажмите [Enter] на вкладке CONNECT для повторной проверки связи.[/]"
            )
        elif is_online and not state.get("status_msg"):
            state["status_msg"] = (
                f"[bold green][ОНЛАЙН] Узел ({tgt_host}:{tgt_port}) доступен "
                f"(пинг {latency:.2f} мс)[/]"
            )

    if single_pass or not sys.stdin.isatty():
        render_current_mode(initial_mode, theme, state)
        return

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    current_mode = initial_mode.upper()
    input_buffer = ""

    # Переход в alternate screen buffer и скрытие курсора (исключает скролл и артефакты)
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        while True:
            # Очистка экрана и перемещение курсора в (1,1) без скролла
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()

            state["input_buffer"] = input_buffer
            render_current_mode(current_mode, theme, state)

            # Минималистичная подсказка управления внизу
            console.print(
                f"\n [dim]Навигация:[/] "
                f"[bold {theme.blue}][← / → / 1..8 / Tab][/] Вкладки  "
                f"[bold {theme.amber}][↑/↓ / PgUp/PgDn][/] Скролл  "
                f"[bold {theme.green}][Enter][/] Ввод  "
                f"[bold {theme.red}][Ctrl+C / Ctrl+Q][/] Выход"
            )

            # Чтение клавиши с надежной поддержкой escape-последовательностей
            ch = read_terminal_key(sys.stdin)

            # 1. Завершение работы
            if ch in ("\x03", "\x11"):  # Ctrl+C, Ctrl+Q
                break

            # 2. Переключение вкладок стрелками Влево (←) и Вправо (→)
            is_left = ch in ("\x1b[D", "\x1b[1;5D", "\x1b[1;3D", "\x1bOD")
            if is_left and (not input_buffer or ch in ("\x1b[1;5D", "\x1b[1;3D")):
                norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                if norm_mode in MODES_ORDER:
                    idx = MODES_ORDER.index(norm_mode)
                    current_mode = MODES_ORDER[(idx - 1) % len(MODES_ORDER)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue

            is_right = ch in ("\x1b[C", "\x1b[1;5C", "\x1b[1;3C", "\x1bOC")
            if is_right and (not input_buffer or ch in ("\x1b[1;5C", "\x1b[1;3C")):
                norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                if norm_mode in MODES_ORDER:
                    idx = MODES_ORDER.index(norm_mode)
                    current_mode = MODES_ORDER[(idx + 1) % len(MODES_ORDER)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue

            # 3. Tab / Shift+Tab переключение вкладок
            if ch == "\t":
                norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                if norm_mode in MODES_ORDER:
                    idx = MODES_ORDER.index(norm_mode)
                    current_mode = MODES_ORDER[(idx + 1) % len(MODES_ORDER)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue
            if ch in ("\x1b[z", "\x1b[Z"):  # Shift+Tab
                norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                if norm_mode in MODES_ORDER:
                    idx = MODES_ORDER.index(norm_mode)
                    current_mode = MODES_ORDER[(idx - 1) % len(MODES_ORDER)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue

            # 4. Цифровые клавиши 1..8, Alt+1..8 и скобки [ / ]
            if ch in ALT_NUM_KEY_MAP:
                current_mode = ALT_NUM_KEY_MAP[ch]
                input_buffer = ""
                continue

            if current_mode in ("SPLASH", "DASH", "CONFIG", "DEV", "WELCOME"):
                if ch in NUM_KEY_MAP:
                    current_mode = NUM_KEY_MAP[ch]
                    input_buffer = ""
                    continue
                if ch == "[":
                    norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                    idx = MODES_ORDER.index(norm_mode) if norm_mode in MODES_ORDER else 1
                    current_mode = MODES_ORDER[(idx - 1) % len(MODES_ORDER)]
                    input_buffer = ""
                    continue
                if ch == "]":
                    norm_mode = "SPLASH" if current_mode == "WELCOME" else current_mode
                    idx = MODES_ORDER.index(norm_mode) if norm_mode in MODES_ORDER else 1
                    current_mode = MODES_ORDER[(idx + 1) % len(MODES_ORDER)]
                    input_buffer = ""
                    continue

            is_prompt_mode = current_mode in ("POCKET", "NOTES", "EXEC")
            if is_prompt_mode and not input_buffer and ch in NUM_KEY_MAP:
                current_mode = NUM_KEY_MAP[ch]
                input_buffer = ""
                continue

            # 5. Переключение вкладок по F1..F8 (fallback)
            if ch in F_KEY_MAP:
                current_mode = F_KEY_MAP[ch]
                input_buffer = ""
                continue

            # 6. Навигация и скролл (Arrow Up/Down, Page Up/Down, Home, End)
            if handle_scroll_action(ch, current_mode, state):
                continue

            # 7. Escape: очистить буфер ввода или вернуться на DASH
            if ch == "\x1b":
                if input_buffer:
                    input_buffer = ""
                    state["status_msg"] = ""
                else:
                    current_mode = "DASH"
                continue

            # 8. Backspace
            if ch in ("\x7f", "\x08"):
                input_buffer = input_buffer[:-1]
                continue

            # 9. Enter: отправка команды или текста
            if ch in ("\r", "\n"):
                stripped = input_buffer.strip()
                if stripped in (":q", ":quit", "quit", "exit"):
                    break
                if stripped in (":1", ":w", ":welcome", ":splash"):
                    current_mode = "SPLASH"
                elif stripped in (":2", ":dash"):
                    current_mode = "DASH"
                elif stripped in (":3", ":pocket"):
                    current_mode = "POCKET"
                elif stripped in (":4", ":notes"):
                    current_mode = "NOTES"
                elif stripped in (":5", ":exec"):
                    current_mode = "EXEC"
                elif stripped in (":6", ":config", ":cfg"):
                    current_mode = "CONFIG"
                elif stripped in (":7", ":dev"):
                    current_mode = "DEV"
                elif stripped in (":8", ":connect", ":setup", ":conn"):
                    current_mode = "CONNECT"
                elif stripped in (":r", ":refresh", "refresh"):
                    h = state.get("tgt_host", tgt_host)
                    p = int(state.get("tgt_port", tgt_port))
                    is_online, latency = probe_target_socket(h, p, timeout_sec=0.5)
                    state["is_online"] = is_online
                    state["latency_ms"] = latency if is_online else None
                    if is_online:
                        state["status_msg"] = (
                            f"[bold green][ОНЛАЙН] Агент доступен на "
                            f"{h}:{p} (пинг {latency:.2f} мс)[/]"
                        )

                    else:
                        state["status_msg"] = f"[bold red][ОФФЛАЙН] Узел {h}:{p} не отвечает.[/]"
                elif not stripped and current_mode in ("CONNECT", "SETUP"):
                    dispatch_tui_action("CONNECT", "", state, client)
                elif stripped:
                    dispatch_tui_action(current_mode, stripped, state, client)
                input_buffer = ""
                continue

            # 8. Печатные символы -> в буфер ввода (буквы никогда не переключают экраны)
            if len(ch) == 1 and ord(ch) >= 32:
                input_buffer += ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        console.print(f"[bold {theme.green}][OK] Сеанс TUI завершён.[/]")
