r"""
ref/AI/ascii_preview.py — Интерактивный генератор и демонстратор логотипов,
TUI интерфейса и 5 цветовых палитр Bridge Local.

Использование:
  uv run python ref/AI/ascii_preview.py all [1-5]       # Показать всё с выбранной палитрой
  uv run python ref/AI/ascii_preview.py welcome [1-5]   # Полноэкранный Neofetch экран приветствия
  uv run python ref/AI/ascii_preview.py modes [1-5]     # 5 оперативных рабочих окон (Drawbridge)
  uv run python ref/AI/ascii_preview.py anim [1-5]      # Анимация процессов (At-a-Glance)
  uv run python ref/AI/ascii_preview.py palettes        # Сравнительная таблица всех 5 палитр

Палитры:
  1: Acid Cyber / Plum Violet   (#D0FF00 Banana Yellow + #8116E0 Plum Violet) — новая из буфера
  2: Cyber Noir / Graphic Novel (#E6006A Electric Magenta + #027C7D Deep Teal) — буфер #1
  3: Chiral Amber / DS1 Classic (#F5A623 Chiral Gold + #56B6C2 Cyan / Navy) — канон Death Stranding
  4: Titanium Monochrome / Steel (#E6EDF3 Titanium White + #ABB2BF Cold Slate) — чистый минимализм
  5: Matrix Emerald / Tokyo     (#00FF66 Terminal Emerald + #0D7377 Deep Pine) — хакерский терминал
"""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ===========================================================================
# 1. ЕДИНАЯ ОФИЦИАЛЬНАЯ ТЕМА BRIDGE LOCAL (TITANIUM VIVID)
# ===========================================================================


@dataclass(frozen=True)
class PaletteTheme:
    name: str
    desc: str
    primary: str  # Главный цвет (логотип Master, акценты, титановый белый)
    secondary: str  # Вторичный цвет (логотип Industrial, стальные фермы, разделители)
    text: str  # Основной яркий белый текст
    muted: str  # Приглушенный цвет
    border: str  # Цвет контуров панелей
    blue: str  # Электрический ультра-циан (сеть, Linux, шина, ссылки)
    green: str  # Лазерный изумрудный (ONLINE, SYNCED, OK)
    amber: str  # Сочный янтарно-золотой (Карман, активная передача)
    purple: str  # Яркий неоновый фиолетовый (Windows-узел, PowerShell, Daemon)
    red: str  # Неоновый коралловый (ошибки, оффлайн)


OFFICIAL_THEME = PaletteTheme(
    name="Titanium Vivid / Cyber-Industrial",
    desc="Единая тема: авиационный титан и сталь с ультра-яркими акцентами",
    primary="#FFFFFF",  # Чистый лазерный белый титан
    secondary="#7D8590",  # Холодная индустриальная сталь
    text="#FFFFFF",  # Предельная четкость белого текста
    muted="#6E7681",  # Читаемый приглушенный
    border="#7D8590",  # Стальной контур
    blue="#00D2FF",  # Электрический ультра-циан (#00D2FF)
    green="#00FF66",  # Лазерный зеленый фосфор (#00FF66)
    amber="#FFB800",  # Сочный янтарно-золотой (#FFB800)
    purple="#C084FC",  # Яркий неоновый фиолетовый (#C084FC)
    red="#FF3366",  # Неоновый коралловый (#FF3366)
)


# ===========================================================================
# 2. ДВА ОФИЦИАЛЬНЫХ ЛОГОТИПА
# ===========================================================================

# 1. BRIDGES MASTER — для полноэкранного экрана приветствия (Neofetch)
BRIDGES_MASTER = r"""
                           .::.
                       .:/XXXXXX\:.
                    .:+HMM@@@@@@MMH+:.
                  . =XMM@##[#  #]##@MMX= .
                . +HMM@#-         -#@MMH+ .
              . =XMM@#-   /\   /\   -#@MMX= .
            . :dMM@#-    /  \ /  \    -#@MMb: .
          . :uMM@#-     / /\ V /\ \     -#@MMu: .
       ..::[dMM@#-     | |  | |  | |     -#@MMb]::..
     .:[u8NNMM@#-      | |  | |  | |      -#@MMNN8u]:.
   .:[dMM@@@MM@#-      | | /| |\ | |      -#@MM@@@MMb]:.
 .u8NNMM@#::#@MMX==.   |_|/_|_|_\|_|   .==XMM@#::#@MMNN8u.
:dMM@#-.     .-#@MMH+-.             .-+HMM@#-.     .-#@MMb:
\XX/-          .-\@MMX=============XMM@/-.          -\XX/
╔═════════════════════════════════════════════════════════╗
║  [#]     B  R  I  D  G  E  S     L  O  C  A  L     [#]  ║
║          ///  S T R A N D   N E T W O R K  ///          ║
╚═════════════════════════════════════════════════════════╝
/XX\-          .-/MM@X=============XMM@\-.          -/XX\
:dMM@#-.     .-#@MMH+-  \  \ | /  /  -+HMM@#-.     .-#@MMb:
 'u8NNMM@#::#@MMX==.  \  \  \|/  /  /  .==XMM@#::#@MMNN8u'
   ':[dMM@@@MM@#-   \  \  \  |  /  /  /   -#@MM@@@MMb]:'
     .:[u8NNMM@#- ---+---+---+---+---+--- -#@MMNN8u]:.
       ''::[dMM@#-    \   \  |  /   /    -#@MMb]::''
          ' :uMM@#-    \   \ | /   /    -#@MMu: '
            ' :dMM@#- --\---+---+--/-- -#@MMb: '
              ' =XMM@#-  \  \|/  /  -#@MMX= '
                ' +HMM@#- \  |  / -#@MMH+ '
                  ' =XMM@#--\+-/--#@MMX= '
                    ' :+HMM\#|#/MMH+: '
                       ':/XXXXXX\:'
                           '::'
"""

# 2. DRAWBRIDGE INDUSTRIAL — для оперативных рабочих окон и HUD
DRAWBRIDGE_INDUSTRIAL = r"""
                     .---:::///////:::---.
                 .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
              .-+XMM@@MM##XX++++++XX##MM@@MMX+-.
            ./HMM@#X+-.     ▄      ▄     .-+X#@MMH/.
          ./XMM#X-.        /║      ║\        .-X#MMX/.
        .+MM@X-.          //║  ||  ║\\          .-X@MM+.
       .+MM#-.           // ║  ||  ║ \\           .-#MM+.
      ./MM#-            //[X]║ || ║[X]\\            -#MM/.
     .X@M:             // [X]║ || ║[X] \\            :M@X.
     :MM+             //  [X]║ || ║[X]  \\            +MM:
     =MM-            //───[X]║ || ║[X]───\\           -MM=
     :MM+           //    [X]║ || ║[X]    \\          +MM:
     .X@M:         //     [X]║ || ║[X]     \\        :M@X.
      ./MM#-      //──────[X]║ || ║[X]──────\\      -#MM/.
       .+MM#-.   (o)═════════╝ || ╚═════════(o)   .-#MM+.
        .+MM@X-.       ▲   ▲   ▲   ▲   ▲        .-X@MM+.
          ./XMM#X-.   ═╩═══╩═══╩═══╩═══╩═══   .-X#MMX/.
            ./HMM@#X+-.                     .-+X#@MMH/.
              .-+XMM@@MM##XX++++++XX##MM@@MMX+-.
                 .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
                     .---:::///////:::---.
╔══════════════════════════════════════════════════════════╗
║             D   R   A   W   B   R   I   D   G   E        ║
║        ///   B O T H   S T I C K   A N D   R O P E   /// ║
║          TO PROTECT WITH STICK · TO CONNECT WITH ROPE    ║
╚══════════════════════════════════════════════════════════╝
"""

# Компактная версия DRAWBRIDGE INDUSTRIAL для верхней плашки окон
DRAWBRIDGE_HEADER = r"""      .▄█ ││ █▄.       D R A W B R I D G E  ::  B R I D G E   L O C A L
     //║  ||  ║\\      /// BOTH STICK AND ROPE : TO PROTECT AND CONNECT
    //[X]║||║[X]\\     [LNX: 192.168.1.104 ◄════► WIN: 192.168.1.150]
   (o)═══╝||╚═══(o)    STATUS: 0.38ms [OK] · POCKET: 100% · NOTES: 0 UNREAD"""


# ===========================================================================
# 3. ПОЛНОЭКРАННЫЙ ЭКРАН ПРИВЕТСТВИЯ (FULL-SCREEN NEOFETCH)
# ===========================================================================


def render_welcome_screen(theme: PaletteTheme) -> None:
    """Выводит полноэкранный экран приветствия с большим BRIDGES Master и Neofetch-сводкой."""
    term_width, _ = shutil.get_terminal_size((120, 40))

    p = theme.primary
    s = theme.secondary
    w = theme.text
    b = theme.blue
    g = theme.green
    a = theme.amber
    pu = theme.purple

    info = f"""[bold {w}]anhelm@workstation[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Host OS:[/]        Linux 6.13 (Arch Linux x86_64)
[bold {b}]Local Node:[/]     LINUX-HOST (192.168.1.104)
[bold {s}]Core Operator:[/]  agy_cli (Antigravity CLI Agent)

[bold {pu}]Remote Node:[/]    WIN-PC (192.168.1.150:41037)
[bold {pu}]Remote OS:[/]      Windows 11 Pro 64-bit (Build 26100)
[bold {pu}]Remote Agent:[/]   BridgeLocalAgent [bold {g}][RUNNING][/]

[bold {b}]СВЯЗЬ И ПРОТОКОЛ (P2P BACKBONE)[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Канал связи:[/]    P2P Direct LAN (1.0 Gbps Full Duplex)
[bold {s}]Пинг (Latency):[/]  0.38 ms [bold {g}][STABLE LAN · OK][/]
[bold {s}]Безопасность:[/]    HMAC-SHA256 Challenge-Response Session
[bold {s}]Транспорт:[/]       JSON-RPC 2.0 / Length-Prefix Wire Framing
[bold {s}]Fail-Fast:[/]       1500 ms (Мгновенное обнаружение обрыва)

[bold {a}]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
[bold {s}]Карман (Pocket):[/] ~/.bridge_local/pocket/
[bold {s}]Файлов в кармане:[/] 18 объектов (1.4 GB) [bold {g}][100% SHA-256 MATCH][/]
[bold {s}]Заметки (Notes):[/] 42 записи [bold {g}][0 непрочитанных][/]

[bold {b}]РЕЖИМЫ РАБОТЫ (MODES)[/]
[dim {s}]─────────────────────────────────────────────────────────────[/]
  [bold {b}][F1][/] Дашборд   [bold {a}][F2][/] Карман   [bold {b}][F3][/] Заметки
  [bold {pu}][F4][/] Exec      [bold {s}][F5][/] Конфиг   [bold {w}][Q][/]  Выход
"""

    logo_text = Text(BRIDGES_MASTER, style=f"bold {p}")
    logo_panel = Panel(
        logo_text,
        title=f"[bold {p}]◈ BRIDGES MASTER EMBLEM ◈[/]",
        subtitle=f"[dim {s}]STRAND NETWORK · LAN BACKBONE[/]",
        border_style=s,
    )
    info_panel = Panel(
        info,
        title=f"[bold {w}][ СИСТЕМНЫЙ СТАТУС / NEOFETCH ][/]",
        subtitle=f"[dim {b}]● THEME #{theme.id}: {theme.name}[/]",
        border_style=s,
    )

    if term_width >= 120:
        grid = Table.grid(expand=True)
        grid.add_column(width=63)
        grid.add_column(ratio=1)
        grid.add_row(logo_panel, info_panel)
        console.print(grid)
    else:
        console.print(logo_panel)
        console.print(info_panel)


# ===========================================================================
# 4. РАБОЧИЙ ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (DRAWBRIDGE INDUSTRIAL)
# ===========================================================================


def render_operational_header(theme: PaletteTheme) -> None:
    """Шапка оперативного окна с логотипом DRAWBRIDGE Industrial и яркими акцентами."""
    header_text = Text()
    # Строка 1
    header_text.append("      .▄█ ││ █▄.       ", style=f"bold {theme.secondary}")
    header_text.append("D R A W B R I D G E", style=f"bold {theme.primary}")
    header_text.append("  ::  ", style=f"bold {theme.secondary}")
    header_text.append("B R I D G E   L O C A L\n", style=f"bold {theme.blue}")
    # Строка 2
    header_text.append("     //║  ||  ║\\\\      ", style=f"bold {theme.secondary}")
    header_text.append(
        "/// BOTH STICK AND ROPE : TO PROTECT AND CONNECT\n",
        style=f"dim {theme.text}",
    )
    # Строка 3
    header_text.append("    //[X]║||║[X]\\\\     ", style=f"bold {theme.secondary}")
    header_text.append("[", style="bold white")
    header_text.append("LNX: 192.168.1.104", style=f"bold {theme.blue}")
    header_text.append(" ◄════► ", style=f"bold {theme.amber}")
    header_text.append("WIN: 192.168.1.150", style=f"bold {theme.purple}")
    header_text.append("]\n", style="bold white")
    # Строка 4
    header_text.append("   (o)═══╝||╚═══(o)    ", style=f"bold {theme.secondary}")
    header_text.append("STATUS: ", style="dim white")
    header_text.append("0.38ms [OK]", style=f"bold {theme.green}")
    header_text.append(" · POCKET: ", style="dim white")
    header_text.append("100%", style=f"bold {theme.blue}")
    header_text.append(" · NOTES: ", style="dim white")
    header_text.append("0 UNREAD", style=f"bold {theme.primary}")

    console.print(
        Panel(
            header_text,
            title=f"[bold {theme.primary}]⚓ DRAWBRIDGE INDUSTRIAL // OPERATIONAL HUB ⚓[/]",
            border_style=theme.secondary,
        )
    )


def render_mode_tabs(active_mode: str, theme: PaletteTheme) -> None:
    """Верхний таб-бар переключения режимов с яркой активной вкладкой."""
    modes = [
        ("DASH", "F1"),
        ("POCKET", "F2"),
        ("NOTES", "F3"),
        ("EXEC", "F4"),
        ("CONFIG", "F5"),
    ]
    bar = Text()
    bar.append(" [BRIDGE LOCAL] ", style=f"bold black on {theme.blue}")
    bar.append(" ")
    for i, (name, key) in enumerate(modes):
        if name == active_mode:
            bar.append(f" █ {key}:{name} ", style="bold white on #1F6FEB")
        else:
            bar.append(f" {key}:{name} ", style=f"dim {theme.secondary}")
        if i < len(modes) - 1:
            bar.append("│")
    console.print(Panel(bar, style=theme.secondary, expand=True))


def render_dashboard_mode(theme: PaletteTheme) -> None:
    """Режим 1: DASHBOARD / СТАТУС (F1)."""
    render_operational_header(theme)
    render_mode_tabs("DASH", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    left = Panel(
        f"""[bold white]ЛОКАЛЬНАЯ ШИНА СВЯЗИ (P2P BACKBONE)[/]
[bold {theme.blue}]ХОСТ: LINUX (Workstation)[/]
  |- IP: 192.168.1.104
  |- OS: Linux 6.13 (Arch Linux)
  +- Оператор: agy_cli (Antigravity Agent)

[bold {theme.purple}]УЗЕЛ: WIN-PC (Service Daemon)[/]
  |- IP: 192.168.1.150:41037
  |- Статус: [bold {theme.green}]ONLINE (Готов)[/]
  |- Heartbeat: 0.38 ms [bold {theme.green}][OK][/] (Лимит: 1500 ms)
  |- CPU: 2.4% | RAM: 14.2 / 64 GB
  +- Uptime: 4d 18h 32m""",
        title="[bold white][ СЕТЕВОЙ КАНАЛ ][/]",
        border_style=theme.secondary,
    )

    right = Panel(
        f"""[bold white]СОСТОЯНИЕ ХРАНИЛИЩА И ОЧЕРЕДЕЙ[/]
[bold {theme.amber}]КАРМАН (Pocket Storage Engine):[/]
  |- Путь: ~/.bridge_local/pocket/
  |- Файлов: 18 объектов (1.4 GB)
  |- FS Watchdog: [bold {theme.green}]АКТИВЕН[/] (0.5s debounce)
  +- Статус: [bold {theme.green}][OK] 100% SHA-256 MATCH[/]

[bold {theme.blue}]ЗАМЕТКИ (Notes Engine):[/]
  |- Файл: notes.jsonl
  |- Всего записей: 42
  +- Непрочитанных: [bold {theme.green}][0] (Все прочитаны)[/]""",
        title="[bold white][ ХРАНИЛИЩЕ И ОЧЕРЕДИ ][/]",
        border_style=theme.secondary,
    )

    grid.add_row(left, right)
    console.print(grid)
    console.print(
        "[dim]Горячие клавиши: [F1..F5] Режимы | [S] Sync | [N] Новая заметка | [Q] Выход[/dim]\n"
    )


def render_pocket_mode(theme: PaletteTheme) -> None:
    """Режим 2: POCKET / КАРМАН (F2) с индикатором процесса передачи."""
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
        "report_phase_04.docx",
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
    # Активный процесс с заметным индикатором передачи [>>>]
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
    console.print(
        "[dim]Горячие клавиши: [D] Drop | [S] Force Sync | [V] Verify SHA | [F1..F5] Режимы[/dim]\n"
    )


def render_notes_mode(theme: PaletteTheme) -> None:
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
  Интеграционные тесты ядра и RPC завершены успешно (146 тестов, 6.80с).
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
    console.print("[dim]Горячие клавиши: [Ctrl+N] Новая | [C] Очистить | [F1..F5] Режимы[/dim]\n")


def render_exec_mode(theme: PaletteTheme) -> None:
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
    console.print(
        "[dim]Горячие клавиши: [Enter] Выполнить | [Ctrl+L] Очистить | [F1..F5] Режимы[/dim]\n"
    )


def render_config_mode(theme: PaletteTheme) -> None:
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
        "192.168.1.150:41037",
        "1500 ms",
        f"[bold {theme.green}][ACTIVE] HMAC-SHA256[/]",
    )
    table.add_row(
        f"[dim {theme.secondary}]NODE-MACBOOK (future)[/]",
        "Mobile Node (mesh)",
        "192.168.1.112:41037",
        "3000 ms",
        f"[dim {theme.red}][OFFLINE][/]",
    )

    console.print(table)
    console.print(
        "[dim]Горячие клавиши: [A] Добавить | [E] Изменить | [T] Пинг | [F1..F5] Режимы[/dim]\n"
    )


# ===========================================================================
# 5. ДЕМОНСТРАЦИЯ МИНИМАЛЬНЫХ АНИМАЦИЙ (AT-A-GLANCE OBSERVABILITY)
# ===========================================================================


def demo_process_animations(theme: PaletteTheme) -> None:
    """Интерактивная демонстрация минимальных индикаторов активных процессов."""
    console.print(
        f"\n[bold {theme.primary}]⚡ ДЕМОНСТРАЦИЯ МИНИМАЛЬНЫХ АНИМАЦИЙ ПРОЦЕССОВ (AT-A-GLANCE)[/]"
    )
    console.print("[dim]Оператор видит с расстояния, идет ли передача/опрос:[/dim]\n")

    spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    pulses = [
        "[>    ]",
        "[>>   ]",
        "[>>>  ]",
        "[ >>>>]",
        "[  >>>]",
        "[   >>]",
        "[    >]",
    ]

    for step in range(14):
        s = spinners[step % len(spinners)]
        p = pulses[step % len(pulses)]

        line = Text()
        line.append(f"  [{s}] ", style=f"bold {theme.blue}")
        line.append("Pocket Sync: ", style="bold white")
        line.append("model_weights.bin ", style="dim white")
        line.append(f"{p} ", style=f"bold {theme.amber}")
        line.append(f"68% ({45 + (step % 5)} MB/s) ", style=f"bold {theme.blue}")
        line.append(" | Heartbeat probe: ", style="dim")
        line.append("0.38ms [OK] ", style=f"bold {theme.green}")

        sys.stdout.write("\r" + line.plain)
        sys.stdout.flush()
        time.sleep(0.10)

    sys.stdout.write("\n\n")
    sys.stdout.flush()


def render_theme_spec(theme: PaletteTheme) -> None:
    """Выводит спецификацию единой утвержденной темы."""
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


# ===========================================================================
# 6. ТОЧКА ВХОДА И ДИСПЕТЧЕР КОМАНД
# ===========================================================================


def resolve_args(argv: list[str]) -> str:
    """Парсит аргументы командной строки вида [mode]."""
    valid_modes = (
        "welcome",
        "neofetch",
        "modes",
        "industrial",
        "master",
        "anim",
        "theme",
        "spec",
        "all",
    )
    for a in argv:
        if a.lower() in valid_modes:
            return a.lower()
    return "all"


def main() -> None:
    mode = resolve_args(sys.argv[1:])
    theme = OFFICIAL_THEME

    sep = "═" * 70

    if mode in ("theme", "spec"):
        render_theme_spec(theme)
        return

    console.print(f"\n[bold {theme.primary}]◈ {theme.name.upper()} ◈[/]")
    console.print(f"[dim {theme.blue}]{theme.desc}[/]\n")

    if mode in ("all", "master"):
        console.print(f"[bold {theme.primary}]{sep}[/]")
        console.print(
            f"[bold {theme.primary}] 1. MASTER LOGO (BRIDGES) — ДЛЯ ПОЛНОЭКРАННОГО СТАРТА [/]"
        )
        console.print(f"[bold {theme.primary}]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_MASTER, style=f"bold {theme.primary}"),
                title=f"[bold {theme.primary}]◈ BRIDGES MASTER ◈[/]",
                subtitle=f"[dim {theme.blue}]STRAND NETWORK · LAN BACKBONE[/]",
                border_style=theme.secondary,
                expand=False,
            )
        )

    if mode in ("all", "industrial"):
        console.print(f"\n[bold {theme.secondary}]{sep}[/]")
        console.print(
            f"[bold {theme.secondary}] 2. INDUSTRIAL LOGO (DRAWBRIDGE) — ДЛЯ ОПЕРАТИВНЫХ ОКОН [/]"
        )
        console.print(f"[bold {theme.secondary}]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_INDUSTRIAL, style=f"bold {theme.secondary}"),
                title=f"[bold {theme.primary}]⚓ DRAWBRIDGE INDUSTRIAL ⚓[/]",
                subtitle="[dim white]BOTH STICK AND ROPE : TO PROTECT AND CONNECT[/]",
                border_style=theme.blue,
                expand=False,
            )
        )

    if mode in ("all", "welcome", "neofetch"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 3. ЭКРАН ПРИВЕТСТВИЯ В СТИЛЕ NEOFETCH (FULL SCREEN) [/]"
        )
        console.print(f"[bold white]{sep}[/]\n")
        render_welcome_screen(theme)

    if mode in ("all", "modes"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 4. ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (5 РЕЖИМОВ С ШАПКОЙ DRAWBRIDGE) [/]"
        )
        console.print(f"[bold white]{sep}[/]\n")
        render_dashboard_mode(theme)
        render_pocket_mode(theme)
        render_notes_mode(theme)
        render_exec_mode(theme)
        render_config_mode(theme)

    if mode in ("all", "anim"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 5. АНИМАЦИИ В РАБОЧИХ ПРОЦЕССАХ (AT-A-GLANCE) [/]")
        console.print(f"[bold white]{sep}[/]")
        demo_process_animations(theme)


if __name__ == "__main__":
    main()
