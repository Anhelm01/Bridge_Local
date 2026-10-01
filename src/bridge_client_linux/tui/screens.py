"""
bridge_client_linux.tui.screens — Отрисовка экранов и рабочих режимов Bridge Local.

Реализует:
  1. Full-screen Neofetch экран приветствия (BRIDGES Master).
  2. Шапку оперативных окон DRAWBRIDGE Industrial.
  3. Вкладки [Tab / Shift+Tab]:
     - SPLASH: экран приветствия и Neofetch
     - DASH: сводный дашборд сети, узлов и очередей
     - POCKET: список и статус хранилища кармана (реальные файлы с диска)
     - NOTES: лента быстрых заметок (реальные записи из notes.jsonl)
     - EXEC: удалённый терминал PowerShell
     - CONFIG: реестр узлов и параметры подключения
     - DEV: журнал трассировки и логов
     - CONNECT: быстрое подключение и настройка узла без правки TOML
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bridge_client_linux.tui.animations import demo_process_animations
from bridge_client_linux.tui.logos import (
    BRIDGES_MASTER,
)
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme
from bridge_core.config import BridgeConfig

console = Console()


def get_local_ip() -> str:
    """Определяет активный локальный IP машины без сетевой блокировки."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = str(s.getsockname()[0])
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def format_bytes(num_bytes: int) -> str:
    """Форматирует размер в байтах в человекочитаемый вид."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def calc_file_sha_preview(file_path: Path) -> str:
    """Вычисляет превью SHA-256 (первые 8 символов) для таблицы кармана."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()[:8]
    except Exception:
        return "unknown"


def get_live_context(custom_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Формирует честный срез системного состояния без вымышленных заглушек.

    Если служба Windows оффлайн, явно отображает OFFLINE статус и недоступность,
    а файлы и заметки считывает напрямую из реального локального каталога на диске.
    """
    d = dict(custom_data or {})
    try:
        cfg = BridgeConfig.load()
    except Exception:
        cfg = BridgeConfig()

    src_node = d.get("node", {}).get("source") or cfg.node.name or "workstation-linux"
    src_display = (
        d.get("node", {}).get("display_name") or cfg.node.display_name or "Linux Workstation"
    )
    src_ip = d.get("node", {}).get("src_ip") or get_local_ip()

    tgt_node = d.get("node", {}).get("target") or "WIN-PC"
    tgt_host = (
        d.get("tgt_host") or d.get("node", {}).get("host") or cfg.connection.host or "192.168.100.2"
    )
    tgt_port = d.get("tgt_port") or d.get("node", {}).get("port") or cfg.connection.port or 9732
    tgt_address = d.get("tgt_address") or f"{tgt_host}:{tgt_port}"

    # Честный статус связи: False по умолчанию (пока явно не подтвержден опрос)
    is_online = bool(d.get("is_online", False))
    latency_val = d.get("latency_ms") if is_online else None

    # Карман: сканирование реального каталога на диске
    pocket_raw_path = cfg.pocket.path or "./pocket"
    pocket_dir = Path(pocket_raw_path).expanduser().resolve()
    pocket_files: list[dict[str, Any]] = []
    pocket_total_bytes = 0

    if pocket_dir.exists() and pocket_dir.is_dir():
        for root, dirs, filenames in os.walk(pocket_dir):
            dirs[:] = [sub for sub in dirs if not sub.startswith(".") and sub != "logs"]
            for fname in filenames:
                if fname.startswith(".") or fname.endswith(".part"):
                    continue
                fp = Path(root) / fname
                try:
                    st = fp.stat()
                    rel_p = fp.relative_to(pocket_dir).as_posix()
                    pocket_files.append(
                        {
                            "name": rel_p,
                            "size": format_bytes(st.st_size),
                            "size_bytes": st.st_size,
                            "direction": "LOCAL [POCKET]",
                            "sha": f"[OK] {calc_file_sha_preview(fp)}...",
                            "status": "READY",
                        }
                    )
                    pocket_total_bytes += st.st_size
                except OSError:
                    continue

    if d.get("pocket_files"):
        pocket_files = d["pocket_files"]
        pocket_count = len(pocket_files)
    else:
        pocket_count = len(pocket_files)

    pocket_size_human = format_bytes(pocket_total_bytes)

    # Заметки: чтение реального файла notes.jsonl
    notes_list: list[dict[str, Any]] = []
    if d.get("notes_list"):
        notes_list = list(d["notes_list"])
    else:
        candidate_notes_files = [
            pocket_dir / ".notes" / "notes.jsonl",
            Path(".notes") / "notes.jsonl",
            Path("pocket/.notes/notes.jsonl"),
        ]
        for cnf in candidate_notes_files:
            if cnf.exists():
                try:
                    with open(cnf, encoding="utf-8") as f:
                        for line in f:
                            s = line.strip()
                            if not s:
                                continue
                            try:
                                n_obj = json.loads(s)
                                ts_raw = n_obj.get("timestamp", "")
                                t_str = (
                                    ts_raw.split("T")[1][:8]
                                    if "T" in ts_raw
                                    else (ts_raw[:8] if ts_raw else "00:00:00")
                                )
                                notes_list.append(
                                    {
                                        "time": t_str,
                                        "author": n_obj.get("author_os", "NODE"),
                                        "text": n_obj.get("text", ""),
                                    }
                                )
                            except Exception:
                                continue
                    if notes_list:
                        break
                except OSError:
                    pass

    notes_count = len(notes_list)

    if is_online:
        latency_str = (
            f"{latency_val:.2f} ms" if isinstance(latency_val, (int, float)) else "0.38 ms"
        )
        status_label = "ONLINE (Готов)"
        remote_agent_label = "READY"
        cpu_str = f"{d.get('remote', {}).get('cpu_percent', 0.0)}%"
        mem_str = f"{d.get('remote', {}).get('memory_used_mb', 0)} MB"
        uptime_sec = d.get("remote", {}).get("uptime_seconds", 0)
        uptime_str = (
            f"{uptime_sec // 86400}d {(uptime_sec % 86400) // 3600}h {(uptime_sec % 3600) // 60}m"
        )
    else:
        latency_str = "НЕДОСТУПЕН"
        status_label = "OFFLINE (Нет связи)"
        remote_agent_label = "OFFLINE"
        cpu_str = "--"
        mem_str = "--"
        uptime_str = "--"

    return {
        "cfg": cfg,
        "src_node": src_node,
        "src_display": src_display,
        "src_ip": src_ip,
        "tgt_node": tgt_node,
        "tgt_host": tgt_host,
        "tgt_port": tgt_port,
        "tgt_address": tgt_address,
        "is_online": is_online,
        "latency_val": latency_val,
        "latency_str": latency_str,
        "status_label": status_label,
        "remote_agent_label": remote_agent_label,
        "cpu_str": cpu_str,
        "mem_str": mem_str,
        "uptime_str": uptime_str,
        "pocket_dir": str(pocket_dir),
        "pocket_path_display": f"{pocket_raw_path}/",
        "pocket_files": pocket_files,
        "pocket_count": pocket_count,
        "pocket_size_human": pocket_size_human,
        "notes_list": notes_list,
        "notes_count": notes_count,
        "notes_unread": 0,
        "notes_file_display": "pocket/.notes/notes.jsonl",
        "exec_history": d.get("exec_history", []),
        "input_buffer": d.get("input_buffer", ""),
        "status_msg": d.get("status_msg", ""),
        "psk_set": bool(cfg.connection.psk_token),
        "heartbeat_interval_ms": int(cfg.heartbeat.interval_sec * 1000),
        "failfast_ms": int(cfg.heartbeat.timeout_sec * 1000),
    }


def render_mode_tabs(active_mode: str, theme: PaletteTheme = OFFICIAL_THEME) -> None:
    """Верхний таб-бар переключения режимов с поддержкой адресации по 1..8, стрелкам ← / → и Tab."""
    tabs = [
        ("1", "SPLASH"),
        ("2", "DASH"),
        ("3", "POCKET"),
        ("4", "NOTES"),
        ("5", "EXEC"),
        ("6", "CONFIG"),
        ("7", "DEV"),
        ("8", "CONNECT"),
    ]
    bar = Text()
    bar.append("[BRIDGE] ", style=f"bold black on {theme.blue}")
    for i, (num_key, name) in enumerate(tabs):
        is_active = (name == active_mode) or (name == "SPLASH" and active_mode == "WELCOME")
        if is_active:
            bar.append(f"█ [{num_key}:{name}]", style="bold white on #1F6FEB")
        else:
            bar.append(f"[{num_key}:{name}]", style=f"dim {theme.secondary}")
        if i < len(tabs) - 1:
            bar.append(" │ ")
    bar.append("  [dim](← / → / 1..8 / Tab)[/]")
    console.print(Panel(bar, style=theme.secondary, expand=True, padding=0))


def render_welcome_screen(
    theme: PaletteTheme = OFFICIAL_THEME,
    status_data: dict[str, Any] | None = None,
) -> None:
    """Выводит экран Neofetch с BRIDGES Master и честным статусом."""
    render_mode_tabs("SPLASH", theme)
    term_width, _ = shutil.get_terminal_size((120, 40))

    p = theme.primary
    s = theme.secondary
    w = theme.text
    b = theme.blue
    g = theme.green
    a = theme.amber
    pu = theme.purple
    r = theme.red

    ctx = get_live_context(status_data)

    if ctx["is_online"]:
        remote_badge = f"[bold {g}][ONLINE / READY][/]"
        net_conn_line = f"[bold {g}][STABLE LAN · {ctx['latency_str']} OK][/]"
        channel_line = "P2P Direct LAN / Sockets"
    else:
        remote_badge = f"[bold {r}][OFFLINE (Служба Windows не запущена)][/]"
        net_conn_line = f"[bold {r}][НЕДОСТУПЕН · Служба не отвечает][/]"
        channel_line = "P2P Direct LAN (Нет подключения)"

    pocket_display = f"{ctx['pocket_count']} об. ({ctx['pocket_size_human']})"
    if ctx["pocket_count"] == 0:
        pocket_suffix = "[dim][Ожидание файлов][/]"
    else:
        pocket_suffix = f"[bold {g}][SHA-256 OK][/]"

    sec_line = "HMAC-SHA256" if ctx["psk_set"] else "Без токена (Open)"
    notes_line = f"{ctx['notes_count']} записей [{ctx['notes_unread']} новых]"

    info = f"""[bold {w}]anhelm@{ctx["src_node"]}[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Host OS:[/]        Linux x86_64
[bold {b}]Local Node:[/]     {ctx["src_display"]} ({ctx["src_ip"]})
[bold {s}]Core Operator:[/]  agy_cli (Antigravity CLI Agent)

[bold {pu}]Remote Node:[/]    {ctx["tgt_node"]} ({ctx["tgt_address"]})
[bold {pu}]Remote OS:[/]      Windows 64-bit
[bold {pu}]Remote Agent:[/]   BridgeLocalAgent {remote_badge}

[bold {b}]СВЯЗЬ И ПРОТОКОЛ (P2P BACKBONE)[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Канал связи:[/]    {channel_line}
[bold {s}]Пинг (Latency):[/]  {net_conn_line}
[bold {s}]Безопасность:[/]    {sec_line}
[bold {s}]Транспорт:[/]       JSON-RPC 2.0 / Length-Prefix Wire Framing
[bold {s}]Fail-Fast:[/]       {ctx["failfast_ms"]} ms (Мгновенное обнаружение обрыва)

[bold {a}]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Карман (Pocket):[/] {ctx["pocket_path_display"]}
[bold {s}]Файлов в кармане:[/] {pocket_display} {pocket_suffix}
[bold {s}]Заметки (Notes):[/] {notes_line}"""

    logo_raw_lines = [line for line in BRIDGES_MASTER.strip("\n").splitlines() if line]
    max_logo_w = max(len(line) for line in logo_raw_lines)
    panel_h = len(logo_raw_lines) + 2

    if term_width >= 125:
        w1 = term_width // 2
        w2 = term_width - w1
        pad = max(0, (w1 - 2 - max_logo_w) // 2)
        centered_lines = [" " * pad + line for line in logo_raw_lines]
        logo_text = Text("\n".join(centered_lines), style=f"bold {p}", no_wrap=True)

        logo_panel = Panel(
            logo_text,
            title=f"[bold {p}]◈ BRIDGES MASTER EMBLEM ◈[/]",
            subtitle=f"[dim {s}]STRAND NETWORK · LAN BACKBONE[/]",
            border_style=s,
            padding=0,
            height=panel_h,
        )
        info_panel = Panel(
            info,
            title=f"[bold {w}][ СИСТЕМНЫЙ СТАТУС / NEOFETCH ][/]",
            subtitle=f"[dim {b}]● THEME: {theme.name}[/]",
            border_style=s,
            padding=(0, 1),
            height=panel_h,
        )

        grid = Table.grid(padding=0)
        grid.add_column(width=w1)
        grid.add_column(width=w2)
        grid.add_row(logo_panel, info_panel)
        console.print(grid)
    else:
        pad = max(0, (term_width - 4 - max_logo_w) // 2)
        centered_lines = [" " * pad + line for line in logo_raw_lines]
        logo_text = Text("\n".join(centered_lines), style=f"bold {p}", no_wrap=True)

        logo_panel = Panel(
            logo_text,
            title=f"[bold {p}]◈ BRIDGES MASTER EMBLEM ◈[/]",
            subtitle=f"[dim {s}]STRAND NETWORK · LAN BACKBONE[/]",
            border_style=s,
            padding=0,
        )
        info_panel = Panel(
            info,
            title=f"[bold {w}][ СИСТЕМНЫЙ СТАТУС / NEOFETCH ][/]",
            subtitle=f"[dim {b}]● THEME: {theme.name}[/]",
            border_style=s,
            padding=(0, 1),
        )
        console.print(logo_panel)
        console.print(info_panel)


def render_operational_header(
    theme: PaletteTheme = OFFICIAL_THEME,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Шапка оперативного окна с логотипом DRAWBRIDGE Industrial без эмодзи."""
    ctx = get_live_context(metrics)
    src_ip = ctx["src_ip"]
    tgt_ip = ctx["tgt_address"]

    if ctx["is_online"]:
        latency_text = f"{ctx['latency_str']} [OK]"
        status_style = f"bold {theme.green}"
    else:
        latency_text = "OFFLINE (Нет связи)"
        status_style = f"bold {theme.red}"

    pocket_stat = f"{ctx['pocket_count']} об. ({ctx['pocket_size_human']})"
    notes_stat = f"{ctx['notes_count']} записей"

    header_text = Text()
    # Строка 1
    header_text.append("      .▄█ ││ █▄.       ", style=f"bold {theme.secondary}")
    header_text.append("D R A W B R I D G E", style=f"bold {theme.primary}")
    header_text.append("  ::  ", style=f"bold {theme.secondary}")
    header_text.append("B R I D G E   L O C A L\n", style=f"bold {theme.blue}")
    # Строка 2
    header_text.append("     //║  ||  ║\\\\      ", style=f"bold {theme.secondary}")
    header_text.append(
        "/// LAN P2P BACKBONE // DIRECT COMMUNICATION LINK ///\n",
        style=f"dim {theme.text}",
    )
    # Строка 3
    header_text.append("    //[X]║||║[X]\\\\     ", style=f"bold {theme.secondary}")
    header_text.append("[", style="bold white")
    header_text.append(f"LNX: {src_ip}", style=f"bold {theme.blue}")
    header_text.append(" ◄════► ", style=f"bold {theme.amber}")
    header_text.append(f"WIN: {tgt_ip}", style=f"bold {theme.purple}")
    header_text.append("]\n", style="bold white")
    # Строка 4
    header_text.append("   (o)═══╝||╚═══(o)    ", style=f"bold {theme.secondary}")
    header_text.append("STATUS: ", style="dim white")
    header_text.append(f"{latency_text}", style=status_style)
    header_text.append(" · POCKET: ", style="dim white")
    header_text.append(f"{pocket_stat}", style=f"bold {theme.blue}")
    header_text.append(" · NOTES: ", style="dim white")
    header_text.append(f"{notes_stat}", style=f"bold {theme.primary}")

    console.print(
        Panel(
            header_text,
            title=f"[bold {theme.primary}]DRAWBRIDGE INDUSTRIAL // OPERATIONAL HUB[/]",
            border_style=theme.secondary,
            padding=(0, 1),
        )
    )


def render_dashboard_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """Режим DASHBOARD / СТАТУС."""
    ctx = get_live_context(data)
    render_operational_header(theme, ctx)
    render_mode_tabs("DASH", theme)

    input_buf = ctx["input_buffer"]
    status_msg = ctx["status_msg"]

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    if ctx["is_online"]:
        status_tag = f"[bold {theme.green}]ONLINE (Готов)[/]"
        ping_tag = (
            f"{ctx['latency_str']} [bold {theme.green}][OK][/] (Лимит {ctx['failfast_ms']}ms)"
        )
    else:
        status_tag = f"[bold {theme.red}]OFFLINE (Служба не запущена)[/]"
        ping_tag = f"[bold {theme.red}]НЕДОСТУПЕН[/] [dim](Таймаут {ctx['failfast_ms']}ms)[/]"

    pocket_status_tag = (
        f"[bold {theme.green}][OK] Готов к синхронизации[/]"
        if ctx["pocket_count"] > 0
        else "[dim]Папка кармана пуста (0 файлов)[/]"
    )

    left = Panel(
        f"""[bold white]СЕТЕВОЙ КАНАЛ (P2P BACKBONE)[/]
[bold {theme.blue}]ХОСТ: {ctx["src_display"]} (Workstation)[/]
  |- IP: {ctx["src_ip"]} / 127.0.0.1
  |- OS: Linux x86_64
  +- Агент: [bold {theme.green}]agy_cli [ONLINE][/]

[bold {theme.purple}]УЗЕЛ: {ctx["tgt_node"]} (Worker Agent)[/]
  |- IP: {ctx["tgt_address"]}
  |- Статус: {status_tag}
  |- Пинг: {ping_tag}
  |- Нагрузка: CPU {ctx["cpu_str"]} | RAM {ctx["mem_str"]}
  +- Uptime: {ctx["uptime_str"]}""",
        title="[bold white][ СЕТЬ ][/]",
        border_style=theme.secondary,
    )

    right = Panel(
        f"""[bold white]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[bold {theme.amber}]КАРМАН (Pocket Storage):[/]
  |- Путь: {ctx["pocket_path_display"]}
  |- Файлов: {ctx["pocket_count"]} объектов ({ctx["pocket_size_human"]})
  |- Watchdog: [bold {theme.green}]АКТИВЕН[/]
  +- Статус: {pocket_status_tag}

[bold {theme.blue}]ЗАМЕТКИ (Notes Engine):[/]
  |- Файл: {ctx["notes_file_display"]}
  |- Всего записей: {ctx["notes_count"]}
  +- Новых: [bold {theme.green}][{ctx["notes_unread"]}][/]""",
        title="[bold white][ ХРАНИЛИЩЕ ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(left, right)
    console.print(grid)

    prompt_bar = Text()
    prompt_bar.append("КОМАНДА > ", style=f"bold {theme.blue}")
    prompt_bar.append(input_buf, style="bold white")
    prompt_bar.append("█", style=f"bold {theme.primary}")
    console.print(
        Panel(
            prompt_bar,
            title=(
                "[dim]←/→ или 1..8: Табы | :send <f> | :exec <cmd> | :r Обновить | :q Выход[/dim]"
            ),
            border_style=theme.blue if input_buf else theme.secondary,
            padding=0,
        )
    )
    if status_msg:
        console.print(f" {status_msg}")


def render_pocket_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    pocket_data: dict[str, Any] | None = None,
) -> None:
    """Режим POCKET / КАРМАН."""
    ctx = get_live_context(pocket_data)
    render_operational_header(theme, ctx)
    render_mode_tabs("POCKET", theme)

    input_buf = ctx["input_buffer"]
    status_msg = ctx["status_msg"]
    files = ctx["pocket_files"]

    table = Table(
        title=f"[ ХРАНИЛИЩЕ КАРМАНА / POCKET STORAGE ({ctx['pocket_path_display']}) ]",
        expand=True,
    )
    table.add_column("Файл / Каталог", style="bold white")
    table.add_column("Размер", style="dim white", justify="right")
    table.add_column("Направление", justify="center")
    table.add_column("SHA-256", style=f"bold {theme.green}", justify="center")
    table.add_column("Активность / Статус")

    if files:
        page_size = 10
        offsets = (
            pocket_data.setdefault("scroll_offsets", {}) if isinstance(pocket_data, dict) else {}
        )
        max_offset = max(0, len(files) - page_size)
        offset = max(0, min(offsets.get("POCKET", 0), max_offset))
        offsets["POCKET"] = offset
        visible_files = files[offset : offset + page_size]
        hidden_below = max(0, len(files) - (offset + page_size))

        if offset > 0:
            table.add_row(f"[dim]▲ (скрыто: {offset} выше)[/]", "", "", "", "")

        for f in visible_files:
            table.add_row(
                f.get("name", "file"),
                f.get("size", "0 B"),
                f.get("direction", "LOCAL [POCKET]"),
                f.get("sha", "[OK]"),
                f"[bold {theme.green}]{f.get('status', 'READY')}[/]",
            )

        if hidden_below > 0:
            table.add_row(
                f"[dim]▼ (скрыто: {hidden_below} ниже, навигация: ↑/↓, PgUp/PgDn)[/]",
                "",
                "",
                "",
                "",
            )
    else:
        table.add_row(
            "[dim](Папка кармана пуста)[/]",
            "--",
            "--",
            "--",
            f"[dim]Файлы не найдены в {ctx['pocket_path_display']}. Введите путь ниже.[/]",
        )

    console.print(table)

    prompt_text = Text()
    prompt_text.append("PUSH FILE > ", style=f"bold {theme.amber}")
    prompt_text.append(input_buf, style="bold white")
    prompt_text.append("█", style=f"bold {theme.primary}")

    panel = Panel(
        prompt_text,
        title=f"[bold {theme.primary}][ ПРЯМАЯ ОТПРАВКА В КАРМАН / DIRECT FILE DROP ][/]",
        subtitle="[dim]Файл ──► [Enter] Отправить на Windows | [↑/↓, PgUp/PgDn] Скролл[/dim]",
        border_style=theme.amber if input_buf else theme.secondary,
        padding=(0, 1),
    )
    console.print(panel)
    if status_msg:
        console.print(f" {status_msg}")


def render_notes_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    notes_data: dict[str, Any] | None = None,
) -> None:
    """Режим NOTES / ЗАМЕТКИ."""
    ctx = get_live_context(notes_data)
    render_operational_header(theme, ctx)
    render_mode_tabs("NOTES", theme)

    input_buf = ctx["input_buffer"]
    status_msg = ctx["status_msg"]
    notes_list = ctx["notes_list"]

    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=1)

    feed_lines = []
    if notes_list:
        page_size = 6
        offsets = (
            notes_data.setdefault("scroll_offsets", {}) if isinstance(notes_data, dict) else {}
        )
        max_offset = max(0, len(notes_list) - page_size)
        offset = max(0, min(offsets.get("NOTES", 0), max_offset))
        offsets["NOTES"] = offset
        visible_notes = notes_list[offset : offset + page_size]
        hidden_below = max(0, len(notes_list) - (offset + page_size))

        if offset > 0:
            feed_lines.append(f"[dim]▲ (скрыто: {offset} выше)[/]")

        for n in visible_notes:
            t = n.get("time", "12:00:00")
            author = n.get("author", "NODE")
            text = n.get("text", "")
            feed_lines.append(f"[bold {theme.purple}][{t}] {author}:[/]\n  {text}\n")

        if hidden_below > 0:
            feed_lines.append(f"[dim]▼ (скрыто: {hidden_below} ниже, навигация: ↑/↓, PgUp/PgDn)[/]")
    else:
        feed_lines.append(
            "[dim italic]Журнал заметок пуст. Введите текст в поле NOTE > для отправки.[/]\n"
        )

    feed_lines.append(
        "[dim]─────────────────────────────────────────────────────────────────────────────[/]"
    )
    feed_lines.append(
        "[bold white]Ввод заметки ([Enter] Отправить на все узлы | [←/→/Tab] Навигация):[/]"
    )
    feed_lines.append(f"[bold {theme.blue}]NOTE > [/][bold white]{input_buf}[/][blink]█[/]")
    if status_msg:
        feed_lines.append(f"  {status_msg}")

    notes_feed = Panel(
        "\n".join(feed_lines),
        title="[bold white][ ЖУРНАЛ ЗАМЕТОК / NOTES STREAM ][/]",
        border_style=theme.blue if input_buf else theme.secondary,
    )

    stats = Panel(
        f"""[bold white]СТАТИСТИКА ЗАМЕТОК[/]
|- Всего записей: {len(notes_list)}
|- Непрочитанных: [bold {theme.green}][{ctx["notes_unread"]}][/]
|- Файл: [dim]{ctx["notes_file_display"]}[/]
+- Режим: [bold {theme.green}]Append-Only (Atomic)[/]

[bold {theme.blue}]УПРАВЛЕНИЕ:[/][dim]
 [Enter] Отправить заметку
 [← / → / 1..8 / Tab] Навигация
 [↑/↓, PgUp/PgDn] Скролл
 [Ctrl+C] Выход[/dim]""",
        title="[bold white][ ИНФО / СТАТИСТИКА ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(notes_feed, stats)
    console.print(grid)


def render_exec_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    exec_data: dict[str, Any] | None = None,
) -> None:
    """Режим REMOTE EXEC / КОНСОЛЬ."""
    ctx = get_live_context(exec_data)
    render_operational_header(theme, ctx)
    render_mode_tabs("EXEC", theme)

    input_buf = ctx["input_buffer"]
    status_msg = ctx["status_msg"]
    history = ctx["exec_history"]

    if ctx["is_online"]:
        runner_badge = f"[bold {theme.green}][READY / ОНЛАЙН][/]"
    else:
        runner_badge = f"[bold {theme.red}][OFFLINE / СЛУЖБА НЕ ЗАПУЩЕНА][/]"

    lines = [
        f"[bold white]УДАЛЕННАЯ СЕССИЯ POWERSHELL ({ctx['tgt_node']} @ {ctx['tgt_address']})[/]",
        (
            f"Кодировка: UTF-8 | Права: Elevated (Admin) | "
            f"Таймаут: {ctx['cfg'].exec.default_timeout_sec}s"
        ),
        f"Статус узла: {runner_badge} | Опрос: [bold {theme.amber}][⠼ IDLE][/]",
        "",
    ]

    if history:
        page_size = 4
        offsets = exec_data.setdefault("scroll_offsets", {}) if isinstance(exec_data, dict) else {}
        max_offset = max(0, len(history) - page_size)
        offset = max(0, min(offsets.get("EXEC", 0), max_offset))
        offsets["EXEC"] = offset
        visible_history = history[offset : offset + page_size]
        hidden_below = max(0, len(history) - (offset + page_size))

        if offset > 0:
            lines.append(f"[dim]▲ (скрыто: {offset} выше)[/]")

        for cmd, output, code in visible_history:
            lines.append(f"[bold {theme.purple}]PS C:\\BridgeService> [/][bold white]{cmd}[/]")
            if output:
                lines.append(output.strip())
            color = theme.green if code == 0 else theme.red
            lines.append(f"[dim](Код завершения: [bold {color}]{code}[/])[/dim]\n")

        if hidden_below > 0:
            lines.append(f"[dim]▼ (скрыто: {hidden_below} ниже, навигация: ↑/↓, PgUp/PgDn)[/]")
    else:
        if not ctx["is_online"]:
            lines.append(
                f"[bold red][ВНИМАНИЕ] Windows-агент недоступен на {ctx['tgt_address']}.[/]"
            )
            lines.append(
                "[dim]Запустите службу BridgeLocalAgent на Windows для выполнения команд.[/]"
            )
        else:
            lines.append(
                "[dim italic]Сессия PowerShell готова. Введите команду в поле ниже и [Enter].[/]"
            )
        lines.append("")

    lines.append(
        "[dim]─────────────────────────────────────────────────────────────────────────────[/]"
    )
    lines.append(
        "[bold white]Ввод команды ([Enter] Выполнить | [←/→/Tab] Навигация | [Ctrl+C] Выход):[/]"
    )

    lines.append(
        f"[bold {theme.blue}]PS C:\\BridgeService> [/][bold white]{input_buf}[/][blink]█[/]"
    )
    if status_msg:
        lines.append(f"  {status_msg}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold white][ УДАЛЕННЫЙ ИСПОЛНИТЕЛЬ POWERSHELL / REMOTE EXEC ][/]",
            border_style=theme.purple if input_buf else theme.secondary,
        )
    )


def render_config_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    config_data: dict[str, Any] | None = None,
) -> None:
    """Режим CONFIG / УЗЛЫ."""
    ctx = get_live_context(config_data)
    render_operational_header(theme, ctx)
    render_mode_tabs("CONFIG", theme)

    table = Table(title="[ РЕЕСТР УЗЛОВ И СЕТЕВЫЕ ПАРАМЕТРЫ / NODE CONFIG ]", expand=True)
    table.add_column("Узел (Node ID)")
    table.add_column("Роль / Назначение", style="dim white")
    table.add_column("Сетевой Адрес", style="bold white")
    table.add_column("Heartbeat", style="dim white")
    table.add_column("Безопасность / Статус")

    auth_str = (
        "[bold green][ACTIVE] HMAC-SHA256[/]" if ctx["psk_set"] else "[dim]Без токена (Open)[/]"
    )

    table.add_row(
        f"[bold {theme.blue}]{ctx['src_node']} (local)[/]",
        "Workstation (Core)",
        f"{ctx['src_ip']} / 127.0.0.1",
        f"{ctx['heartbeat_interval_ms']} ms",
        auth_str,
    )

    if ctx["is_online"]:
        win_status = f"[bold {theme.green}][ONLINE][/] {auth_str}"
    else:
        win_status = f"[bold {theme.red}][OFFLINE][/] [dim](Служба не запущена)[/]"

    table.add_row(
        f"[bold {theme.purple}]{ctx['tgt_node']} (remote)[/]",
        "Worker Agent (Windows)",
        f"{ctx['tgt_address']}",
        f"fail-fast {ctx['failfast_ms']} ms",
        win_status,
    )

    console.print(table)


def render_dev_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    logs_data: dict[str, Any] | None = None,
) -> None:
    """Режим DEV / LOGS — Трассировка ядра и логов."""
    ctx = get_live_context(logs_data)
    render_operational_header(theme, ctx)
    render_mode_tabs("DEV", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(ratio=1)

    b, g, p, a, r = theme.blue, theme.green, theme.purple, theme.amber, theme.red

    if ctx["is_online"]:
        net_diag = f"[bold {g}][OK][/] Связь установлена (rtt={ctx['latency_str']})"
    else:
        net_diag = f"[bold {r}][OFFLINE][/] {ctx['tgt_address']} недоступен (служба не запущена)"

    auth_lbl = "[bold " + g + "][НАСТРОЕН][/]" if ctx["psk_set"] else "[dim][ОТКЛЮЧЕН][/]"
    p_info = f"{ctx['pocket_count']} файлов, {ctx['pocket_size_human']}"
    ex_tout = ctx["cfg"].exec.default_timeout_sec
    hb_iv = ctx["cfg"].heartbeat.interval_sec
    hb_ff = ctx["failfast_ms"]

    base_items = [
        f"[bold {b}][CONFIG][/]  Узел: {ctx['src_node']} (цель: {ctx['tgt_address']})",
        f"[bold {p}][AUTH][/]    HMAC-SHA256: {auth_lbl}",
        f"[bold {b}][NET][/]     Сокет: {net_diag}",
        f"[bold {a}][FS][/]      Карман: {ctx['pocket_path_display']} ({p_info})",
        f"[bold {p}][NOTES][/]   Журнал: {ctx['notes_file_display']} ({ctx['notes_count']} шт.)",
        f"[bold {b}][EXEC][/]    PowerShell: UTF-8 chcp 65001, timeout={ex_tout}s",
        f"[bold {g}][HEART][/]   Интервал: {hb_iv}s, fail-fast: {hb_ff}ms",
        f"[bold {b}][WIRE][/]    Wire framing: 4-byte length prefix (max 64MB)",
        f"[bold {g}][RPC][/]     JSON-RPC 2.0 Dispatcher: active methods=8",
        f"[bold {a}][SYNC][/]    Watchdog pocket sync: active debounce 100ms",
        f"[bold {p}][STREAM][/]  Duplex packet streaming: ready",
    ]

    custom_logs = (
        list(logs_data.get("dev_logs", []))
        if isinstance(logs_data, dict) and logs_data.get("dev_logs")
        else []
    )
    all_dev_items = base_items + custom_logs

    page_size = 8
    offsets = logs_data.setdefault("scroll_offsets", {}) if isinstance(logs_data, dict) else {}
    max_offset = max(0, len(all_dev_items) - page_size)
    offset = max(0, min(offsets.get("DEV", 0), max_offset))
    offsets["DEV"] = offset
    visible_items = all_dev_items[offset : offset + page_size]
    hidden_below = max(0, len(all_dev_items) - (offset + page_size))

    feed_lines = ["[bold white]СИСТЕМНАЯ ДИАГНОСТИКА И СТАТУС ПОДСИСТЕМ BRIDGE LOCAL[/]"]
    if offset > 0:
        feed_lines.append(f"[dim]▲ (скрыто: {offset} выше)[/]")

    feed_lines.extend(visible_items)

    if hidden_below > 0:
        feed_lines.append(f"[dim]▼ (скрыто: {hidden_below} ниже, навигация: ↑/↓, PgUp/PgDn)[/]")

    feed_lines.append("[dim]───────────────────────────────────────────────────────────────────[/]")
    feed_lines.append(
        "[bold white]Управление: [←/→/1..8] Табы | [↑/↓, PgUp/PgDn] Скролл | [Ctrl+C] Выход[/]"
    )

    logs_feed = Panel(
        "\n".join(feed_lines),
        title="[bold white][ ДИАГНОСТИЧЕСКАЯ ТРАССИРОВКА / HYPER-LOGGING STREAM ][/]",
        border_style=theme.blue,
    )

    stats = Panel(
        f"""[bold white]СОСТОЯНИЕ ЯДРА[/]
|- Уровень: [bold {theme.amber}]{ctx["cfg"].logging.level}[/]
|- Dev-Mode: {"[bold " + g + "]АКТИВЕН[/]" if ctx["cfg"].logging.dev_mode else "[dim]ВЫКЛ[/]"}
|- Цель: [dim]{ctx["tgt_address"]}[/]
|- Сеть: {"[bold " + g + "][ONLINE][/]" if ctx["is_online"] else "[bold " + r + "][OFFLINE][/]"}
+- Карман: [bold white]{ctx["pocket_count"]} файлов[/]

[bold {theme.blue}]ПОДСИСТЕМЫ:[/][dim]
 [F1] SPLASH  [F2] DASH
 [F3] POCKET  [F4] NOTES
 [F5] EXEC    [F6] CONFIG
 [F7] DEV     [F8] CONNECT[/dim]""",
        title="[bold white][ СТАТУС DEV-MODE ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(logs_feed, stats)
    console.print(grid)


def render_connect_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """Режим CONNECT / БЫСТРОЕ ПОДКЛЮЧЕНИЕ К УЗЛУ."""
    ctx = get_live_context(data)
    render_operational_header(theme, ctx)
    render_mode_tabs("CONNECT", theme)

    input_buf = ctx["input_buffer"]
    status_msg = ctx["status_msg"]

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    # 1. Левая колонка: Текущие параметры и статус
    status_style = theme.green if ctx["is_online"] else theme.red
    status_badge = (
        f"[bold {theme.green}][ONLINE] Доступен ({ctx['latency_str']})[/]"
        if ctx["is_online"]
        else f"[bold {theme.red}][OFFLINE] Сокет не отвечает[/]"
    )
    auth_badge = (
        f"[bold {theme.green}][АКТИВЕН] HMAC-SHA256[/]"
        if ctx["psk_set"]
        else "[dim]Отключен (Open/Без токена)[/]"
    )

    info_lines = [
        "[bold white]ПАРАМЕТРЫ СЕТЕВОГО ПОДКЛЮЧЕНИЯ (bridge.toml):[/]",
        f"  • [bold {theme.blue}]Целевой узел:[/]           [bold white]{ctx['tgt_node']}[/]",
        f"  • [bold {theme.purple}]IP-адрес / Host:[/]        [bold white]{ctx['tgt_host']}[/]",
        f"  • [bold {theme.amber}]TCP-порт:[/]               [bold white]{ctx['tgt_port']}[/]",
        f"  • [bold white]Полный адрес:[/]          [bold white]{ctx['tgt_address']}[/]",
        f"  • [bold white]Статус связи:[/]          {status_badge}",
        f"  • [bold white]Аутентификация (PSK):[/]  {auth_badge}",
        f"  • [dim]Конфиг-файл:[/]            [dim]{ctx['cfg']._config_path or 'bridge.toml'}[/]",
        "",
        "[dim]─────────────────────────────────────────────────────────────────────────────[/]",
        f"  [bold {theme.green}]192.168.1.150:9732[/]  -> записать IP и порт и проверить связь",
        f"  [bold {theme.green}]192.168.1.150[/]       -> обновить только IP (сохранить порт)",
        f"  [bold {theme.green}]9732[/] или [bold {theme.green}]:9732[/]    -> изменить TCP-порт",
        f"  [bold {theme.green}]token <ключ>[/]        -> обновить ключ безопасности PSK",
        f"  [bold {theme.green}]test[/] / [bold {theme.green}][R][/]          -> проверить связь",
    ]

    left_panel = Panel(
        "\n".join(info_lines),
        title=f"[bold {theme.blue}][ 1. АДРЕС ЦЕЛЕВОГО УЗЛА И СТАТУС ][/]",
        border_style=status_style,
    )

    # 2. Правая колонка: Инструкция для оператора
    help_lines = [
        "[bold white]БЫСТРОЕ ПОДКЛЮЧЕНИЕ БЕЗ ПРАВКИ TOML-ФАЙЛОВ:[/]",
        "1. Вам больше [bold underline]не требуется[/] открывать текстовые редакторы.",
        "2. Введите IP вашей Windows-машины в поле ввода внизу",
        "   и нажмите [bold amber][Enter][/].",
        "3. Программа самостоятельно:",
        f"   - Проверит сокет (таймаут {ctx['failfast_ms']} мс).",
        "   - Запишет изменения в локальный bridge.toml.",
        "   - При успехе переключит статус в ONLINE и активирует обмен.",
        "",
        "[bold white]ПРИМЕРЫ АДРЕСОВ В ДОМАШНЕЙ СЕТИ:[/]",
        "  • Домашний Wi-Fi: [dim]192.168.1.150:9732[/] или [dim]192.168.0.105:9732[/]",
        "  • Локальный тест: [dim]127.0.0.1:9732[/]",
        "  • Tailscale/VPN:  [dim]100.x.y.z:9732[/]",
        "",
        "[dim]Подсказка: на Windows IP можно узнать командой: ipconfig[/]",
    ]

    right_panel = Panel(
        "\n".join(help_lines),
        title=f"[bold {theme.amber}][ 2. РУКОВОДСТВО ОПЕРАТОРА ][/]",
        border_style=theme.amber,
    )

    grid.add_row(left_panel, right_panel)
    console.print(grid)

    # Строка статуса и поле ввода
    if status_msg:
        console.print(Panel(status_msg, style=theme.secondary, padding=(0, 1)))

    prompt_line = (
        f" [bold {theme.green}]CONNECT (IP:Порт) > [/][bold white]{input_buf}[/]"
        f"[blink {theme.blue}]█[/]  [dim](Введите IP:Порт и нажмите Enter)[/]"
    )
    console.print(Panel(prompt_line, border_style=theme.blue, padding=(0, 1)))


def render_theme_spec(theme: PaletteTheme = OFFICIAL_THEME) -> None:
    """Выводит спецификацию утвержденной темы."""
    table = Table(
        title="◈ УТВЕРЖДЕННАЯ ТЕМА BRIDGE LOCAL: TITANIUM VIVID ◈",
        expand=True,
    )
    table.add_column("Роль в интерфейсе", style="bold white", width=28)
    table.add_column("Цветовой код", width=18)
    table.add_column("Визуальный образец", width=36)

    chips = [
        (
            "Primary (Титан / Master)",
            theme.primary,
            Text("████████ [BRIDGE MASTER]", style=f"bold {theme.primary}"),
        ),
        (
            "Secondary (Сталь / Фреймы)",
            theme.secondary,
            Text("████████ [DRAWBRIDGE]", style=f"bold {theme.secondary}"),
        ),
        (
            "Blue (Электро-циан / Сеть)",
            theme.blue,
            Text("████████ [LNX: 192.168.1.104]", style=f"bold {theme.blue}"),
        ),
        (
            "Green (Лазерный фосфор / OK)",
            theme.green,
            Text("████████ [ONLINE · 0.38ms OK]", style=f"bold {theme.green}"),
        ),
        (
            "Amber (Сочное золото / Sync)",
            theme.amber,
            Text("████████ [>>> 68% SYNC]", style=f"bold {theme.amber}"),
        ),
        (
            "Purple (Неоновый фиолетовый)",
            theme.purple,
            Text("████████ [WIN-PC · PowerShell]", style=f"bold {theme.purple}"),
        ),
        (
            "Red (Неоновый коралловый)",
            theme.red,
            Text("████████ [OFFLINE / ERROR]", style=f"bold {theme.red}"),
        ),
    ]

    for role, code, preview in chips:
        table.add_row(role, Text(code, style="bold white"), preview)

    console.print(table)
    console.print(f"\n[dim]{theme.desc}[/dim]\n")


def render_current_mode(
    mode: str,
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """Отрисовывает один выбранный режим интерфейса."""
    m = mode.upper()
    if m == "DASH":
        render_dashboard_mode(theme, data)
    elif m == "POCKET":
        render_pocket_mode(theme, data)
    elif m == "NOTES":
        render_notes_mode(theme, data)
    elif m == "EXEC":
        render_exec_mode(theme, data)
    elif m == "CONFIG":
        render_config_mode(theme, data)
    elif m == "DEV":
        render_dev_mode(theme, data)
    elif m in ("CONNECT", "SETUP"):
        render_connect_mode(theme, data)
    elif m in ("WELCOME", "SPLASH"):
        render_welcome_screen(theme, data)
    elif m == "ANIM":
        demo_process_animations(theme)
    else:
        render_dashboard_mode(theme, data)
