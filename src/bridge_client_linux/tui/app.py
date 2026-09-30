"""
bridge_client_linux.tui.app — Интерактивный цикл TUI приложения Bridge Local.

Реализует:
  - Безопасную инициализацию alternate screen buffer (исключает повреждение терминала).
  - Обработку функциональных клавиш F1..F6, цифр 1..6, Tab, Q, Esc, W, A.
  - Однопроходный режим для неинтерактивных сред / CI / тестов.
  - Чистое восстановление настроек терминала при завершении.
"""

from __future__ import annotations

import select
import sys
from typing import Any

from rich.console import Console

from bridge_client_linux.tui.screens import render_current_mode
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

console = Console()


def handle_key_action(key: str, current_mode: str) -> tuple[str, bool]:
    """
    Обрабатывает нажатую клавишу и возвращает кортеж:
      (новый_режим, продолжать_ли_цикл)
    """
    k = key.lower()
    # Выход из приложения
    if k in ("q", "\x03", "quit", "exit"):
        return current_mode, False

    # Режимы 1..6
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

    # Экран приветствия / Neofetch
    if k in ("w", "welcome", "splash"):
        return "WELCOME", True

    # Демонстрация анимаций
    if k in ("a", "anim"):
        return "ANIM", True

    # Tab — циклическое переключение
    if k in ("\t",):
        order = ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV"]
        if current_mode in order:
            nxt = order[(order.index(current_mode) + 1) % len(order)]
            return nxt, True
        return "DASH", True

    return current_mode, True


def run_interactive_tui(
    theme: PaletteTheme = OFFICIAL_THEME,
    initial_mode: str = "WELCOME",
    data: dict[str, Any] | None = None,
    single_pass: bool = False,
) -> None:
    """
    Запускает полноэкранный интерактивный TUI-интерфейс.

    Если stdin не является TTY или передан single_pass=True,
    отрисовывает заданный режим однократно и завершается.
    """
    if single_pass or not sys.stdin.isatty():
        render_current_mode(initial_mode, theme, data)
        return

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    current_mode = initial_mode.upper()

    # Переход в alternate screen buffer и скрытие курсора (исключает скролл и артефакты)
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        while True:
            # Очистка экрана и перемещение курсора в (1,1) без скролла
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()

            render_current_mode(current_mode, theme, data)

            # Минималистичная подсказка управления внизу
            console.print(
                f"\n [dim]Навигация:[/] "
                f"[bold {theme.blue}][1..6][/] Вкладки  "
                f"[bold {theme.primary}][W][/] Сплэш  "
                f"[bold {theme.amber}][A][/] Анимация  "
                f"[bold {theme.red}][Q][/] Выход"
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

            current_mode, keep_going = handle_key_action(ch, current_mode)
            if not keep_going:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        console.print(f"[bold {theme.green}][OK] Сеанс TUI завершён.[/]")
