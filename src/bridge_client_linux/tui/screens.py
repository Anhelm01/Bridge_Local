"""
bridge_client_linux.tui.screens — Отрисовка экранов и рабочих режимов Bridge Local.

Реализует:
  1. Full-screen Neofetch экран приветствия (BRIDGES Master).
  2. Шапку оперативных окон DRAWBRIDGE Industrial.
  3. Вкладки [F1..F6] / [1..6]:
     - DASH: сводный дашборд сети, узлов и очередей
     - POCKET: список и статус хранилища кармана
     - NOTES: лента быстрых заметок
     - EXEC: удалённый терминал PowerShell
     - CONFIG: реестр узлов и параметры подключения
     - DEV: журнал трассировки и логов
"""

from __future__ import annotations

import shutil
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

console = Console()


def render_welcome_screen(
    theme: PaletteTheme = OFFICIAL_THEME,
    status_data: dict[str, Any] | None = None,
) -> None:
    """Выводит экран приветствия Neofetch с центрированным BRIDGES Master и системным статусом."""
    term_width, _ = shutil.get_terminal_size((120, 40))

    p = theme.primary
    s = theme.secondary
    w = theme.text
    b = theme.blue
    g = theme.green
    a = theme.amber
    pu = theme.purple

    d = status_data or {}
    node_src = d.get("node", {}).get("source", "LINUX-HOST")
    node_tgt = d.get("node", {}).get("target", "WIN-PC")
    tgt_host = d.get("node", {}).get("host", "192.168.1.150")
    tgt_port = d.get("node", {}).get("port", 9732)
    latency = d.get("connection", {}).get("latency_ms", 0.38)
    remote_os = d.get("remote", {}).get("os", "windows")
    remote_status = d.get("remote", {}).get("status", "ready")
    pocket_files = d.get("pocket", {}).get("remote_files", 18)
    pocket_bytes_mb = round(d.get("pocket", {}).get("remote_bytes", 1400000000) / (1024 * 1024), 1)
    notes_count = d.get("notes", {}).get("total", 42)
    notes_unread = d.get("notes", {}).get("unread", 0)

    info = f"""[bold {w}]anhelm@workstation[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Host OS:[/]        Linux x86_64 (Arch/Debian/Fedora)
[bold {b}]Local Node:[/]     {node_src} (127.0.0.1)
[bold {s}]Core Operator:[/]  agy_cli (Antigravity CLI Agent)

[bold {pu}]Remote Node:[/]    {node_tgt} ({tgt_host}:{tgt_port})
[bold {pu}]Remote OS:[/]      {remote_os.capitalize()} 64-bit
[bold {pu}]Remote Agent:[/]   BridgeLocalAgent [bold {g}][{remote_status.upper()}][/]

[bold {b}]СВЯЗЬ И ПРОТОКОЛ (P2P BACKBONE)[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Канал связи:[/]    P2P Direct LAN / Sockets
[bold {s}]Пинг (Latency):[/]  {latency} ms [bold {g}][STABLE LAN · OK][/]
[bold {s}]Безопасность:[/]    HMAC-SHA256 Challenge-Response Session
[bold {s}]Транспорт:[/]       JSON-RPC 2.0 / Length-Prefix Wire Framing
[bold {s}]Fail-Fast:[/]       1500 ms (Мгновенное обнаружение обрыва)

[bold {a}]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Карман (Pocket):[/] ~/.bridge_local/pocket/
[bold {s}]Файлов в кармане:[/] {pocket_files} об. ({pocket_bytes_mb} MB) [bold {g}][SHA-256 OK][/]
[bold {s}]Заметки (Notes):[/] {notes_count} записей [bold {g}][{notes_unread} непрочитанных][/]"""

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
    m = metrics or {}
    src_ip = m.get("src_ip", "192.168.1.104")
    tgt_ip = m.get("tgt_ip", "192.168.1.150:9732")
    latency = m.get("latency_ms", "0.38ms [OK]")
    pocket_pct = m.get("pocket_pct", "100%")
    notes_stat = m.get("notes_stat", "0 UNREAD")

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
    header_text.append(f"{latency}", style=f"bold {theme.green}")
    header_text.append(" · POCKET: ", style="dim white")
    header_text.append(f"{pocket_pct}", style=f"bold {theme.blue}")
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


def render_mode_tabs(active_mode: str, theme: PaletteTheme = OFFICIAL_THEME) -> None:
    """Верхний таб-бар переключения режимов."""
    modes = [
        ("DASH", "1"),
        ("POCKET", "2"),
        ("NOTES", "3"),
        ("EXEC", "4"),
        ("CONFIG", "5"),
        ("DEV", "6"),
    ]
    bar = Text()
    bar.append("[BRIDGE] ", style=f"bold black on {theme.blue}")
    for i, (name, key) in enumerate(modes):
        if name == active_mode:
            bar.append(f"█ {key}:{name}", style="bold white on #1F6FEB")
        else:
            bar.append(f"{key}:{name}", style=f"dim {theme.secondary}")
        if i < len(modes) - 1:
            bar.append(" │ ")
    console.print(Panel(bar, style=theme.secondary, expand=True, padding=0))


def render_dashboard_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    data: dict[str, Any] | None = None,
) -> None:
    """Режим 1: DASHBOARD / СТАТУС (F1)."""
    render_operational_header(theme)
    render_mode_tabs("DASH", theme)

    d = data or {}
    cpu = d.get("remote", {}).get("cpu_percent", 2.4)
    mem = d.get("remote", {}).get("memory_used_mb", 14320)
    uptime = d.get("remote", {}).get("uptime_seconds", 412320)
    uptime_str = f"{uptime // 86400}d {(uptime % 86400) // 3600}h {(uptime % 3600) // 60}m"

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    left = Panel(
        f"""[bold white]СЕТЕВОЙ КАНАЛ (P2P BACKBONE)[/]
[bold {theme.blue}]ХОСТ: LINUX (Workstation)[/]
  |- IP: 127.0.0.1 / 192.168.1.104
  |- OS: Linux x86_64
  +- Агент: [bold {theme.green}]agy_cli [ONLINE][/]

[bold {theme.purple}]УЗЕЛ: WIN-PC (Service Daemon)[/]
  |- IP: 192.168.1.150:9732
  |- Статус: [bold {theme.green}]ONLINE (Готов)[/]
  |- Пинг: 0.38 ms [bold {theme.green}][OK][/] (Лимит 1.5s)
  |- Нагрузка: CPU {cpu}% | RAM {mem} MB
  +- Uptime: {uptime_str}""",
        title="[bold white][ СЕТЬ ][/]",
        border_style=theme.secondary,
    )

    right = Panel(
        f"""[bold white]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[bold {theme.amber}]КАРМАН (Pocket Storage):[/]
  |- Путь: ~/.bridge_local/pocket/
  |- Файлов: 18 объектов (1.4 GB)
  |- Watchdog: [bold {theme.green}]АКТИВЕН (0.5s)[/]
  +- Статус: [bold {theme.green}][OK] 100% SHA-256[/]

[bold {theme.blue}]ЗАМЕТКИ (Notes Engine):[/]
  |- Файл: notes.jsonl
  |- Всего записей: 42
  +- Новых: [bold {theme.green}][0] (Все OK)[/]""",
        title="[bold white][ ХРАНИЛИЩЕ ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(left, right)
    console.print(grid)


def render_pocket_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    pocket_data: dict[str, Any] | None = None,
) -> None:
    """Режим 2: POCKET / КАРМАН (F2)."""
    render_operational_header(theme)
    render_mode_tabs("POCKET", theme)

    table = Table(
        title="[ ХРАНИЛИЩЕ КАРМАНА / POCKET STORAGE (~/.bridge_local/pocket/) ]", expand=True
    )
    table.add_column("Файл / Каталог", style="bold white")
    table.add_column("Размер", style="dim white", justify="right")
    table.add_column("Направление", justify="center")
    table.add_column("SHA-256", style=f"bold {theme.green}", justify="center")
    table.add_column("Активность / Статус")

    table.add_row(
        "report_phase_05.docx",
        "2.4 MB",
        f"[bold {theme.blue}]LNX --> WIN[/]",
        "[OK] d9e4f1a...",
        f"[bold {theme.green}]SYNCED[/]",
    )
    table.add_row(
        "setup_env_win.ps1",
        "12.8 KB",
        f"[bold {theme.purple}]WIN --> LNX[/]",
        "[OK] 3a7c88b...",
        f"[bold {theme.green}]SYNCED[/]",
    )
    table.add_row(
        "model_weights.bin",
        "1.2 GB",
        f"[bold {theme.blue}]LNX --> WIN[/]",
        f"[bold {theme.amber}][⠋ SYNC][/]",
        f"[bold {theme.amber}][>>> 68%][/] [bold {theme.blue}]48 MB/s[/]",
    )
    table.add_row(
        "screenshot_crash.png",
        "840 KB",
        f"[bold {theme.purple}]WIN --> LNX[/]",
        "[OK] f7a012c...",
        f"[bold {theme.green}]SYNCED[/]",
    )

    console.print(table)


def render_notes_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    notes_data: dict[str, Any] | None = None,
) -> None:
    """Режим 3: NOTES / ЗАМЕТКИ (F3)."""
    render_operational_header(theme)
    render_mode_tabs("NOTES", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=1)

    notes_feed = Panel(
        f"""[bold {theme.purple}][10:04:15] WIN-PC (Windows Operator):[/]
  Служба BridgeLocalAgent запущена в фоне, кодировка UTF-8 (chcp 65001) проверена.

[bold {theme.blue}][10:08:22] LINUX (Antigravity agy_cli):[/]
  Интеграционные тесты ядра и RPC завершены успешно (151 тест, 9.64с).
  Подготовлена передача весов модели через карман.

[bold {theme.amber}][10:11:03] USER (Operator Note):[/]
  Проверь температуру GPU на Windows перед запуском бенчмарка.

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод новой заметки ([Enter] Отправить на все узлы | [Esc] Отмена):[/]
[bold {theme.blue}]> [/][blink]_[/]""",
        title="[bold white][ ЖУРНАЛ ЗАМЕТОК / NOTES STREAM ][/]",
        border_style=theme.secondary,
    )

    stats = Panel(
        f"""[bold white]СТАТИСТИКА ЗАМЕТОК[/]
|- Всего записей: 43
|- Непрочитанных: [bold {theme.green}][0][/]
|- Файл: [dim]notes.jsonl[/]
+- Режим: [bold {theme.green}]Append-Only (Atomic)[/]

[bold {theme.blue}]ФИЛЬТРЫ:[/][dim]
 [A] Все заметки
 [U] Только новые
 [S] Поиск по тексту[/dim]""",
        title="[bold white][ ИНФО / СТАТИСТИКА ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(notes_feed, stats)
    console.print(grid)


def render_exec_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    exec_data: dict[str, Any] | None = None,
) -> None:
    """Режим 4: REMOTE EXEC / КОНСОЛЬ (F4)."""
    render_operational_header(theme)
    render_mode_tabs("EXEC", theme)

    console.print(
        Panel(
            f"""[bold white]УДАЛЕННАЯ СЕССИЯ POWERSHELL (WIN-PC)[/]
Кодировка: UTF-8 (chcp 65001) | Права: Elevated (Admin) | Таймаут: 30s
Статус раннера: [bold {theme.green}][READY][/] | Фоновый опрос: [bold {theme.amber}][⠼ IDLE][/]

[bold {theme.purple}]PS C:\\BridgeService> [/][white]Get-Service -Name "BridgeLocalAgent"[/]

Status   Name               DisplayName
------   ----               -----------
[bold {theme.green}]Running[/]  BridgeLocalAgent   Bridge Local Windows Daemon v0.4.0

[bold {theme.purple}]PS C:\\BridgeService> [/][white]Get-Process python | Select Id, WS[/]

   Id        CPU       WS
   --        ---       --
 4912   1.421875 42811392

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод команды ([Enter] Выполнить на WIN-PC | [Ctrl+C] Прервать):[/]
[bold {theme.blue}]PS C:\\BridgeService> [/] [blink]_[/]""",
            title="[bold white][ УДАЛЕННЫЙ ИСПОЛНИТЕЛЬ POWERSHELL / REMOTE EXEC ][/]",
            border_style=theme.secondary,
        )
    )


def render_config_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    config_data: dict[str, Any] | None = None,
) -> None:
    """Режим 5: CONFIG / УЗЛЫ (F5)."""
    render_operational_header(theme)
    render_mode_tabs("CONFIG", theme)

    table = Table(title="[ РЕЕСТР УЗЛОВ И СЕТЕВЫЕ ПАРАМЕТРЫ / NODE CONFIG ]", expand=True)
    table.add_column("Узел (Node ID)")
    table.add_column("Роль / Назначение", style="dim white")
    table.add_column("Сетевой Адрес", style="bold white")
    table.add_column("Heartbeat", style="dim white")
    table.add_column("Безопасность")

    table.add_row(
        f"[bold {theme.blue}]LINUX-HOST (local)[/]",
        "Workstation (Core)",
        "127.0.0.1 / 192.168.1.104",
        "1500 ms",
        f"[bold {theme.green}][ACTIVE] HMAC-SHA256[/]",
    )
    table.add_row(
        f"[bold {theme.purple}]WIN-PC (remote)[/]",
        "Worker Agent",
        "192.168.1.150:9732",
        "1500 ms",
        f"[bold {theme.green}][ACTIVE] HMAC-SHA256[/]",
    )
    table.add_row(
        f"[dim {theme.secondary}]NODE-MACBOOK (future)[/]",
        "Mobile Node (mesh)",
        "192.168.1.112:9732",
        "3000 ms",
        f"[dim {theme.red}][OFFLINE][/]",
    )

    console.print(table)


def render_dev_mode(
    theme: PaletteTheme = OFFICIAL_THEME,
    logs_data: dict[str, Any] | None = None,
) -> None:
    """Режим 6: DEV / LOGS — Трассировка ядра и логов (F6)."""
    render_operational_header(theme)
    render_mode_tabs("DEV", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(ratio=1)

    b, g, p, a = theme.blue, theme.green, theme.purple, theme.amber
    logs_content = "\n".join(
        [
            "[bold white]ЖУРНАЛ ДИАГНОСТИКИ DEV-MODE (JSON-RPC + WIRE + PROXY)[/]",
            f"[dim]14:20:12.104[/] [bold {b}][WIRE][/]   len=184 crc=0x9A4F [bold {g}][OK][/]",
            f"[dim]14:20:12.106[/] [bold {p}][RPC][/]    id=199 ping=0.38ms [bold {g}][OK][/]",
            f"[dim]14:20:12.150[/] [bold {g}][PROXY][/]  bypass proxychains [bold {g}][OK][/]",
            f"[dim]14:20:12.210[/] [bold {a}][FS][/]     debounce=0.5s event=modify",
            f"[dim]14:20:12.280[/] [bold {a}][POCKET][/] chunk 19/20 64KB [bold {g}][SYNC][/]",
            f"[dim]14:20:12.350[/] [bold {p}][PROC][/]   PowerShell PID=4912 exit=0",
            f"[dim]14:20:12.420[/] [bold {g}][HEART][/]  rtt=0.38ms [bold {g}][HEALTHY][/]",
            "[dim]───────────────────────────────────────────────────────────────────[/]",
            "[bold white]Фильтры: [T] TRACE | [D] DEBUG | [I] INFO | [C] Clean | [P] Pause[/]",
            f"[bold {b}]DEV TRACE > [/][bold {g}]STREAMING ACTIVE[/] [blink]●[/]",
        ]
    )
    logs_feed = Panel(
        logs_content,
        title="[bold white][ ДИАГНОСТИЧЕСКАЯ ТРАССИРОВКА / HYPER-LOGGING STREAM ][/]",
        border_style=theme.blue,
    )

    stats = Panel(
        f"""[bold white]СОСТОЯНИЕ ЛОГГЕРА[/]
|- Уровень: [bold {theme.amber}]TRACE (Hyper)[/]
|- JSONL: [bold {theme.green}]АКТИВЕН[/]
|- Файл: [dim]logs/2026-09-30.jsonl[/]
|- Буфер: [bold white]4,812 / 10k[/]
|- Память: [dim]3.4 MB[/]
+- Proxy Guard: [bold {theme.green}][PASS][/]

[bold {theme.blue}]ПОДСИСТЕМЫ:[/][dim]
 [W] Wire Protocol
 [R] JSON-RPC
 [F] Pocket Watchdog
 [P] PowerShell Runner
 [H] Heartbeat Probe[/dim]""",
        title="[bold white][ СТАТУС DEV-MODE ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(logs_feed, stats)
    console.print(grid)


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
    elif m == "WELCOME":
        render_welcome_screen(theme, data)
    elif m == "ANIM":
        demo_process_animations(theme)
    else:
        render_dashboard_mode(theme, data)
