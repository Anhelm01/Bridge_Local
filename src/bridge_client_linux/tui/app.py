"""
bridge_client_linux.tui.app — Интерактивный цикл Mini HUD Bridge Local v0.3.0.

Единственный интерфейс: Micro/Mini HUD.
  - Чтение клавиш в raw-режиме (alternate screen buffer).
  - Omnibar: единая строка ввода для всех команд.
  - Безопасное восстановление терминала при выходе.
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

from bridge_client_linux.tui.screens import render_mini_hud
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

console = Console()


def read_terminal_key(stream: Any = sys.stdin, timeout_sec: float = 0.04) -> str:
    """
    Читает одну клавишу или escape-последовательность из stdin в raw-режиме.
    Возвращает строку символа/последовательности или '' при таймауте.
    """
    try:
        rdy, _, _ = select.select([stream], [], [], timeout_sec)
    except (io.UnsupportedOperation, ValueError, TypeError, OSError):
        ch_fallback = stream.read(1)
        return str(ch_fallback) if ch_fallback else ""

    if not rdy:
        return ""
    ch: str = str(stream.read(1))
    if ch == "\x1b":
        rdy2, _, _ = select.select([stream], [], [], 0.02)
        if rdy2:
            ch2: str = str(stream.read(1))
            if ch2 == "[":
                rdy3, _, _ = select.select([stream], [], [], 0.02)
                if rdy3:
                    ch3: str = str(stream.read(1))
                    if ch3.isdigit():
                        rdy4, _, _ = select.select([stream], [], [], 0.02)
                        if rdy4:
                            ch4: str = str(stream.read(1))
                            return "\x1b[" + ch3 + ch4
                    return "\x1b[" + ch3
            elif ch2 == "O":
                rdy3, _, _ = select.select([stream], [], [], 0.02)
                if rdy3:
                    ch3 = str(stream.read(1))
                    return "\x1b O" + ch3
            return "\x1b" + ch2
    return ch


def probe_target_socket(host: str, port: int, timeout_sec: float = 0.5) -> tuple[bool, float]:
    """
    Быстрая неблокирующая проверка доступности сокета целевого узла.
    Возвращает (is_online, latency_ms).
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


def dispatch_omnibar_action(
    cmd: str,
    state: dict[str, Any],
    client: Any = None,
) -> None:
    """Выполняет команду из строки ввода Omnibar Mini HUD."""
    from datetime import datetime

    time_str = datetime.now().strftime("%H:%M:%S")
    raw = cmd.strip()

    if not raw:
        # Пустой ввод — проверка пинга узла
        h = state.get("tgt_host", "127.0.0.1")
        p = int(state.get("tgt_port", 9732))
        is_online, latency = probe_target_socket(h, p, timeout_sec=0.4)
        state["is_online"] = is_online
        state["latency_ms"] = latency if is_online else None
        state["last_error"] = False
        if is_online:
            state["last_output"] = f"[ping] ✓ Узел {h}:{p} доступен ({latency:.1f} мс)"
            state["last_summary"] = f"[{time_str}] ping -> {latency:.0f}ms"
        else:
            state["last_output"] = f"[ping] ✗ Узел {h}:{p} недоступен"
            state["last_summary"] = f"[{time_str}] ping -> OFFLINE"
        return

    # 1. Выход
    if raw.lower() in ("q", "quit", "exit", ":q"):
        state["_quit"] = True
        return

    # 2. Очистка экрана
    if raw.lower() in ("clear", "cls"):
        state["last_output"] = ""
        state["last_summary"] = ""
        state["last_error"] = False
        return

    # 3. Удалённое выполнение команды: 'e <cmd>' или 'exec <cmd>'
    exec_cmd = None
    if raw.lower().startswith("e ") and not raw.lower().startswith("exit"):
        exec_cmd = raw[2:].strip()
    elif raw.lower().startswith("exec "):
        exec_cmd = raw[5:].strip()
    if exec_cmd is not None:
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        try:
            async def _run_exec() -> Any:
                async with client:
                    return await client.exec(command=exec_cmd, timeout_sec=30)

            res = asyncio.run(_run_exec())
            out = res.stdout or res.stderr or ""
            state["is_online"] = True
            state["last_error"] = res.exit_code != 0
            state["last_output"] = out[:600] if out else f"[exec] exit {res.exit_code}"
            state["last_summary"] = f"[{time_str}] {exec_cmd[:30]} -> exit {res.exit_code}"
        except Exception as exc:
            state["is_online"] = False
            state["last_error"] = True
            state["last_output"] = f"[exec] ✗ {exc}"
            state["last_summary"] = f"[{time_str}] exec -> Error"
        return

    # 4. drop -B / pocket -B — из буфера обмена
    if raw.lower() in ("drop -b", "pocket -b", "drop --clipboard", "pocket --clipboard", "send -b"):
        from bridge_client_linux.clipboard import get_clipboard_content
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        try:
            clip_data = get_clipboard_content()
            if clip_data.data_type == "files" and clip_data.files:
                file_path = clip_data.files[0]

                async def _run_push() -> Any:
                    async with client:
                        return await client.pocket_push_file(file_path)

                asyncio.run(_run_push())
                state["is_online"] = True
                state["last_error"] = False
                state["last_output"] = f"[drop -B] ✓ {file_path.name} отправлен в Карман"
                state["last_summary"] = f'[{time_str}] drop -B -> "{file_path.name}"'
            elif clip_data.data_type == "image" and clip_data.image_bytes:
                filename = clip_data.suggested_filename or datetime.now().strftime(
                    "screenshot_%Y-%m-%d_%H-%M-%S.png"
                )
                img_path = getattr(client, "pocket_dir", Path("./pocket")) / filename
                img_path.write_bytes(clip_data.image_bytes)

                async def _run_img() -> Any:
                    async with client:
                        return await client.pocket_push_file(img_path)

                asyncio.run(_run_img())
                state["is_online"] = True
                state["last_error"] = False
                state["last_output"] = f"[drop -B] ✓ Скриншот {filename} отправлен"
                state["last_summary"] = f"[{time_str}] drop -B -> screenshot"
            elif clip_data.data_type == "text" and clip_data.text:

                async def _run_note() -> Any:
                    async with client:
                        return await client.note_send(text=clip_data.text)

                res = asyncio.run(_run_note())
                state["is_online"] = True
                state["last_error"] = False
                state["last_output"] = "[drop -B] ✓ Текст отправлен как заметка"
                state["last_summary"] = f"[{time_str}] drop -B -> note"
            else:
                state["last_error"] = True
                state["last_output"] = "[drop -B] Буфер пуст или формат не поддерживается"
                state["last_summary"] = f"[{time_str}] drop -B -> Empty"
        except Exception as exc:
            state["is_online"] = False
            state["last_error"] = True
            state["last_output"] = f"[drop -B] ✗ {exc}"
            state["last_summary"] = f"[{time_str}] drop -B -> Error"
        return

    # 5. pocket send / send / drop <файл>
    send_match = None
    for pfx in ("pocket send ", "pocket drop ", "pocket push ", "send ", "drop "):
        if raw.lower().startswith(pfx):
            send_match = raw[len(pfx):].strip()
            break
    if send_match is not None:
        clean_path = send_match.strip("'\"")
        if clean_path.lower() in ("-b", "--clipboard"):
            dispatch_omnibar_action("drop -B", state, client)
            return
        file_path = Path(clean_path).expanduser().resolve()
        if not file_path.is_file():
            state["last_error"] = True
            state["last_output"] = f"[send] ✗ Файл не найден: {clean_path}"
            state["last_summary"] = f"[{time_str}] send -> Not found"
            return
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        try:
            async def _run_push2() -> Any:
                async with client:
                    return await client.pocket_push_file(file_path)

            file_size = file_path.stat().st_size
            asyncio.run(_run_push2())
            state["is_online"] = True
            state["last_error"] = False
            state["last_output"] = f"[send] ✓ {file_path.name} → узел ({file_size} байт)"
            state["last_summary"] = f'[{time_str}] send "{file_path.name}" -> OK'
        except Exception as exc:
            state["is_online"] = False
            state["last_error"] = True
            state["last_output"] = f"[send] ✗ {exc}"
            state["last_summary"] = f"[{time_str}] send -> Error"
        return

    # 6. pocket ls
    if raw.lower() in ("pocket ls", "pocket list", "ls -p", "ls --pocket"):
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        try:
            from bridge_core.config import BridgeConfig
            cfg = BridgeConfig.load()
            p_dir = Path(cfg.pocket.path or "./pocket").expanduser().resolve()
            files = [f for f in p_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
            if not files:
                state["last_output"] = "[pocket ls] Карман пуст"
            else:
                top = "\n".join(f"  • {f.name} ({f.stat().st_size} B)" for f in files[:8])
                extra = f"\n  ... и ещё {len(files) - 8}" if len(files) > 8 else ""
                state["last_output"] = f"[pocket ls] {len(files)} файлов:\n{top}{extra}"
            state["last_error"] = False
        except Exception as exc:
            state["last_error"] = True
            state["last_output"] = f"[pocket ls] ✗ {exc}"
        return

    # 7. pocket clear
    if raw.lower().startswith("pocket clear"):
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        flags = raw.lower()
        local_only = "--local" in flags or " -l" in flags
        remote_only = "--remote" in flags or " -r" in flags
        force = "--force" in flags or " -f" in flags
        if not force:
            state["last_error"] = False
            state["last_output"] = "[pocket clear] Добавьте -f для подтверждения удаления"
            return
        try:
            del_local = 0
            del_remote = 0
            if not remote_only:
                from bridge_core.config import BridgeConfig
                cfg = BridgeConfig.load()
                p_dir = Path(cfg.pocket.path or "./pocket").expanduser().resolve()
                for f in p_dir.rglob("*"):
                    if f.is_file() and not f.name.startswith(".") and f.parent.name != "logs":
                        f.unlink()
                        del_local += 1
            if not local_only:
                async def _clear_remote() -> Any:
                    async with client:
                        return await client.pocket_clear()
                res = asyncio.run(_clear_remote())
                del_remote = getattr(res, "deleted_remote", 0)
            state["is_online"] = True
            state["last_error"] = False
            state["last_output"] = f"[pocket clear] ✓ Удалено: локально {del_local}, удалённо {del_remote}"
            state["last_summary"] = f"[{time_str}] pocket clear -> {del_local}+{del_remote}"
        except Exception as exc:
            state["last_error"] = True
            state["last_output"] = f"[pocket clear] ✗ {exc}"
        return

    # 8. note <текст>
    if raw.lower().startswith("note "):
        note_text = raw[5:].strip()
        if client is None:
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()
        try:
            async def _run_note2() -> Any:
                async with client:
                    return await client.note_send(text=note_text)

            res = asyncio.run(_run_note2())
            state["is_online"] = True
            state["last_error"] = False
            state["last_output"] = f"[note] ✓ Заметка отправлена: {note_text}"
            state["last_summary"] = f"[{time_str}] note -> sent ({len(note_text)} chars)"
        except Exception as exc:
            state["is_online"] = False
            state["last_error"] = True
            state["last_output"] = f"[note] ✗ {exc}"
            state["last_summary"] = f"[{time_str}] note -> Error"
        return

    # 9. token
    if raw.lower().startswith("token") or raw.lower().startswith("psk "):
        import hashlib
        import secrets

        from bridge_client_linux.clipboard import copy_text_to_clipboard
        from bridge_core.config import BridgeConfig

        cfg = BridgeConfig.load()
        cur_tok = cfg.connection.psk_token or ""
        rest = raw[5:].strip() if raw.lower().startswith("token") else raw[4:].strip()

        if rest in ("-c", "--clipboard"):
            copy_text_to_clipboard(cur_tok)
            state["last_output"] = "[token -c] ✓ Ключ скопирован в буфер обмена"
            state["last_error"] = False
            return
        if rest in ("-g", "-g -c", "-c -g"):
            new_tok = secrets.token_hex(16)
            cfg.update_connection(psk_token=new_tok)
            if client is not None and hasattr(client, "update_target"):
                client.update_target(psk_token=new_tok)
            if "-c" in rest:
                copy_text_to_clipboard(new_tok)
            state["last_output"] = f"[token -g] ✓ Новый токен: {new_tok}"
            state["last_error"] = False
            return
        if rest:
            cfg.update_connection(psk_token=rest)
            if client is not None and hasattr(client, "update_target"):
                client.update_target(psk_token=rest)
            masked = f"{rest[:4]}...{rest[-4:]}" if len(rest) >= 8 else "***"
            state["last_output"] = f"[token] ✓ Ключ обновлён: {masked}"
            state["last_error"] = False
            return
        masked = (
            f"{cur_tok[:4]}...{cur_tok[-4:]}"
            if len(cur_tok) >= 8
            else ("(не задан)" if not cur_tok else "***")
        )
        fp = hashlib.sha256(cur_tok.encode()).hexdigest()[:12] if cur_tok else "none"
        state["last_output"] = f"[token] PSK: {masked} | SHA-256: {fp}"
        state["last_error"] = False
        return

    # 10. connect <host:port>
    if raw.lower().startswith("connect "):
        tgt_arg = raw[8:].strip().replace("http://", "").replace("https://", "")
        cur_host = state.get("tgt_host", "127.0.0.1")
        cur_port = int(state.get("tgt_port", 9732))
        new_host, new_port = cur_host, cur_port
        if ":" in tgt_arg:
            parts = tgt_arg.split(":", 1)
            new_host = parts[0].strip() or cur_host
            with contextlib.suppress(ValueError):
                new_port = int(parts[1].strip())
        elif tgt_arg.isdigit():
            new_port = int(tgt_arg)
        else:
            new_host = tgt_arg or cur_host
        if new_host.lower() == "localhost":
            new_host = "127.0.0.1"
        is_online, latency = probe_target_socket(new_host, new_port, timeout_sec=0.5)
        state["tgt_host"] = new_host
        state["tgt_port"] = new_port
        state["tgt_address"] = f"{new_host}:{new_port}"
        state["is_online"] = is_online
        state["latency_ms"] = latency if is_online else None
        try:
            from bridge_core.config import BridgeConfig
            cfg = BridgeConfig.load()
            cfg.update_connection(host=new_host, port=new_port)
            if client is not None and hasattr(client, "update_target"):
                client.update_target(host=new_host, port=new_port)
        except Exception:
            pass
        if is_online:
            state["last_output"] = f"[connect] ✓ {new_host}:{new_port} доступен ({latency:.1f} мс)"
        else:
            state["last_output"] = f"[connect] Адрес {new_host}:{new_port} сохранён (OFFLINE)"
        state["last_error"] = not is_online
        return

    # 11. scan
    if raw.lower().startswith("scan"):
        auto = "-a" in raw.lower() or "--apply" in raw.lower()
        try:
            from bridge_core.discovery import discover_nodes

            psk = cfg.connection.psk_token or ""
            source_node = cfg.node.name or "workstation-linux"
            nodes = asyncio.run(
                discover_nodes(
                    psk_token=psk,
                    timeout_sec=1.5,
                    source_node=source_node,
                )
            )
            if not nodes:
                state["last_output"] = "[scan] Узлы в сети не найдены"
            else:
                lines = [f"[scan] Найдено {len(nodes)} узел(а):"]
                for n in nodes[:5]:
                    lines.append(f"  • {n.node_name or '?'} @ {n.ip}:{n.port}")
                if auto and nodes:
                    first = nodes[0]
                    state["tgt_host"] = first.ip
                    state["tgt_port"] = first.port
                    state["tgt_address"] = f"{first.ip}:{first.port}"
                    lines.append(f"  → Автоподключение к {first.ip}:{first.port}")
                state["last_output"] = "\n".join(lines)
            state["last_error"] = False
        except Exception as exc:
            state["last_error"] = True
            state["last_output"] = f"[scan] ✗ {exc}"
        return

    # 12. Неизвестная команда
    state["last_error"] = True
    state["last_output"] = (
        f"[?] Неизвестно: {raw}\n"
        f"Команды: e <cmd>  |  send <файл>  |  drop -B  |  note <текст>\n"
        f"         pocket ls/clear  |  token [-g|-c]  |  connect <IP:PORT>  |  scan  |  clear  |  q"
    )
    state["last_summary"] = f"[{time_str}] unknown: {raw[:20]}"


def dispatch_tui_action(
    mode: str,
    text: str,
    state: dict[str, Any],
    client: Any | None = None,
) -> None:
    """Всегда направляет ввод в omnibar."""
    dispatch_omnibar_action(text.strip(), state, client)


def run_interactive_tui(
    theme: PaletteTheme = OFFICIAL_THEME,
    initial_mode: str = "MINI",
    data: dict[str, Any] | None = None,
    single_pass: bool = False,
    is_mini: bool = True,
    client: Any | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    """
    Запускает интерактивный Mini HUD.

    В неинтерактивном режиме (не-TTY или single_pass) отрисовывает
    один кадр и завершается.
    """
    active_state: dict[str, Any] = dict(state if state is not None else (data or {}))
    active_state.setdefault("input_buffer", "")
    active_state.setdefault("status_msg", "")
    active_state.setdefault("last_output", "")
    active_state.setdefault("last_summary", "")
    active_state.setdefault("last_error", False)

    if client is None:
        with contextlib.suppress(Exception):
            from bridge_client_linux.client import BridgeClient
            client = BridgeClient()

    # Загрузка конфигурации
    try:
        from bridge_core.config import BridgeConfig
        cfg = BridgeConfig.load()
        tgt_host = cfg.connection.host
        tgt_port = cfg.connection.port
    except Exception:
        tgt_host = "127.0.0.1"
        tgt_port = 9732

    active_state["tgt_host"] = tgt_host
    active_state["tgt_port"] = tgt_port

    # Первичный опрос узла
    if "is_online" not in active_state:
        is_online, latency = probe_target_socket(tgt_host, tgt_port, timeout_sec=0.5)
        active_state["is_online"] = is_online
        active_state["latency_ms"] = latency if is_online else None
        if not is_online:
            active_state["last_output"] = f"[OFFLINE] Агент не запущен на {tgt_host}:{tgt_port}"
        else:
            active_state["last_output"] = f"[ONLINE] {tgt_host}:{tgt_port} ({latency:.1f} мс)"

    if single_pass or not sys.stdin.isatty():
        render_mini_hud(theme, active_state)
        return

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    input_buffer = ""

    sys.stdout.write("\033[?25l")  # скрыть курсор
    sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        while True:
            sys.stdout.write("\033[H\033[2J")  # очистка экрана
            sys.stdout.flush()
            active_state["input_buffer"] = input_buffer
            render_mini_hud(theme, active_state)

            ch = read_terminal_key(sys.stdin)

            # Выход
            if ch in ("\x03", "\x11"):  # Ctrl+C, Ctrl+Q
                break
            if active_state.get("_quit"):
                break

            # Backspace
            if ch in ("\x7f", "\x08"):
                input_buffer = input_buffer[:-1]
                continue

            # Escape — очистить буфер
            if ch == "\x1b":
                input_buffer = ""
                active_state["status_msg"] = ""
                continue

            # Enter — отправить команду
            if ch in ("\r", "\n"):
                stripped = input_buffer.strip()
                dispatch_omnibar_action(stripped, active_state, client)
                if active_state.get("_quit"):
                    break
                input_buffer = ""
                continue

            # Печатные символы → в буфер
            if len(ch) == 1 and ord(ch) >= 32:
                input_buffer += ch

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h")  # показать курсор
        sys.stdout.flush()
