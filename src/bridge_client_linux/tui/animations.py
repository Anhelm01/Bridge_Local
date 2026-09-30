"""
bridge_client_linux.tui.animations — Минимальные немерцающие анимации
фоновых процессов (At-a-Glance Observability).

Стандарт AGENTS.md (Раздел 7):
  - Позволяет оператору с расстояния 2-3 метров мгновенно оценить статус
    (активная передача, опрос сокета, простой) без необходимости вчитываться в текст.
  - Zero Flicker: строго локализовано без перерисовки всего терминала.
  - Headless Cleanliness: спиннеры и ANSI-эскейпы полностью исключаются при --json.
"""

from __future__ import annotations

import sys
import time

from rich.text import Text

from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

BRAILLE_SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

ACTIVITY_PULSES = [
    "[>    ]",
    "[>>   ]",
    "[>>>  ]",
    "[ >>>>]",
    "[  >>>]",
    "[   >>]",
    "[    >]",
]


def get_spinner(step: int) -> str:
    """Возвращает текущий глиф Braille-спиннера."""
    return BRAILLE_SPINNERS[step % len(BRAILLE_SPINNERS)]


def get_pulse(step: int) -> str:
    """Возвращает текущий глиф пульсирующей передачи данных."""
    return ACTIVITY_PULSES[step % len(ACTIVITY_PULSES)]


def demo_process_animations(theme: PaletteTheme = OFFICIAL_THEME, steps: int = 14) -> None:
    """Демонстрация локализованной анимации в терминале."""
    for step in range(steps):
        s = get_spinner(step)
        p = get_pulse(step)

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
        time.sleep(0.08)

    sys.stdout.write("\n\n")
    sys.stdout.flush()
