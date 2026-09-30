r"""
ref/AI/ascii_preview.py — Интерактивный генератор и демонстратор логотипов
и TUI интерфейса Bridge Local.

Обновления по спецификации пользователя:
  1. Цветовая палитра: Титановый монохром (Titanium Silver / Slate) для всех логотипов
     (бывший янтарный ромб переведен в титан).
  2. Два формата логотипа:
     - БОЛЬШОЙ: для экрана приветствия и системной сводки (Neofetch layout).
     - МИНИ: для оперативных окон и верхнего HUD.
     - Варианты 1 (Bridges) и 3 (Drawbridge) выполнены в единой титановой палитре.
  3. Звездочки '★' удалены со всех логотипов (заменены на строгие маркеры [#] / [◇]).
  4. Рабочий оперативный интерфейс (DASH, POCKET, NOTES, EXEC, CONFIG):
     - Полностью очищен от терминологии Death Stranding (только реальные термины:
       P2P LAN Backbone, Pocket Storage, Notes Engine, PowerShell Exec, Node Registry).
     - Смайлики и эмодзи полностью удалены (заменены на текстовые маркеры [OK], [NET] и т.д.).
     - Лор и девизы Death Stranding сохранены исключительно в логотипах.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(width=80)

# ===========================================================================
# 1. БОЛЬШОЙ ЛОГОТИП (ДЛЯ ЭКРАНА ПРИВЕТСТВИЯ / NEOFETCH)
# Стиль: Титановый монохром (#E6EDF3 / #ABB2BF), без звездочек ★
# ===========================================================================

# Вариант 1: BRIDGES MASTER TITANIUM (Ромб, пилоны моста, перспективная паутина)
BRIDGES_BIG_TITANIUM = r"""
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

# Вариант 3: DRAWBRIDGE INDUSTRIAL TITANIUM (Разводной мост, фермы, без звездочек)
DRAWBRIDGE_BIG_TITANIUM = r"""
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

# ===========================================================================
# 2. МАЛЫЙ ЛОГОТИП (ДЛЯ ОПЕРАТИВНЫХ ОКОН / HUD)
# Стиль: Тот же титановый монохром (#E6EDF3), компактный формат
# ===========================================================================

# Вариант А: BRIDGES Плотный ромб (5 строк)
MINI_BRIDGES_TITANIUM = r"""     .:/XXXXXX\:.      BRIDGE LOCAL v0.4.0
   .:+HMM@@@@@@MMH+:.  /// STRAND NETWORK
  <==================> [HOST: LINUX ◄════► NODE: WIN64]
   ':+HMM\|/\|/MMH+:'  STATUS: ONLINE (0.28ms) · POCKET: 100%
     ':/XXXXXX\:'      FAIL-FAST: 1500ms · NOTES: 0 UNREAD"""

# Вариант Б: BRIDGES Геометрические ванты (4 строки)
MINI_BRIDGES_GEOMETRIC = r"""      ▲═══\═══▲        BRIDGE LOCAL v0.4.0  [P2P LAN BACKBONE]
    .[#]═══|═══[#].    [LNX: 192.168.1.104 ◄════► WIN: 192.168.1.150]
     \    \|/    /     STATUS: 0.38ms [OK] · POCKET: SYNCED · NOTES: OK
      '---'v'---'      FAIL-FAST: 1500ms · HMAC-SHA256: ACTIVE"""

# Вариант В: DRAWBRIDGE Разводной мост мини (4 строки)
MINI_DRAWBRIDGE_TITANIUM = r"""      .▄█ ││ █▄.       D R A W B R I D G E  v0.4.0
     [X]█ ││ █[X]      /// BOTH STICK AND ROPE
     (o)═╝││╚═(o)      [LNX: 192.168.1.104 ◄════► WIN: 192.168.1.150]
      ▲ ╩════╩ ▲       STATUS: 0.38ms [OK] · P2P BACKBONE"""

# ===========================================================================
# 3. ЭКРАН ПРИВЕТСТВИЯ (В СТИЛЕ NEOFETCH)
# Большой логотип слева + системная сводка справа
# ===========================================================================

NEOFETCH_LOGO = r"""       .::[#]::.
   .:/XXXXXXXXXX\:.
.:+HMM@@@@@@@@@@MMH+:.
 =XMM@##[#  #]##@MMX=
  \XMM@#      #@MMX/
   \XMM@# /\ #@MMX/
 ╔══════════════════╗
 ║  B R I D G E S   ║
 ║  LOCAL · STRAND  ║
 ╚══════════════════╝
   /XMM@# \/ #@MMX\
  /XMM@#  ||  #@MMX\
 =XMM@##--++--##@MMX=
':+HMM@@@@@@@@@@MMH+:'
   ':\XXXXXXXXXX/:'
       '::[v]::'"""


def render_neofetch_welcome() -> None:
    """Выводит стартовый экран приветствия в стиле Neofetch."""
    info = """[bold white]anhelm@workstation[/]
------------------
[bold #61AFEF]OS:[/] Linux 6.13 (Arch Linux)
[bold #61AFEF]Host:[/] LINUX-HOST (192.168.1.104)
[bold #61AFEF]Agent:[/] agy_cli (Antigravity Operator)
[bold #98C379]Remote Node:[/] WIN-PC (192.168.1.150:41037)
[bold #98C379]Remote OS:[/] Windows 11 Pro 64-bit
[bold #98C379]Remote Agent:[/] BridgeLocalAgent (WinService)
[bold yellow]Link Latency:[/] 0.38 ms [bold green][STABLE LAN][/]
[bold yellow]Pocket Storage:[/] ~/.bridge_local/pocket/ (1.4 GB / 18 files)
[bold yellow]Notes Feed:[/] 42 records (0 unread)
[bold yellow]Security:[/] HMAC-SHA256 authenticated session
[bold #E5C07B]Protocol:[/] JSON-RPC 2.0 / Length-Prefix Wire Framing

[dim]Режимы (Modes):[/]
  [F1] Дашборд   [F2] Карман   [F3] Заметки
  [F4] Exec      [F5] Конфиг   [Q]  Выход"""

    grid = Table.grid(expand=True)
    grid.add_column(width=28)
    grid.add_column(ratio=1)

    grid.add_row(
        Panel(Text(NEOFETCH_LOGO, style="bold #E6EDF3"), border_style="#5C6370"),
        Panel(info, title="[bold white][ СИСТЕМНЫЙ СТАТУС / NEOFETCH ][/]", border_style="#5C6370"),
    )
    console.print(grid)


# ===========================================================================
# 4. РАБОЧИЙ ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (MODES)
# Строгий стиль: без лора Death Stranding, без смайликов и эмодзи
# ===========================================================================


def render_operational_header() -> None:
    """Компактная шапка с малым логотипом для рабочих окон."""
    console.print(Panel(Text(MINI_BRIDGES_GEOMETRIC, style="bold #E6EDF3"), border_style="#5C6370"))


def render_mode_tabs(active_mode: str) -> None:
    """Верхняя панель переключения режимов (Tab Bar в 1 строку без эмодзи)."""
    modes = [
        ("DASH", "F1"),
        ("POCKET", "F2"),
        ("NOTES", "F3"),
        ("EXEC", "F4"),
        ("CONFIG", "F5"),
    ]
    bar = Text()
    bar.append(" [BRIDGE LOCAL] ", style="bold white on #1E222A")
    bar.append(" ")
    for i, (name, key) in enumerate(modes):
        if name == active_mode:
            bar.append(f" █ {key}:{name} ", style="bold white on #3A3F4B")
        else:
            bar.append(f" {key}:{name} ", style="dim #ABB2BF")
        if i < len(modes) - 1:
            bar.append("│")
    console.print(Panel(bar, style="#3E4451", expand=True))


def render_dashboard_mode() -> None:
    """Режим 1: DASHBOARD / СТАТУС (F1)."""
    render_operational_header()
    render_mode_tabs("DASH")

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    left = Panel(
        """[bold white]ЛОКАЛЬНАЯ ШИНА СВЯЗИ (P2P BACKBONE)[/]
[bold #61AFEF]ХОСТ: LINUX (Workstation)[/]
  |- IP: 192.168.1.104
  |- OS: Linux 6.13 (Arch Linux)
  +- Оператор: agy_cli (Antigravity Agent)

[bold #98C379]УЗЕЛ: WIN-PC (Service Daemon)[/]
  |- IP: 192.168.1.150:41037
  |- Статус: [bold green]ONLINE (Готов)[/]
  |- Heartbeat: 0.38 ms [green][OK][/] (Лимит: 1500 ms)
  |- CPU: 2.4% | RAM: 14.2 / 64 GB
  +- Uptime: 4d 18h 32m""",
        title="[bold white][ СЕТЕВОЙ КАНАЛ ][/]",
        border_style="#5C6370",
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
        border_style="#5C6370",
    )

    grid.add_row(left, right)
    console.print(grid)
    console.print(
        "[dim]Горячие клавиши: [F1..F5] Режимы | [S] Sync | [N] Новая заметка | [Q] Выход[/dim]\n"
    )


def render_pocket_mode() -> None:
    """Режим 2: POCKET / КАРМАН (F2)."""
    render_mode_tabs("POCKET")
    table = Table(
        title="[ ХРАНИЛИЩЕ КАРМАНА / POCKET STORAGE (~/.bridge_local/pocket/) ]", expand=True
    )
    table.add_column("Файл / Каталог", style="bold white")
    table.add_column("Размер", style="cyan", justify="right")
    table.add_column("Направление", style="yellow", justify="center")
    table.add_column("SHA-256", style="bold green", justify="center")
    table.add_column("Статус", style="green")

    table.add_row("report_phase_04.docx", "2.4 MB", "LNX --> WIN", "[OK] d9e4f1a...", "SYNCED")
    table.add_row("setup_env_win.ps1", "12.8 KB", "WIN --> LNX", "[OK] 3a7c88b...", "SYNCED")
    table.add_row(
        "model_weights.bin",
        "1.2 GB",
        "LNX --> WIN",
        "[yellow][BUSY 68%][/]",
        "[bold yellow]TRANSFERRING (48 MB/s)[/]",
    )
    table.add_row("screenshot_crash.png", "840 KB", "WIN --> LNX", "[OK] f7a012c...", "SYNCED")

    console.print(table)
    console.print(
        "[dim]Горячие клавиши: [D] Drop | [S] Sync | [V] Verify SHA | [F1..F5] Режимы[/dim]\n"
    )


def render_notes_mode() -> None:
    """Режим 3: NOTES / ЗАМЕТКИ (F3)."""
    render_mode_tabs("NOTES")
    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=1)

    notes_feed = Panel(
        """[bold #61AFEF][10:04:15] WIN-PC (Windows Operator):[/]
  Служба BridgeLocalAgent запущена в фоне, кодировка UTF-8 (chcp 65001) проверена.

[bold #98C379][10:08:22] LINUX (Antigravity agy_cli):[/]
  Интеграционные тесты ядра и RPC завершены успешно (146 тестов, 6.80с).
  Подготовлена передача весов модели через карман.

[bold #F5A623][10:11:03] USER (Operator Note):[/]
  Проверь температуру GPU на Windows перед запуском бенчмарка.

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод новой заметки ([Enter] Отправить на все узлы | [Esc] Отмена):[/]
[bold cyan]> [/][blink]_[/]""",
        title="[bold white][ ЖУРНАЛ ЗАМЕТОК / NOTES STREAM ][/]",
        border_style="#5C6370",
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
        border_style="#5C6370",
    )

    grid.add_row(notes_feed, stats)
    console.print(grid)
    console.print("[dim]Горячие клавиши: [Ctrl+N] Новая | [C] Очистить | [F1..F5] Режимы[/dim]\n")


def render_exec_mode() -> None:
    """Режим 4: REMOTE EXEC / КОНСОЛЬ (F4)."""
    render_mode_tabs("EXEC")

    console.print(
        Panel(
            """[bold white]УДАЛЕННАЯ СЕССИЯ POWERSHELL (WIN-PC)[/]
Кодировка: UTF-8 (chcp 65001) | Права: Elevated (Admin) | Таймаут: 30s

[bold #61AFEF]PS C:\\BridgeService> [/][white]Get-Service -Name "BridgeLocalAgent"[/]

Status   Name               DisplayName
------   ----               -----------
[bold green]Running[/]  BridgeLocalAgent   Bridge Local Windows Daemon v0.4.0

[bold #61AFEF]PS C:\\BridgeService> [/][white]Get-Process -Name "python" | Select Id, CPU, WS[/]

   Id        CPU       WS
   --        ---       --
 4912   1.421875 42811392

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold yellow]Ввод команды ([Enter] Выполнить на WIN-PC | [Ctrl+C] Прервать):[/]
[bold white]PS C:\\BridgeService> [/] [blink]_[/]""",
            title="[bold white][ УДАЛЕННЫЙ ИСПОЛНИТЕЛЬ POWERSHELL / REMOTE EXEC ][/]",
            border_style="#5C6370",
        )
    )
    console.print(
        "[dim]Горячие клавиши: [Enter] Выполнить | [Ctrl+L] Очистить | [F1..F5] Режимы[/dim]\n"
    )


def render_config_mode() -> None:
    """Режим 5: CONFIG / УЗЛЫ (F5)."""
    render_mode_tabs("CONFIG")
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
# 5. ТОЧКА ВХОДА И ДИСПЕТЧЕР
# ===========================================================================


def main() -> None:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    sep = "═" * 70

    if arg in ("all", "big"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 1. БОЛЬШОЙ ЛОГОТИП — BRIDGES MASTER (ТИТАНОВЫЙ МОНОХРОМ) [/]")
        console.print(f"[bold white]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_BIG_TITANIUM, style="bold #E6EDF3"),
                title="[bold white]◈ BRIDGES // LOCAL NODE PROTOCOL ◈[/]",
                subtitle="[dim white]STRAND NETWORK · LAN UMBILICAL[/]",
                border_style="#ABB2BF",
                expand=False,
            )
        )

        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 2. БОЛЬШОЙ ЛОГОТИП — DRAWBRIDGE INDUSTRIAL (ТИТАНОВЫЙ МОНОХРОМ) [/]"
        )
        console.print(f"[bold white]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_BIG_TITANIUM, style="bold #E6EDF3"),
                title="[bold white]⚓ DRAWBRIDGE // SECURE LOCAL BASCULE ⚓[/]",
                subtitle="[dim white]BOTH STICK AND ROPE : LINUX ↔ WIN64[/]",
                border_style="#ABB2BF",
                expand=False,
            )
        )

    if arg in ("all", "mini"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 3. МАЛЫЕ ЛОГОТИПЫ ДЛЯ ОПЕРАТИВНЫХ ОКОН / HUD [/]")
        console.print(f"[bold white]{sep}[/]\n")
        console.print("[bold #ABB2BF]Вариант А: BRIDGES Плотный ромб[/]")
        console.print(
            Panel(Text(MINI_BRIDGES_TITANIUM, style="bold #E6EDF3"), border_style="#5C6370")
        )
        console.print("[bold #ABB2BF]Вариант Б: BRIDGES Геометрические ванты[/]")
        console.print(
            Panel(Text(MINI_BRIDGES_GEOMETRIC, style="bold #E6EDF3"), border_style="#5C6370")
        )
        console.print("[bold #ABB2BF]Вариант В: DRAWBRIDGE Разводной мост мини[/]")
        console.print(
            Panel(Text(MINI_DRAWBRIDGE_TITANIUM, style="bold #E6EDF3"), border_style="#5C6370")
        )

    if arg in ("all", "welcome", "neofetch"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print("[bold white] 4. ЭКРАН ПРИВЕТСТВИЯ В СТИЛЕ NEOFETCH [/]")
        console.print(f"[bold white]{sep}[/]\n")
        render_neofetch_welcome()

    if arg in ("all", "modes"):
        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 5. РАБОЧИЙ ОПЕРАТИВНЫЙ ИНТЕРФЕЙС (5 РЕЖИМОВ БЕЗ ЭМОДЗИ И ЛОРА DS) [/]"
        )
        console.print(f"[bold white]{sep}[/]\n")
        render_dashboard_mode()
        render_pocket_mode()
        render_notes_mode()
        render_exec_mode()
        render_config_mode()


if __name__ == "__main__":
    main()
