r"""
ref/AI/ascii_preview.py — Генератор и демонстратор ASCII-логотипов
и концептов TUI интерфейса Bridge Local по референсам из ref/Hum/.

Референсы:
  - photo_2026-09-30_10-01-41.jpg: Логотип BRIDGES (DS1 — ромб, звезды, паутина-ванты)
  - photo_2026-09-30_10-01-48.jpg: Логотип DRAWBRIDGE (DS2 — полукруг, разводные пролеты, фермы)
  - photo_2026-09-30_10-01-45.jpg: Стиль 1 — Монохром (. , - : ; [ ] u 8 d N M ^ @ P \)
  - photo_2026-09-30_10-01-50.jpg: Стиль 2 — Янтарный CRT-терминал (. , - : ; / = + % $ # X H M @)
  - intCli.txt: Архитектура TUI с делением на "modes" (DASHBOARD, POCKET, NOTES, EXEC, CONFIG)
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(width=80)

# ===========================================================================
# 1. ЛОГОТИП BRIDGES: ЯНТАРНАЯ CRT-ПЛОТНОСТЬ (Ref 1 + Ref 4)
# ===========================================================================
BRIDGES_AMBER_MASTER = r"""
                           .::.
                       .:/XXXXXX\:.
                    .:+HMM@@@@@@MMH+:.
                  . =XMM@##[★ ★]##@MMX= .
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
║  [★ ★]     B  R  I  D  G  E    L  O  C  A  L     [★ ★]  ║
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

# ===========================================================================
# 2. ЛОГОТИП BRIDGES: МОНОХРОМНАЯ ПЛОТНОСТЬ ТИТАНА (Ref 1 + Ref 2)
# ===========================================================================
BRIDGES_TITANIUM_MONO = r"""
                        ..:: [★ ★] ::..
                     .:[u8NNMMMMMMNN8u]:.
                   .:[dMM@@@@@@@@@@@@MMb]:.
                 .:uNMM#::..      ..::#MMNu:.
               .:dMM@/.    /|    |\    .\@MMb:.
             .:uMM@/      / | /\ | \      \@MMu:.
          ..::[dMM@/     |  |/  \|  |     \@MMb]::..
        .:[u8NNMM@/      |  | || |  |      \@MMNN8u]:.
      .:[dMM@@@MM@/      |  |/  \|  |      \@MM@@@MMb]:.
    .:uNMM#::#@MM@/      |__|/__\|__|      \@MM@#::#MMNu:.
  .:dMM@/.  .\@MM@/                      .\@MM@/.  .\@MMb:.
.:[dMM@/     .\@MM@X====================XMM@/.      \@MMb]:.
╔══════════════════════════════════════════════════════════╗
║  [★ ★]      B  R  I  D  G  E    L  O  C  A  L     [★ ★]  ║
║          ///   S T R A N D   N E T W O R K   ///         ║
╚══════════════════════════════════════════════════════════╝
':dMM@\      ./@MM@X====================XMM@\.      /@MMb:'
  ':uNMM#::#@MM@/   \    \    |    /    /  \@MM@#::#MMNu:'
    ':[dMM@@@MM@/    \    \   |   /    /    \@MM@@@MMb]:'
      .:[u8NNMM@/---\---\--\--+--/--/---/---\@MMNN8u]:.
        ''::[dMM@\   \   \  \ | /  /   /   /@MMb]::''
           ':uMM@\    \   \  \|/  /   /    /@MMu:'
            ':dMM@\----\---\--+--/---/----/@MMb:'
             ':uNMM\    \   \ | /   /    /MMNu:'
              ':[dMM\    \   \|/   /    /MMb]:'
               ':u8NN\----\---+---/----/NN8u:'
                 ''::\     \  |  /     /::''
                      \     \ | /     /
                       '-----\+------'
                             'v'
"""

# ===========================================================================
# 3. ЛОГОТИП DRAWBRIDGE: ИНДУСТРИАЛЬНЫЙ РАЗВОДНОЙ МОСТ (Ref 3 + Ref 4)
# ===========================================================================
DRAWBRIDGE_INDUSTRIAL_BASCULE = r"""
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
       .+MM#-.   (◎)═════════╝ || ╚═════════(◎)   .-#MM+.
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
# 4. ЛОГОТИП DRAWBRIDGE: СОВРЕМЕННЫЙ ЩИТ-ШЕВРОН (Ref 3 + Ref 2)
# ===========================================================================
DRAWBRIDGE_COMPACT_SHIELD = r"""
                     .▄██████████████▄.
                  .▄██▀▀    ││    ▀▀██▄.
                .▄██▀   ▄█  ││  █▄   ▀██▄.
               ▄██▀    ███▌ ││ ▐███    ▀██▄
              ███▌    ████▌ ││ ▐████    ▐███
             ████    █████▌ ││ ▐█████    ████
             ████───[X]███▌ ││ ▐███[X]───████
             ████   [X]███▌ ││ ▐███[X]   ████
              ███▌  (◎)═══╝ ││ ╚═══(◎)  ▐███
               ▀██▄    ▲    ││    ▲    ▄██▀
                 ▀██▄▄ ╩════╩╩════╩ ▄▄██▀
                    ▀▀██████████████▀▀
          ╔═════════════════════════════════════╗
          ║          D R A W B R I D G E        ║
          ║    ///  BOTH STICK AND ROPE  ///    ║
          ║      LINUX HOST ◄═══► WIN64 NODE    ║
          ╚═════════════════════════════════════╝
"""

# ===========================================================================
# 5. ХИРАЛЬНЫЙ СЕТЕВОЙ ГОЛОГРАФИЧЕСКИЙ РАДАР (Odradek / Strand Map)
# ===========================================================================
CHIRAL_RADAR_MESH = r"""
                      .:: [ ★  ★  ★ ] ::.
                  .:/+XXXXXX##HH##XXXXXX+\:.
                .:+XMM@@@@@@@@@@@@@@@@@@MMX+:.
             . =XMM@##'              '##@MMX= .
           . +HMM@#-    [LNX]      [WIN]   -#@MMH+ .
         . =XMM@#-       (●)════════(●)      -#@MMX= .
       . :dMM@#-          \  CHIRAL  /         -#@MMb: .
     ..::[dMM@#-           \ NETWORK/           -#@MMb]::..
   .:[u8NNMM@#-     ..-------\-||-/-------..     -#@MMNN8u]:.
 .:[dMM@@@MM@#-    '          \|/          '    -#@MM@@@MMb]:.
<=============================<◇>=============================>
|             B  R  I  D  G  E     L  O  C  A  L              |
|        ///  DISCONNECTED FROM WORLD · CONNECTED TO US  ///  |
<=============================<◇>=============================>
 ':[dMM@@@MM@#-    .          /|\          .    -#@MM@@@MMb]:'
   .:[u8NNMM@#-     ''-------/-||-\-------''     -#@MMNN8u]:.
     ''::[dMM@#-           / UMBILICAL\         -#@MMb]::''
       ' :dMM@#-          /  0.28 ms   \       -#@MMb: '
         ' =XMM@#-       (●)════════(●)      -#@MMX= '
           ' +HMM@#-    [HOST]    [CLIENT] -#@MMH+ '
             ' =XMM@##.              .##@MMX= '
                ':+XMM@@@@@@@@@@@@@@@@@@MMX+:'
                  ':\+XXXXXX##HH##XXXXXX+/: '
                      ':: [ ★  ★  ★ ] ::'
"""

# ===========================================================================
# 6. КОМПАКТНЫЕ МИКРО-БАННЕРЫ (Для повседневного CLI и agy_cli)
# ===========================================================================


def render_compact_cli_banners() -> None:
    """Выводит компактные версии для CLI вызовов без лишних токенов."""
    table = Table(title="⚡ КОМПАКТНЫЕ ВАРИАНТЫ ДЛЯ CLI (ОДНОСТРОЧНИКИ / 2-СТРОЧНИКИ)", expand=True)
    table.add_column("Тип", style="bold yellow", width=18)
    table.add_column("Отображение в терминале", style="white")

    # 1. BRIDGES Micro
    b1 = Text()
    b1.append(" [LNX] ───▲═══\\═══/═══▲─── [WIN] ", style="bold #F5A623")
    b1.append(":: BRIDGE LOCAL ", style="bold white")
    b1.append("(LAN 1.0 Gbps · 0.28ms)", style="dim green")
    table.add_row("Bridges Single", b1)

    # 2. BRIDGES 2-Line
    b2 = Text()
    b2.append("  ▲═══\\═══▲   ", style="bold #F5A623")
    b2.append("BRIDGE LOCAL v0.4.0 ", style="bold white")
    b2.append("/// STRAND LAN UMBILICAL\n", style="dim #56B6C2")
    b2.append(" [LNX] ═ [WIN] ", style="bold #61AFEF")
    b2.append("» Pocket: ", style="dim")
    b2.append("100% SYNCED", style="bold green")
    b2.append(" · Notes: ", style="dim")
    b2.append("0 unread", style="cyan")
    b2.append(" · Heartbeat: ", style="dim")
    b2.append("0.3ms (OK)", style="green")
    table.add_row("Bridges 2-Line", b2)

    # 3. DRAWBRIDGE Micro
    b3 = Text()
    b3.append(" |\\_/| ", style="bold #FF6B00")
    b3.append("[LNX]===/   \\===[WIN] ", style="bold white")
    b3.append("DRAWBRIDGE ACTIVE ", style="bold #FF6B00")
    b3.append("[Stick: SECURE | Rope: ENGAGED]", style="dim #ABB2BF")
    table.add_row("Drawbridge Single", b3)

    # 4. Hazard Minimal Headless (Минимум токенов для LLM)
    b4 = Text()
    b4.append("/// ", style="bold #E5C07B")
    b4.append("BRIDGE LOCAL", style="bold white")
    b4.append(" /// ", style="bold #E5C07B")
    b4.append("[NODE: LINUX ↔ WIN64] ", style="bold #61AFEF")
    b4.append("STATUS: ONLINE (0.3ms)", style="green")
    table.add_row("Hazard Minimal", b4)

    console.print(table)


# ===========================================================================
# 7. АРХИТЕКТУРА ИНТЕРФЕЙСА С РЕЖИМАМИ (MODES — Ref intCli.txt)
# ===========================================================================


def render_mode_tabs(active_mode: str) -> None:
    """Верхняя панель переключения режимов (Компактный Tab Bar в 1 строку)."""
    modes = [
        ("DASH", "F1"),
        ("POCKET", "F2"),
        ("NOTES", "F3"),
        ("EXEC", "F4"),
        ("CFG", "F5"),
    ]
    bar = Text()
    bar.append(" ◈ BRIDGES ◈ ", style="bold black on #F5A623")
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
    render_mode_tabs("DASH")

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    left = Panel(
        """[bold white]ЛОКАЛЬНАЯ ХИРАЛЬНАЯ СЕТЬ (STRAND MESH)[/]
[bold #61AFEF]HOST: LINUX (Workstation)[/]
  ├─ IP: 192.168.1.104
  ├─ OS: Linux 6.13 (Arch / Omarchy)
  └─ Agent: agy_cli (Antigravity Operator)

[bold #98C379]NODE: WIN-PC (Service Daemon)[/]
  ├─ IP: 192.168.1.150:41037
  ├─ Status: [bold green]ONLINE (Ready)[/]
  ├─ Heartbeat: 0.38 ms [green]●[/] (Fail-Fast limit: 1500 ms)
  ├─ CPU: 2.4% | RAM: 14.2 / 64 GB
  └─ Uptime: 4d 18h 32m""",
        title="[bold #F5A623]📡 СЕТЕВОЙ ЛИНК[/]",
        border_style="#F5A623",
    )

    right = Panel(
        """[bold white]СОСТОЯНИЕ ХРАНИЛИЩА И ОЧЕРЕДЕЙ[/]
[bold yellow]КАРМАН (Pocket Storage):[/]
  ├─ Путь: ~/.bridge_local/pocket/
  ├─ Файлов в кармане: 18 файлов (1.4 GB)
  ├─ Watchdog: [green]АКТИВЕН[/] (debounce 0.5s)
  └─ Последний sync: 10:04:12 [green]✔ 100% SHA MATCH[/]

[bold cyan]ЗАПИСКИ (Notes Engine):[/]
  ├─ Хранилище: pocket/.notes/notes.jsonl
  ├─ Всего заметок: 42
  └─ Непрочитанных: [bold green]0 unread[/]""",
        title="[bold #56B6C2]📦 КАРМАН И ЗАПИСКИ[/]",
        border_style="#56B6C2",
    )

    grid.add_row(left, right)
    console.print(grid)
    console.print(
        "[dim]Горячие клавиши: [F1..F5] Режимы | [S] Sync | [N] Новая записка | [Q] Выход[/dim]\n"
    )


def render_pocket_mode() -> None:
    """Режим 2: POCKET / КАРМАН (F2)."""
    render_mode_tabs("POCKET")
    table = Table(title="📦 POCKET STORAGE ENGINE (~/.bridge_local/pocket/)", expand=True)
    table.add_column("Файл / Директория", style="bold white")
    table.add_column("Размер", style="cyan", justify="right")
    table.add_column("Направление", style="yellow", justify="center")
    table.add_column("SHA-256 Match", style="bold green", justify="center")
    table.add_column("Статус", style="green")

    table.add_row("report_phase_04.docx", "2.4 MB", "LNX ──► WIN", "✔ d9e4f1a...", "Synced")
    table.add_row("setup_env_win.ps1", "12.8 KB", "WIN ──► LNX", "✔ 3a7c88b...", "Synced")
    table.add_row(
        "model_weights.bin",
        "1.2 GB",
        "LNX ──► WIN",
        "[yellow]● 68%[/]",
        "[bold yellow]Transferring (48 MB/s)[/]",
    )
    table.add_row("screenshot_crash.png", "840 KB", "WIN ──► LNX", "✔ f7a012c...", "Synced")

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
  Поставил службу BridgeLocalAgent в автозапуск, chcp 65001 проверен.

[bold #98C379][10:08:22] LINUX (Antigravity agy_cli):[/]
  Интеграционные тесты ядра и RPC прошли без сбоев (146 тестов, 7.21с).
  Готовлю передачу весов модели в карман.

[bold #F5A623][10:11:03] USER (Quick Note):[/]
  Не забудь глянуть температуру GPU на винде перед запуском бенча!

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold white]Ввод новой записки ([Enter] Отправить на все узлы):[/]
[bold cyan]» [/][blink]█[/]""",
        title="[bold cyan]📝 ЛЕНТА ЗАМЕТОК (STREAM)[/]",
        border_style="cyan",
    )

    stats = Panel(
        """[bold white]СТАТИСТИКА ЗАМЕТОК[/]
├─ Всего записей: 43
├─ Непрочитанных: [bold green]0[/]
├─ Файл: [dim]notes.jsonl[/]
└─ Синхронизация: [green]Instant[/]

[bold yellow]ФИЛЬТРЫ:[/][dim]
 [A] Все заметки
 [U] Только непрочитанные
 [S] Поиск по тексту[/dim]""",
        title="[bold yellow]ИНФО[/]",
        border_style="#E5C07B",
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
Кодировка: [bold green]UTF-8 (chcp 65001)[/] | Права: [bold red]Admin[/] | Таймаут: 30s

[bold #61AFEF]PS C:\\BridgeService> [/][white]Get-Service -Name "BridgeLocalAgent"[/]

Status   Name               DisplayName
------   ----               -----------
[bold green]Running[/]  BridgeLocalAgent   Bridge Local Windows Daemon v0.4.0

[bold #61AFEF]PS C:\\BridgeService> [/][white]Get-Process -Name "python" | Select Id, CPU, WS[/]

   Id        CPU       WS
   --        ---       --
 4912   1.421875 42811392

[dim]─────────────────────────────────────────────────────────────────────────────[/]
[bold yellow]Ввод команды ([Enter] Отправить на Windows | [Ctrl+C] Прервать):[/]
[bold white]PS C:\\BridgeService> [/] [blink]█[/]""",
            title="[bold red]⚡ POWERSHELL RUNNER (ELEVATED)[/]",
            border_style="#E06C75",
        )
    )
    console.print(
        "[dim]Горячие клавиши: [Enter] Выполнить | [Ctrl+L] Очистить | [F1..F5] Режимы[/dim]\n"
    )


def render_config_mode() -> None:
    """Режим 5: CONFIG / УЗЛЫ (F5)."""
    render_mode_tabs("CFG")
    table = Table(title="⚙ РЕГИСТР УЗЛОВ И ПАРАМЕТРЫ СЕТИ", expand=True)
    table.add_column("Узел (Node ID)", style="bold white")
    table.add_column("Роль / Тип", style="cyan")
    table.add_column("Сетевой Адрес", style="yellow")
    table.add_column("Heartbeat", style="white")
    table.add_column("Авторизация", style="bold green")

    table.add_row(
        "LINUX-HOST (local)",
        "Workstation (Core)",
        "127.0.0.1 / 192.168.1.104",
        "1500 ms",
        "✔ HMAC Active",
    )
    table.add_row(
        "WIN-PC (remote)",
        "Worker Agent",
        "192.168.1.150:41037",
        "1500 ms",
        "✔ HMAC Active",
    )
    table.add_row(
        "NODE-MACBOOK (future)",
        "Mobile Node",
        "192.168.1.112:41037",
        "3000 ms",
        "[dim]Offline[/dim]",
    )

    console.print(table)
    console.print(
        "[dim]Горячие клавиши: [A] Добавить | [E] Изменить | [T] Пинг | [F1..F5] Режимы[/dim]\n"
    )


# ===========================================================================
# 8. ТОЧКА ВХОДА И ДЕМОНСТРАТОР
# ===========================================================================


def main() -> None:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    sep = "═" * 70

    if arg in ("all", "bridges"):
        console.print(f"\n[bold #F5A623]{sep}[/]")
        console.print("[bold yellow] 1. BRIDGES MASTER — ЯНТАРНАЯ ПЛОТНОСТЬ CRT (Ref 1 + 4) [/]")
        console.print(f"[bold #F5A623]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_AMBER_MASTER, style="bold #F5A623"),
                title="[bold #FFA500]◈ BRIDGES // LOCAL NODE PROTOCOL ◈[/]",
                subtitle="[dim #F5A623]DISCONNECTED FROM WORLD · CONNECTED TO EACH OTHER[/]",
                border_style="#DCA134",
                expand=False,
            )
        )

        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 2. BRIDGES TITANIUM — МОНОХРОМНАЯ ТОЧЕЧНАЯ ПЛОТНОСТЬ (Ref 1 + Ref 2) [/]"
        )
        console.print(f"[bold white]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_TITANIUM_MONO, style="bold #E6EDF3"),
                title="[bold white]◈ BRIDGES // STRAND ARCHITECTURE ◈[/]",
                subtitle="[dim white]TOMORROW IS IN YOUR HANDS · LAN UMBILICAL[/]",
                border_style="#ABB2BF",
                expand=False,
            )
        )

    if arg in ("all", "drawbridge"):
        console.print(f"\n[bold #FF6B00]{sep}[/]")
        console.print("[bold #FF6B00] 3. DRAWBRIDGE INDUSTRIAL — РАЗВОДНЫЕ ПРОЛЕТЫ (Ref 3 + 4) [/]")
        console.print(f"[bold #FF6B00]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_INDUSTRIAL_BASCULE, style="bold #FF6B00"),
                title="[bold #FF6B00]⚓ DRAWBRIDGE // SECURE LOCAL BASCULE ⚓[/]",
                subtitle="[dim white]BOTH STICK AND ROPE : LINUX ↔ WIN64[/]",
                border_style="#FF6B00",
                expand=False,
            )
        )

        console.print(f"\n[bold #E5C07B]{sep}[/]")
        console.print(
            "[bold #E5C07B] 4. DRAWBRIDGE SHIELD — МИНИМАЛИСТИЧНЫЙ ЩИТ-ШЕВРОН (Ref 3 + Ref 2) [/]"
        )
        console.print(f"[bold #E5C07B]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_COMPACT_SHIELD, style="bold #E5C07B"),
                title="[bold #E5C07B]⚓ DRAWBRIDGE // COMPACT EMBLEM ⚓[/]",
                subtitle="[dim #E5C07B]TO PROTECT AND CONNECT · TOGETHER FOR TOMORROW[/]",
                border_style="#E5C07B",
                expand=False,
            )
        )

    if arg in ("all", "radar"):
        console.print(f"\n[bold cyan]{sep}[/]")
        console.print("[bold cyan] 5. CHIRAL NETWORK RADAR — ГОЛОГРАФИЧЕСКИЙ ТЕРМИНАЛ ODRADEK [/]")
        console.print(f"[bold cyan]{sep}[/]")
        console.print(
            Panel(
                Text(CHIRAL_RADAR_MESH, style="bold cyan"),
                title="[bold cyan]📡 CHIRAL RADAR // LOCAL MESH 📡[/]",
                subtitle="[dim cyan]STRAND LINK ONLINE · 0.28 MS LATENCY[/]",
                border_style="cyan",
                expand=False,
            )
        )

    if arg in ("all", "compact"):
        console.print(f"\n[bold cyan]{sep}[/]")
        console.print("[bold cyan] 6. КОМПАКТНЫЕ МИКРО-БАННЕРЫ ДЛЯ СТРОКИ СОСТОЯНИЯ CLI [/]")
        console.print(f"[bold cyan]{sep}[/]\n")
        render_compact_cli_banners()

    if arg in ("all", "modes"):
        console.print(f"\n[bold green]{sep}[/]")
        console.print("[bold green] 7. АРХИТЕКТУРА ИНТЕРФЕЙСА: ВСЕ 5 РЕЖИМОВ (Ref intCli.txt) [/]")
        console.print(f"[bold green]{sep}[/]\n")
        render_dashboard_mode()
        render_pocket_mode()
        render_notes_mode()
        render_exec_mode()
        render_config_mode()


if __name__ == "__main__":
    main()
