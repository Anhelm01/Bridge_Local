r"""
ref/AI/ascii_preview.py — Интерактивный генератор и просмотрщик ASCII-логотипов
и концептов интерфейса по референсам из ref/Hum/.

Референсы из ref/Hum/:
  - photo_2026-09-30_10-01-41.jpg: Логотип BRIDGES (Death Stranding 1)
  - photo_2026-09-30_10-01-48.jpg: Логотип DRAWBRIDGE (Death Stranding 2)
  - photo_2026-09-30_10-01-45.jpg: Стиль 1 — Монохромный градиент (. , - : ; [ ] u 8 d N M ^ @ P \)
  - photo_2026-09-30_10-01-50.jpg: Стиль 2 — Янтарный CRT-терминал (. , - : ; / = + % $ # X H M @)
  - intCli.txt: Архитектура TUI с делением на "modes" (DASHBOARD, POCKET, NOTES, EXEC, CONFIG)
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ===========================================================================
# 1. ЛОГОТИП BRIDGES (Ромб, звезды, гребень, паутина-ванты)
# ===========================================================================

# Вариант 1А: Янтарная CRT-плотность (Ref 1 + Ref 4)
BRIDGES_AMBER_DENSITY = r"""
                      .:: ★ ★ ::.
                     . :+XMMMMX+: .
                    . :+HMM@@MMH+: .
                   . =XMM@#::#@MMX= .
                  . +HMM@#-  -#@MMH+ .
                 . =XMM@#-    -#@MMX= .
              .:::-#MM@#-      -#@MM#-:::.
            .:+XHH#HMM@#-  <>  -#@MMH#HHX+:.
          .:+HMM@@@@MM@#-.    .-#@MM@@@@MMH+:.
        .:=XMM@##@@@MM@#-.    .-#@MM@@@##@MMX=:.
      .-/HMM@#-  -#@MM@#-.    .-#@MM@#-  -#@MMH/-.
    .-+XMM@#-      -#@MM@#::::#@MM@#-      -#@MMX+-.
  .-=XMM@#-          -#@@MM@@MM@@#-          -#@MMX=-.
 .-%MM@#-              -########-              -#@MM%-.
<======================================================>
|             B  R  I  D  G  E     L  O  C  A  L       |
|              ///  STRAND  LAN  UMBILICAL  ///        |
<======================================================>
 '-%MM@#-.                                        .-#@MM%-'
  '-=XMM@#-.    \      \   ||   /      /    .-#@MMX=-'
    '-+XMM@#-.   \      \  ||  /      /   .-#@MMX+-'
      '-/HMM@#-.  \  ..---====---..  /  .-#@MMH/-'
        .-=XMM@#-.  '::;;;====;;;::'  .-#@MMX=-.
          .-+HMM@@-.   \ \ || / /   .-@@MMH+-.
            .-+XHH#H-.  \ \|/ /  .-H#HHX+-.
              .:::-#M-.  \ V /  .-M#-:::.
                 . =XM-.  \ /  .-MX= .
                  . +H-.   V   .-H+ .
                   . =X-.     .-X= .
                    . :+-.   .-+: .
                     . ::.   .:: .
                          'v'
"""

# Вариант 1Б: Монохромная точечная плотность (Ref 1 + Ref 2)
BRIDGES_MONO_DENSITY = r"""
                      ..: [★ ★] :..
                     . :u8NNMMNN8u: .
                    . :[dMM@@@@MMb]: .
                   . :uNMM#::..::#MMNu: .
                  . :dMM@/.      .\@MMb: .
                 . :uMM@/          \@MMu: .
              ..::[dMM@/    /\    \@MMb]::..
            .:[u8NNMM@/    /  \    \@MMNN8u]:.
          .:[dMM@@@MM@/   / /\ \   \@MM@@@MMb]:.
        .:uNMM#::#@MM@/  / /  \ \  \@MM@#::#MMNu:.
      .:dMM@/.  .\@MM@/ / / /\ \ \ \@MM@/.  .\@MMb:.
    .:uMM@/       \@MM@/ / /  \ \ \@MM@/       \@MMu:.
  .:[dMM@/         \@MM@/ /    \ \@MM@/         \@MMb]:.
 .u8NNMM/           \@MM@/      \@MM@/           \MMNN8u.
<========================================================>
|              B  R  I  D  G  E    L  O  C  A  L         |
|               [ LINUX HOST  <===>  WIN64 AGENT ]       |
<========================================================>
 'u8NNMM\           /@@MM\      /@@MM\           /MMNN8u'
  ':[dMM@\         /@@MM@/ \  / \@MM@@\         /@MMb]:'
    ':uMM@\       /@@MM@/   \/   \@MM@@\       /@MMu:'
      ':dMM@\.  ./@MM@/ \   ||   / \@MM@\.  ./@MMb:'
        ':uNMM#::#@MM@/   \ || /   \@MM@#::#MMNu:'
          ':[dMM@@@MM@\..  \||/  ../@MM@@@MMb]:'
            .:[u8NNMM@/''--====--''\@MMNN8u]:.
              ''::[dMM@\  / || \  /@MMb]::''
                 ':uMM@\ /  ||  \ /@MMu:'
                  ':dMM@\   ||   /@MMb:'
                   ':uNMM\  ||  /MMNu:'
                    ':[dMM\ || /MMb]:'
                     ':u8NN\||/NN8u:'
                       '':::vv:::''
"""

# ===========================================================================
# 2. ЛОГОТИП DRAWBRIDGE (Полукруг, вертикаль, два разводных пролета, фермы)
# ===========================================================================

# Вариант 2А: Чистый минималистичный силуэт (Ref 3)
DRAWBRIDGE_CLEAN_MINIMAL = r"""
                  .▄▄██████████▄▄.
               ▄██▀▀          ▀▀██▄
             ▄█▀    ▄█      █▄    ▀█▄
            █▀     ███▌ ││ ▐███     ▀█
           █▌     ████▌ ││ ▐████     ▐█
          █▌  │  █████▌ ││ ▐█████  │  ▐█
          █▌ ─┼─ █████▌ ││ ▐█████ ─┼─ ▐█
          █▌  │  █████▌ ││ ▐█████  │  ▐█
           █▌    ▀▀▀▀▀▀ ││ ▀▀▀▀▀▀    ▐█
            █▄          ││          ▄█
             ▀█▄        ││        ▄█▀
               ▀██▄▄    ││    ▄▄██▀
                  ▀▀██████████▀▀
           D  R  A  W  B  R  I  D  G  E
          ///  B R I D G E   L O C A L  ///
    BOTH STICK AND ROPE : TO PROTECT AND CONNECT
"""

# Вариант 2Б: Индустриальная янтарная плотность (Ref 3 + Ref 4)
DRAWBRIDGE_AMBER_DENSITY = r"""
                  .---:::///////:::---.
              .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
           .-+XMM@@MM##XX++++++XX##MM@@MMX+-.
         ./HMM@#X+-.     ▄█    █▄     .-+X#@MMH/.
       ./XMM#X-.        ███▌ ││ ▐███        .-X#MMX/.
      .+MM@X-.         ████▌ ││ ▐████         .-X@MM+.
     .+MM#-.      │   █████▌ ││ ▐█████   │      .-#MM+.
    ./MM#-       ─┼─ ██████▌ ││ ▐██████ ─┼─       -#MM/.
    :MM#-         │ ▐██████▌ ││ ▐██████▌ │         -#MM:
   .X@M:            ███████▌ ││ ▐███████            :M@X.
   :MM+            ▐███████▌ ││ ▐███████▌            +MM:
   =MM-            ▀▀▀▀▀▀▀▀▀ ││ ▀▀▀▀▀▀▀▀▀            -MM=
   :MM+                      ││                      +MM:
   .X@M:                     ││                     :M@X.
    :MM#-                    ││                    -#MM:
    ./MM#-                   ││                   -#MM/.
     .+MM#-.                 ││                 .-#MM+.
      .+MM@X-.               ││               .-X@MM+.
       ./XMM#X-.             ││             .-X#MMX/.
         ./HMM@#X+-.         ││         .-+X#@MMH/.
           .-+XMM@@MM##XX++++││++++XX##MM@@MMX+-.
              .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
                  .---:::///////:::---.
           D  R  A  W  B  R  I  D  G  E
      ///  B O T H   S T I C K   A N D   R O P E  ///
"""

# ===========================================================================
# 3. КОМПАКТНЫЕ МИКРО-БАННЕРЫ (Для повседневного CLI и agy_cli)
# ===========================================================================


def render_compact_cli_banners() -> None:
    """Выводит компактные версии для CLI вызовов без лишних токенов."""
    table = Table(title="⚡ КОМПАКТНЫЕ ВАРИАНТЫ ДЛЯ CLI (ОДНОСТРОЧНИКИ / 2-СТРОЧНИКИ)", expand=True)
    table.add_column("Тип", style="bold yellow", width=16)
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

    # 4. Hazard AI Headless (Минимум токенов)
    b4 = Text()
    b4.append("/// ", style="bold #E5C07B")
    b4.append("BRIDGE LOCAL", style="bold white")
    b4.append(" /// ", style="bold #E5C07B")
    b4.append("[NODE: LINUX ↔ WIN64] ", style="bold #61AFEF")
    b4.append("STATUS: ONLINE (0.3ms)", style="green")
    table.add_row("Hazard Minimal", b4)

    console.print(table)


# ===========================================================================
# 4. АРХИТЕКТУРА ИНТЕРФЕЙСА С РЕЖИМАМИ (MODES)
# ===========================================================================


def render_mode_tabs(active_mode: str) -> None:
    """Верхняя панель переключения режимов (Tab Bar)."""
    modes = [
        ("DASHBOARD", "F1"),
        ("POCKET", "F2"),
        ("NOTES", "F3"),
        ("EXEC", "F4"),
        ("CONFIG", "F5"),
    ]
    bar = Text()
    bar.append(" ◈ BRIDGE LOCAL ◈ ", style="bold black on #F5A623")
    bar.append(" ")
    for name, key in modes:
        if name == active_mode:
            bar.append(f" █ {name} [{key}] ", style="bold white on #282C34")
        else:
            bar.append(f"   {name} [{key}]  ", style="dim #5C6370 on #1E222A")
        bar.append(" ")
    console.print(Panel(bar, style="#3E4451", expand=True))


def render_dashboard_mode() -> None:
    """Режим 1: DASHBOARD / СТАТУС (F1)."""
    render_mode_tabs("DASHBOARD")

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    # Левая колонка: Узлы и сеть
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

    # Правая колонка: Состояние кармана и заметок
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


# ===========================================================================
# 5. ТОЧКА ВХОДА И ДЕМОНСТРАТОР
# ===========================================================================


def main() -> None:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    sep = "═" * 70

    if arg in ("all", "bridges"):
        console.print(f"\n[bold #F5A623]{sep}[/]")
        console.print("[bold yellow] 1. ЛОГОТИП BRIDGES — ЯНТАРНАЯ CRT-ПЛОТНОСТЬ (Ref 1 + 4) [/]")
        console.print(f"[bold #F5A623]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_AMBER_DENSITY, style="bold #F5A623"),
                title="[bold #FFA500]◈ BRIDGES // LOCAL NODE PROTOCOL ◈[/]",
                subtitle="[dim #F5A623]DISCONNECTED FROM WORLD · CONNECTED TO EACH OTHER[/]",
                border_style="#DCA134",
                expand=False,
            )
        )

        console.print(f"\n[bold white]{sep}[/]")
        console.print(
            "[bold white] 2. ЛОГОТИП BRIDGES — МОНОХРОМНАЯ ТОЧЕЧНАЯ ПЛОТНОСТЬ (Ref 1 + Ref 2) [/]"
        )
        console.print(f"[bold white]{sep}[/]")
        console.print(
            Panel(
                Text(BRIDGES_MONO_DENSITY, style="bold #E6EDF3"),
                title="[bold white]◈ BRIDGES // STRAND ARCHITECTURE ◈[/]",
                subtitle="[dim white]TOMORROW IS IN YOUR HANDS · LAN UMBILICAL[/]",
                border_style="#ABB2BF",
                expand=False,
            )
        )

    if arg in ("all", "drawbridge"):
        console.print(f"\n[bold #FF6B00]{sep}[/]")
        console.print("[bold #FF6B00] 3. ЛОГОТИП DRAWBRIDGE — ЧИСТЫЙ МИНИМАЛИЗМ СУДНА (Ref 3) [/]")
        console.print(f"[bold #FF6B00]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_CLEAN_MINIMAL, style="bold #E6EDF3"),
                title="[bold #FF6B00]⚓ DRAWBRIDGE // SECURE LOCAL BASCULE ⚓[/]",
                subtitle="[dim white]BOTH STICK AND ROPE : LINUX ↔ WIN64[/]",
                border_style="#FF6B00",
                expand=False,
            )
        )

        console.print(f"\n[bold #E5C07B]{sep}[/]")
        console.print(
            "[bold #E5C07B] 4. ЛОГОТИП DRAWBRIDGE — ИНДУСТРИАЛЬНАЯ ПЛОТНОСТЬ (Ref 3 + Ref 4) [/]"
        )
        console.print(f"[bold #E5C07B]{sep}[/]")
        console.print(
            Panel(
                Text(DRAWBRIDGE_AMBER_DENSITY, style="bold #E5C07B"),
                title="[bold #E5C07B]⚓ DRAWBRIDGE // HEAVY INDUSTRIAL GIRDERS ⚓[/]",
                subtitle="[dim #E5C07B]TO PROTECT AND CONNECT · TOGETHER FOR TOMORROW[/]",
                border_style="#E5C07B",
                expand=False,
            )
        )

    if arg in ("all", "compact"):
        console.print(f"\n[bold cyan]{sep}[/]")
        console.print("[bold cyan] 5. КОМПАКТНЫЕ МИКРО-БАННЕРЫ ДЛЯ СТРОКИ СОСТОЯНИЯ CLI [/]")
        console.print(f"[bold cyan]{sep}[/]\n")
        render_compact_cli_banners()

    if arg in ("all", "modes"):
        console.print(f"\n[bold green]{sep}[/]")
        console.print(
            "[bold green] 6. АРХИТЕКТУРА ИНТЕРФЕЙСА: РЕЖИМЫ (MODES DEMO — Ref intCli.txt) [/]"
        )
        console.print(f"[bold green]{sep}[/]\n")
        render_dashboard_mode()
        render_exec_mode()


if __name__ == "__main__":
    main()
