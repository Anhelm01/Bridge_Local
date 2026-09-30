r"""
ref/AI/ascii_preview.py — Интерактивный генератор и демонстратор логотипов
и TUI интерфейса Bridge Local.

Обновления по спецификации:
  1. Палитра из буфера обмена (ref/Hum/palette_clipboard.jpg):
     - Electric Magenta (#E6006A) — акцентные бейджи, фокус, подсветка логотипа.
     - Deep Cyber Teal (#027C7D) — сетевые линки, инфо-разделители, рамки узлов.
     - Crisp Titanium White (#FFFFFF) — основной текст, символы псевдографики.
     - Доступно переключение тем: --theme noir (по умолчанию) и --theme titanium.
  2. Ровно 2 утвержденных логотипа (без лишних мини-версий):
     - MASTER (BRIDGES Master): полноэкранный экран приветствия (Neofetch layout).
     - INDUSTRIAL (DRAWBRIDGE Industrial): оперативные рабочие окна и дашборд.
  3. Экран приветствия (Full-Screen Neofetch):
     - В полноэкранном режиме (ширина >= 120) выводит большой BRIDGES Master слева
       и подробную системную сводку Neofetch справа.
  4. Рабочий оперативный интерфейс (DASH, POCKET, NOTES, EXEC, CONFIG):
     - Полная очистка от лора Death Stranding (только реальные термины инжиниринга).
     - Полное отсутствие эмодзи и смайликов (только текстовые маркеры [OK], [BUSY]).
     - Шапка с эмблемой DRAWBRIDGE Industrial.
  5. Анимация фоновых процессов (At-a-Glance Observability):
     - Минимальные немерцающие индикаторы (braille spinners, transfer pulse) для
       мгновенного считывания состояния процессов без построчного чтения текста.
"""

from __future__ import annotations

import shutil
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ===========================================================================
# 1. ЦВЕТОВЫЕ ТЕМЫ (PALETTES)
# ===========================================================================


class Palette:
    """Палитра Cyber Noir из буфера обмена (ref/Hum/palette_clipboard.jpg)."""

    MAGENTA = "#E6006A"  # Electric Magenta (Внимание, фокус, активный статус)
    TEAL = "#027C7D"  # Deep Cyber Teal (Сеть, шина P2P, стабильность)
    WHITE = "#FFFFFF"  # Чистый белый (Текст, ключевые символы)
    MUTED = "#5C6370"  # Приглушенный серый (Второстепенные рамки)
    BORDER = "#027C7D"  # Основной цвет контуров панелей


class TitaniumPalette:
    """Альтернативная тема: Титановый монохром."""

    MAGENTA = "#E6EDF3"
    TEAL = "#ABB2BF"
    WHITE = "#FFFFFF"
    MUTED = "#5C6370"
    BORDER = "#ABB2BF"


# ===========================================================================
# 2. ДВА УТВЕРЖДЕННЫХ ЛОГОТИПА (MASTER И INDUSTRIAL)
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


def render_welcome_screen(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Выводит полноэкранный экран приветствия с большим BRIDGES Master и Neofetch-сводкой."""
    term_width, _ = shutil.get_terminal_size((120, 40))

    m = theme.MAGENTA
    t = theme.TEAL

    info = f"""[bold white]anhelm@workstation[/]
[dim {t}]─────────────────────────────────────────────────────────────[/]
[bold {t}]Host OS:[/]        Linux 6.13 (Arch Linux x86_64)
[bold {t}]Local Node:[/]     LINUX-HOST (192.168.1.104)
[bold {t}]Core Operator:[/]  agy_cli (Antigravity CLI Agent)

[bold {m}]Remote Node:[/]    WIN-PC (192.168.1.150:41037)
[bold {m}]Remote OS:[/]      Windows 11 Pro 64-bit (Build 26100)
[bold {m}]Remote Agent:[/]   BridgeLocalAgent [bold green][RUNNING][/]

[bold white]СВЯЗЬ И ПРОТОКОЛ (P2P BACKBONE)[/]
[dim {t}]─────────────────────────────────────────────────────────────[/]
[bold {t}]Канал связи:[/]    P2P Direct LAN (1.0 Gbps Full Duplex)
[bold {t}]Пинг (Latency):[/]  0.38 ms [bold green][STABLE LAN · OK][/]
[bold {t}]Безопасность:[/]    HMAC-SHA256 Challenge-Response Session
[bold {t}]Транспорт:[/]       JSON-RPC 2.0 / Length-Prefix Wire Framing
[bold {t}]Fail-Fast:[/]       1500 ms (Мгновенное обнаружение обрыва)

[bold white]ХРАНИЛИЩЕ И ОЧЕРЕДИ[/]
[dim {t}]─────────────────────────────────────────────────────────────[/]
[bold {m}]Карман (Pocket):[/] ~/.bridge_local/pocket/
[bold {m}]Файлов в кармане:[/] 18 объектов (1.4 GB) [bold green][100% SHA-256 MATCH][/]
[bold {m}]Заметки (Notes):[/] 42 записи [bold green][0 непрочитанных][/]

[bold white]РЕЖИМЫ РАБОТЫ (MODES)[/]
[dim {t}]─────────────────────────────────────────────────────────────[/]
  [bold {m}][F1][/] Дашборд   [bold {m}][F2][/] Карман   [bold {m}][F3][/] Заметки
  [bold {m}][F4][/] Exec      [bold {m}][F5][/] Конфиг   [bold {m}][Q][/]  Выход
"""

    logo_text = Text(BRIDGES_MASTER, style=f"bold {theme.MAGENTA}")
    logo_panel = Panel(
        logo_text,
        title=f"[bold {theme.MAGENTA}]◈ BRIDGES MASTER EMBLEM ◈[/]",
        subtitle=f"[dim {theme.TEAL}]STRAND NETWORK · LAN BACKBONE[/]",
        border_style=theme.TEAL,
    )
    info_panel = Panel(
        info,
        title="[bold white][ СИСТЕМНЫЙ СТАТУС / NEOFETCH ][/]",
        subtitle="[dim green]● SYSTEM LINK OPERATIONAL[/]",
        border_style=theme.TEAL,
    )

    # Если терминал достаточно широкий (полный экран >= 120 колонок) — 2 колонки
    if term_width >= 120:
        grid = Table.grid(expand=True)
        grid.add_column(width=63)
        grid.add_column(ratio=1)
        grid.add_row(logo_panel, info_panel)
        console.print(grid)
    else:
        # Для узких терминалов — вертикальное расположение
        console.print(logo_panel)
        console.print(info_panel)


# ===========================================================================
# 4. РАБОЧИЙ ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (DRAWBRIDGE INDUSTRIAL)
# ===========================================================================


def render_operational_header(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Шапка оперативного окна с логотипом DRAWBRIDGE Industrial."""
    console.print(
        Panel(
            Text(DRAWBRIDGE_HEADER, style=f"bold {theme.TEAL}"),
            title=f"[bold {theme.MAGENTA}]⚓ DRAWBRIDGE INDUSTRIAL // OPERATIONAL HUB ⚓[/]",
            border_style=theme.MAGENTA,
        )
    )


def render_mode_tabs(
    active_mode: str, theme: type[Palette] | type[TitaniumPalette] = Palette
) -> None:
    """Верхний таб-бар переключения режимов (без эмодзи, в 1 строку)."""
    modes = [
        ("DASH", "F1"),
        ("POCKET", "F2"),
        ("NOTES", "F3"),
        ("EXEC", "F4"),
        ("CONFIG", "F5"),
    ]
    bar = Text()
    bar.append(" [BRIDGE LOCAL] ", style=f"bold black on {theme.MAGENTA}")
    bar.append(" ")
    for i, (name, key) in enumerate(modes):
        if name == active_mode:
            bar.append(f" █ {key}:{name} ", style="bold white on #282C34")
        else:
            bar.append(f" {key}:{name} ", style=f"dim {theme.TEAL}")
        if i < len(modes) - 1:
            bar.append("│")
    console.print(Panel(bar, style=theme.TEAL, expand=True))


def render_dashboard_mode(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Режим 1: DASHBOARD / СТАТУС (F1)."""
    render_operational_header(theme)
    render_mode_tabs("DASH", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    left = Panel(
        f"""[bold white]ЛОКАЛЬНАЯ ШИНА СВЯЗИ (P2P BACKBONE)[/]
[bold {theme.TEAL}]ХОСТ: LINUX (Workstation)[/]
  |- IP: 192.168.1.104
  |- OS: Linux 6.13 (Arch Linux)
  +- Оператор: agy_cli (Antigravity Agent)

[bold {theme.MAGENTA}]УЗЕЛ: WIN-PC (Service Daemon)[/]
  |- IP: 192.168.1.150:41037
  |- Статус: [bold green]ONLINE (Готов)[/]
  |- Heartbeat: 0.38 ms [green][OK][/] (Лимит: 1500 ms)
  |- CPU: 2.4% | RAM: 14.2 / 64 GB
  +- Uptime: 4d 18h 32m""",
        title="[bold white][ СЕТЕВОЙ КАНАЛ ][/]",
        border_style=theme.TEAL,
    )

    right = Panel(
        """[bold white]СОСТОЯНИЕ ХРАНИЛИЩА И ОЧЕРЕДЕЙ[/]
[bold yellow]КАРМАН (Pocket Storage Engine):[/]
  |- Путь: ~/.bridge_local/pocket/
  |- Файлов: 18 объектов (1.4 GB)
  |- FS Watchdog: [green]АКТИВЕН[/] (0.5s debounce)
  +- Статус: [bold green][OK] 100% SHA-256 MATCH[/]

[bold cyan]ЗАМЕТКИ (Notes Engine):[/]
  |- Файл: notes.jsonl
  |- Всего записей: 42
  +- Непрочитанных: [bold green][0] (Все прочитаны)[/]""",
        title="[bold white][ ХРАНИЛИЩЕ И ОЧЕРЕДИ ][/]",
        border_style=theme.TEAL,
    )

    grid.add_row(left, right)
    console.print(grid)
    console.print(
        "[dim]Горячие клавиши: [F1..F5] Режимы | [S] Sync | [N] Новая заметка | [Q] Выход[/dim]\n"
    )


def render_pocket_mode(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Режим 2: POCKET / КАРМАН (F2) с индикатором процесса передачи."""
    render_operational_header(theme)
    render_mode_tabs("POCKET", theme)

    table = Table(
        title="[ ХРАНИЛИЩЕ КАРМАНА / POCKET STORAGE (~/.bridge_local/pocket/) ]", expand=True
    )
    table.add_column("Файл / Каталог", style="bold white")
    table.add_column("Размер", style="cyan", justify="right")
    table.add_column("Направление", style="yellow", justify="center")
    table.add_column("SHA-256", style="bold green", justify="center")
    table.add_column("Активность / Статус", style=f"bold {theme.MAGENTA}")

    table.add_row(
        "report_phase_04.docx", "2.4 MB", "LNX --> WIN", "[OK] d9e4f1a...", "[green]SYNCED[/]"
    )
    table.add_row(
        "setup_env_win.ps1", "12.8 KB", "WIN --> LNX", "[OK] 3a7c88b...", "[green]SYNCED[/]"
    )
    # Активный процесс с заметным индикатором передачи [>>>]
    table.add_row(
        "model_weights.bin",
        "1.2 GB",
        "LNX --> WIN",
        "[yellow][⠋ SYNC][/]",
        f"[bold {theme.MAGENTA}][>>> 68%][/] [yellow]48 MB/s[/]",
    )
    table.add_row(
        "screenshot_crash.png", "840 KB", "WIN --> LNX", "[OK] f7a012c...", "[green]SYNCED[/]"
    )

    console.print(table)
    console.print(
        "[dim]Горячие клавиши: [D] Drop | [S] Force Sync | [V] Verify SHA | [F1..F5] Режимы[/dim]\n"
    )


def render_notes_mode(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Режим 3: NOTES / ЗАМЕТКИ (F3)."""
    render_operational_header(theme)
    render_mode_tabs("NOTES", theme)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=1)

    notes_feed = Panel(
        f"""[bold {theme.TEAL}][10:04:15] WIN-PC (Windows Operator):[/]
  Служба BridgeLocalAgent запущена в фоне, кодировка UTF-8 (chcp 65001) проверена.

[bold {theme.MAGENTA}][10:08:22] LINUX (Antigravity agy_cli):[/]
  Интеграционные тесты ядра и RPC завершены успешно (146 тестов, 6.80с).
  Подготовлена передача весов модели через карман.

[bold white][10:11:03] USER (Operator Note):[/]
  Проверь температуру GPU на Windows перед запуском бенчмарка.

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод новой заметки ([Enter] Отправить на все узлы | [Esc] Отмена):[/]
[bold {theme.MAGENTA}]> [/][blink]_[/]""",
        title="[bold white][ ЖУРНАЛ ЗАМЕТОК / NOTES STREAM ][/]",
        border_style=theme.TEAL,
    )

    stats = Panel(
        """[bold white]СТАТИСТИКА ЗАМЕТОК[/]
|- Всего записей: 43
|- Непрочитанных: [bold green][0][/]
|- Файл: [dim]notes.jsonl[/]
+- Режим: [green]Append-Only (Atomic)[/]

[bold yellow]ФИЛЬТРЫ:[/][dim]
 [A] Все заметки
 [U] Только новые
 [S] Поиск по тексту[/dim]""",
        title="[bold white][ ИНФО / СТАТИСТИКА ][/]",
        border_style=theme.TEAL,
    )

    grid.add_row(notes_feed, stats)
    console.print(grid)
    console.print("[dim]Горячие клавиши: [Ctrl+N] Новая | [C] Очистить | [F1..F5] Режимы[/dim]\n")


def render_exec_mode(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Режим 4: REMOTE EXEC / КОНСОЛЬ (F4)."""
    render_operational_header(theme)
    render_mode_tabs("EXEC", theme)

    console.print(
        Panel(
            f"""[bold white]УДАЛЕННАЯ СЕССИЯ POWERSHELL (WIN-PC)[/]
Кодировка: UTF-8 (chcp 65001) | Права: Elevated (Admin) | Таймаут: 30s
Статус раннера: [bold green][READY][/] | Фоновый опрос: [bold {theme.MAGENTA}][⠼ IDLE][/]

[bold {theme.TEAL}]PS C:\\BridgeService> [/][white]Get-Service -Name "BridgeLocalAgent"[/]

Status   Name               DisplayName
------   ----               -----------
[bold green]Running[/]  BridgeLocalAgent   Bridge Local Windows Daemon v0.4.0

[bold {theme.TEAL}]PS C:\\BridgeService> [/][white]Get-Process python | Select Id, WS[/]

   Id        CPU       WS
   --        ---       --
 4912   1.421875 42811392

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод команды ([Enter] Выполнить на WIN-PC | [Ctrl+C] Прервать):[/]
[bold {theme.MAGENTA}]PS C:\\BridgeService> [/] [blink]_[/]""",
            title="[bold white][ УДАЛЕННЫЙ ИСПОЛНИТЕЛЬ POWERSHELL / REMOTE EXEC ][/]",
            border_style=theme.TEAL,
        )
    )
    console.print(
        "[dim]Горячие клавиши: [Enter] Выполнить | [Ctrl+L] Очистить | [F1..F5] Режимы[/dim]\n"
    )


def render_config_mode(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Режим 5: CONFIG / УЗЛЫ (F5)."""
    render_operational_header(theme)
    render_mode_tabs("CONFIG", theme)

    table = Table(title="[ РЕЕСТР УЗЛОВ И СЕТЕВЫЕ ПАРАМЕТРЫ / NODE CONFIG ]", expand=True)
    table.add_column("Узел (Node ID)", style="bold white")
    table.add_column("Роль / Назначение", style="cyan")
    table.add_column("Сетевой Адрес", style="yellow")
    table.add_column("Heartbeat", style="white")
    table.add_column("Безопасность", style="bold green")

    table.add_row(
        "LINUX-HOST (local)",
        "Workstation (Core)",
        "127.0.0.1 / 192.168.1.104",
        "1500 ms",
        "[ACTIVE] HMAC-SHA256",
    )
    table.add_row(
        "WIN-PC (remote)",
        "Worker Agent",
        "192.168.1.150:41037",
        "1500 ms",
        "[ACTIVE] HMAC-SHA256",
    )
    table.add_row(
        "NODE-MACBOOK (future)",
        "Mobile Node (mesh)",
        "192.168.1.112:41037",
        "3000 ms",
        "[dim][OFFLINE][/dim]",
    )

    console.print(table)
    console.print(
        "[dim]Горячие клавиши: [A] Добавить | [E] Изменить | [T] Пинг | [F1..F5] Режимы[/dim]\n"
    )


# ===========================================================================
# 5. ДЕМОНСТРАЦИЯ МИНИМАЛЬНЫХ АНИМАЦИЙ (AT-A-GLANCE OBSERVABILITY)
# ===========================================================================


def demo_process_animations(theme: type[Palette] | type[TitaniumPalette] = Palette) -> None:
    """Интерактивная демонстрация минимальных индикаторов активных процессов."""
    console.print(
        f"\n[bold {theme.MAGENTA}]⚡ ДЕМОНСТРАЦИЯ МИНИМАЛЬНЫХ АНИМАЦИЙ ПРОЦЕССОВ (AT-A-GLANCE)[/]"
    )
    console.print(
        "[dim]Оператор видит с расстояния, идет ли передача/опрос, без чтения текста строк:[/dim]\n"
    )

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

    for step in range(12):
        s = spinners[step % len(spinners)]
        p = pulses[step % len(pulses)]

        line = Text()
        line.append(f"  [{s}] ", style=f"bold {theme.MAGENTA}")
        line.append("Pocket Sync: ", style="bold white")
        line.append("model_weights.bin ", style="cyan")
        line.append(f"{p} ", style=f"bold {theme.MAGENTA}")
        line.append(f"68% ({45 + (step % 5)} MB/s) ", style="yellow")
        line.append(" | Heartbeat probe: ", style="dim")
        line.append("0.38ms [OK] ", style="green")

        # Перезаписываем строку в терминале
        sys.stdout.write("\r" + line.plain)
        sys.stdout.flush()
        time.sleep(0.12)

    sys.stdout.write("\n\n")
    sys.stdout.flush()


# ===========================================================================
# 6. ТОЧКА ВХОДА И ДИСПЕТЧЕР КОМАНД
# ===========================================================================


def main() -> None:
    args = [a.lower() for a in sys.argv[1:]]

    # Выбор темы:
    theme = TitaniumPalette if "--theme=titanium" in args or "titanium" in args else Palette

    mode = "all"
    for a in args:
        if a in ("welcome", "neofetch", "modes", "industrial", "master", "anim", "all"):
            mode = a
            break

    sep = "═" * 70

    if mode in ("all", "master"):
        console.print(f"\n[bold {theme.MAGENTA}]{sep}[/]")
        console.print(
            f"[bold {theme.MAGENTA}] 1. MASTER LOGO (BRIDGES) — ДЛЯ ПОЛНОЭКРАННОГО СТАРТА [/]"
        )
        console.print(f"[bold {theme.MAGENTA}]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_MASTER, style=f"bold {theme.MAGENTA}"),
                title=f"[bold {theme.MAGENTA}]◈ BRIDGES MASTER ◈[/]",
                subtitle=f"[dim {theme.TEAL}]STRAND NETWORK · LAN BACKBONE[/]",
                border_style=theme.TEAL,
                expand=False,
            )
        )

    if mode in ("all", "industrial"):
        console.print(f"\n[bold {theme.TEAL}]{sep}[/]")
        console.print(
            f"[bold {theme.TEAL}] 2. INDUSTRIAL LOGO (DRAWBRIDGE) — ДЛЯ ОПЕРАТИВНЫХ ОКОН [/]"
        )
        console.print(f"[bold {theme.TEAL}]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_INDUSTRIAL, style=f"bold {theme.TEAL}"),
                title=f"[bold {theme.MAGENTA}]⚓ DRAWBRIDGE INDUSTRIAL ⚓[/]",
                subtitle="[dim white]BOTH STICK AND ROPE : TO PROTECT AND CONNECT[/]",
                border_style=theme.MAGENTA,
                expand=False,
            )
        )

    if mode in ("all", "welcome", "neofetch"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 3. ЭКРАН ПРИВЕТСТВИЯ В СТИЛЕ NEOFETCH (FULL SCREEN) [/]")
        console.print(f"[bold white]{sep}[/]\n")
        render_welcome_screen(theme)

    if mode in ("all", "modes"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 4. ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (5 РЕЖИМОВ С ШАПКОЙ DRAWBRIDGE) [/]")
        console.print(f"[bold white]{sep}[/]\n")
        render_dashboard_mode(theme)
        render_pocket_mode(theme)
        render_notes_mode(theme)
        render_exec_mode(theme)
        render_config_mode(theme)

    if mode in ("all", "anim"):
        demo_process_animations(theme)


if __name__ == "__main__":
    main()
