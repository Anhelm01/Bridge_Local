"""
bridge_client_linux.tui.app — Интерактивный цикл TUI приложения Bridge Local.

Реализует:
  - Безопасную инициализацию alternate screen buffer (исключает повреждение терминала).
  - Обработку функциональных клавиш F1..F6, цифр 1..6, Tab, Q, Esc, W, A, R.
  - Честный неблокирующий опрос доступности Windows-агента (OFFLINE / ONLINE).
  - Однопроходный режим для неинтерактивных сред / CI / тестов.
  - Чистое восстановление настроек терминала при завершении.
"""

from __future__ import annotations

import asyncio
import contextlib
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


def probe_target_socket(host: str, port: int, timeout_sec: float = 0.25) -> tuple[bool, float]:
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
    """
    k = key.lower()
    # Выход из приложения
    if k in ("q", "\x03", "quit", "exit"):
        return current_mode, False

    # Режимы 1..7
    if k in ("1", "f1", "\x1bop", "dash"):
        return "DASH", True
    if k in ("2", "f2", "\x1boq", "pocket"):
        return "POCKET", True
    if k in ("3", "f3", "\x1bor", "notes"):
        return "NOTES", True
    if k in ("4", "f4", "\x1bos", "exec"):
        return "EXEC", True
    if k in ("5", "f5", "\x1b[15~", "config"):
        return "CONFIG", True
    if k in ("6", "f6", "\x1b[17~", "dev", "logs"):
        return "DEV", True
    if k in ("7", "f7", "\x1b[18~", "connect", "setup", "c"):
        return "CONNECT", True

    # Экран приветствия / Neofetch
    if k in ("w", "welcome", "splash"):
        return "WELCOME", True

    # Демонстрация анимаций
    if k in ("a", "anim"):
        return "ANIM", True

    # Обновление связи
    if k in ("r", "refresh"):
        return current_mode, True

    # Tab — циклическое переключение
    if k in ("\t",):
        order = ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT"]
        if current_mode in order:
            nxt = order[(order.index(current_mode) + 1) % len(order)]
            return nxt, True
        return "DASH", True

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
                    return await client.exec(command=cmd, timeout_sec=15)

            res = asyncio.run(_run_exec())
            out = res.stdout if res.stdout else res.stderr
            state["exec_history"].append((cmd, out or "", res.exit_code))
            state["status_msg"] = f"[bold green][OK] Команда выполнена (код {res.exit_code})[/]"
            state["is_online"] = True
        except Exception as e:
            state["is_online"] = False
            state["exec_history"].append((cmd, f"[СБОЙ СЕТИ / ОШИБКА] {e}", 2))
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

        if cmd.startswith("token "):
            new_tok = cmd[6:].strip()
            try:
                cfg = BridgeConfig.load()
                cfg.update_connection(psk_token=new_tok)
                cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
                state["status_msg"] = f"[bold green][OK] Ключ безопасности сохранен в {cfg_name}[/]"
            except Exception as e:
                state["status_msg"] = f"[bold red][ОШИБКА СОХРАНЕНИЯ ТОКЕНА][/] {e}"
        elif cmd in ("test", "ping", "r", "refresh"):
            tgt_host = state.get("tgt_host", "127.0.0.1")
            tgt_port = state.get("tgt_port", 9732)
            is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.35)
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None
            if is_online:
                state["status_msg"] = (
                    f"[bold green][ОНЛАЙН] Доступен {tgt_host}:{tgt_port} ({latency:.2f} мс)[/]"
                )
            else:
                state["status_msg"] = (
                    f"[bold red][ОФФЛАЙН] Сокет {tgt_host}:{tgt_port} не отвечает[/]"
                )
        elif cmd in ("default", "localhost"):
            tgt_host = "127.0.0.1"
            tgt_port = 9732
            is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.35)
            state["tgt_host"] = tgt_host
            state["tgt_port"] = tgt_port
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None
            try:
                cfg = BridgeConfig.load()
                cfg.update_connection(host=tgt_host, port=tgt_port)
                cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
                state["status_msg"] = (
                    f"[bold green][OK] Сброшено на 127.0.0.1:9732 и записано в {cfg_name}[/]"
                )
            except Exception as e:
                state["status_msg"] = f"[bold red][ОШИБКА СОХРАНЕНИЯ ТОМЛ][/] {e}"
        else:
            raw_target = cmd.replace("http://", "").replace("https://", "").strip()
            cur_port = int(state.get("tgt_port", 9732))
            cur_host = str(state.get("tgt_host", "127.0.0.1"))

            new_host = cur_host
            new_port = cur_port

            if raw_target.startswith(":"):
                with contextlib.suppress(ValueError):
                    new_port = int(raw_target[1:].strip())
            elif ":" in raw_target:
                parts = raw_target.split(":", 1)
                new_host = parts[0].strip()
                with contextlib.suppress(ValueError):
                    new_port = int(parts[1].strip())
            else:
                new_host = raw_target

            is_online, latency = probe_target_socket(new_host, new_port, timeout_sec=0.35)
            state["tgt_host"] = new_host
            state["tgt_port"] = new_port
            state["is_online"] = is_online
            state["latency_ms"] = latency if is_online else None

            try:
                cfg = BridgeConfig.load()
                cfg.update_connection(host=new_host, port=new_port)
                cfg_name = cfg._config_path.name if cfg._config_path else "bridge.toml"
                if is_online:
                    state["status_msg"] = (
                        f"[bold green][УСПЕШНО] Подключено к {new_host}:{new_port}! "
                        f"ОНЛАЙН ({latency:.2f} мс). {cfg_name} обновлен.[/]"
                    )
                else:
                    state["status_msg"] = (
                        f"[bold amber][СОХРАНЕНО] Адрес {new_host}:{new_port} в {cfg_name}. "
                        f"Узел ОФФЛАЙН (проверьте Windows-агент).[/]"
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
    state.setdefault("input_buffer", "")
    state.setdefault("status_msg", "")

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
        is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.25)
        state["is_online"] = is_online
        state["latency_ms"] = latency if is_online else None
        if not is_online and not state.get("status_msg"):
            state["status_msg"] = (
                f"[bold red][ОФФЛАЙН] Windows-агент не запущен на {tgt_host}:{tgt_port}. "
                f"Нажмите [R] для повторной проверки связи.[/]"
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
                f"[bold {theme.blue}][F1..F7/Tab][/] Вкладки  "
                f"[bold {theme.amber}][Enter][/] Ввод  "
                f"[bold {theme.green}][R][/] Проверить связь  "
                f"[bold {theme.primary}][W][/] Сплэш  "
                f"[bold {theme.red}][Ctrl+C/Q][/] Выход"
            )

            # Чтение клавиши с поддержкой escape-последовательностей
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch += sys.stdin.read(1)
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        ch += sys.stdin.read(3)

            # 1. Завершение работы
            if ch in ("\x03", "\x11"):  # Ctrl+C, Ctrl+Q
                break

            # 2. Функциональные клавиши переключения режимов
            k_lower = ch.lower()
            if k_lower in ("\x1bop", "\x1b[11~", "f1"):
                current_mode = "DASH"
                input_buffer = ""
                continue
            if k_lower in ("\x1boq", "\x1b[12~", "f2"):
                current_mode = "POCKET"
                input_buffer = ""
                continue
            if k_lower in ("\x1bor", "\x1b[13~", "f3"):
                current_mode = "NOTES"
                input_buffer = ""
                continue
            if k_lower in ("\x1bos", "\x1b[14~", "f4"):
                current_mode = "EXEC"
                input_buffer = ""
                continue
            if k_lower in ("\x1b[15~", "f5"):
                current_mode = "CONFIG"
                input_buffer = ""
                continue
            if k_lower in ("\x1b[17~", "f6"):
                current_mode = "DEV"
                input_buffer = ""
                continue
            if k_lower in ("\x1b[18~", "f7", "7"):
                current_mode = "CONNECT"
                input_buffer = ""
                continue

            # 3. Tab / Shift+Tab переключение вкладок
            order = ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT"]
            if ch == "\t":
                if current_mode in order:
                    idx = order.index(current_mode)
                    current_mode = order[(idx + 1) % len(order)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue
            if ch == "\x1b[z":  # Shift+Tab
                if current_mode in order:
                    idx = order.index(current_mode)
                    current_mode = order[(idx - 1) % len(order)]
                else:
                    current_mode = "DASH"
                input_buffer = ""
                continue

            # 4. Escape: очистить буфер ввода или вернуться на DASH
            if ch == "\x1b":
                if input_buffer:
                    input_buffer = ""
                    state["status_msg"] = ""
                else:
                    current_mode = "DASH"
                continue

            # 5. Backspace
            if ch in ("\x7f", "\x08"):
                input_buffer = input_buffer[:-1]
                continue

            # 6. Enter: отправка команды или текста
            if ch in ("\r", "\n"):
                stripped = input_buffer.strip()
                if stripped in (":q", ":quit", "quit", "exit"):
                    break
                if stripped in (":1", ":dash"):
                    current_mode = "DASH"
                elif stripped in (":2", ":pocket"):
                    current_mode = "POCKET"
                elif stripped in (":3", ":notes"):
                    current_mode = "NOTES"
                elif stripped in (":4", ":exec"):
                    current_mode = "EXEC"
                elif stripped in (":5", ":config"):
                    current_mode = "CONFIG"
                elif stripped in (":6", ":dev"):
                    current_mode = "DEV"
                elif stripped in (":7", ":connect", ":setup"):
                    current_mode = "CONNECT"
                elif stripped in (":w", ":welcome"):
                    current_mode = "WELCOME"
                elif stripped in (":r", ":refresh", "refresh", "r"):
                    is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.35)
                    state["is_online"] = is_online
                    state["latency_ms"] = latency if is_online else None
                    if is_online:
                        state["status_msg"] = (
                            f"[bold green][ОНЛАЙН] Агент доступен (пинг {latency:.2f} мс)[/]"
                        )
                    else:
                        state["status_msg"] = (
                            f"[bold red][ОФФЛАЙН] Узел {tgt_host}:{tgt_port} не отвечает.[/]"
                        )
                elif stripped:
                    dispatch_tui_action(current_mode, stripped, state, client)
                input_buffer = ""
                continue

            # 7. Цифры 1..7 и быстрые клавиши на экранах без активного ввода
            if (
                current_mode in ("DASH", "WELCOME", "CONFIG", "DEV")
                and not input_buffer
                and ch in ("1", "2", "3", "4", "5", "6", "7", "w", "a", "q", "r", "R", "c", "C")
            ):
                if ch.lower() == "r":
                    is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.35)
                    state["is_online"] = is_online
                    state["latency_ms"] = latency if is_online else None
                    if is_online:
                        state["status_msg"] = (
                            f"[bold green][ОНЛАЙН] Агент доступен (пинг {latency:.2f} мс)[/]"
                        )
                    else:
                        state["status_msg"] = (
                            f"[bold red][ОФФЛАЙН] Узел {tgt_host}:{tgt_port} не отвечает.[/]"
                        )
                    continue
                new_mode, keep_going = handle_key_action(ch, current_mode)
                if not keep_going:
                    break
                current_mode = new_mode
                continue

            # 8. Печатные символы -> в буфер ввода
            if len(ch) == 1 and ord(ch) >= 32:
                input_buffer += ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        console.print(f"[bold {theme.green}][OK] Сеанс TUI завершён.[/]")
