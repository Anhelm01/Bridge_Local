"""
Unit tests for interactive TUI buttons, keyboard navigation, and rendering in Bridge Local.
Verifies:
  - F1..F8 direct tab addressing across all 8 tabs.
  - Scroll navigation (Arrow Up/Down, Page Up/Down, Home, End) and bounds clamping.
  - Letters do not trigger mode changes or quit.
  - Escape sequence reading and parsing.
  - Screen rendering with scrolling indicators.
"""

from __future__ import annotations

import io
from typing import Any

from bridge_client_linux.tui import (
    MODES_ORDER,
    OFFICIAL_THEME,
    demo_process_animations,
    handle_key_action,
    handle_scroll_action,
    read_terminal_key,
    render_config_mode,
    render_current_mode,
    render_dashboard_mode,
    render_dev_mode,
    render_exec_mode,
    render_mode_tabs,
    render_notes_mode,
    render_operational_header,
    render_pocket_mode,
    render_theme_spec,
    render_welcome_screen,
)


def test_official_theme_attributes() -> None:
    """Проверяет полноту атрибутов официальной темы (никаких AttributeError)."""
    assert OFFICIAL_THEME.name == "Titanium Vivid / Cyber-Industrial"
    assert OFFICIAL_THEME.primary == "#FFFFFF"
    assert OFFICIAL_THEME.secondary == "#7D8590"
    assert OFFICIAL_THEME.text == "#FFFFFF"
    assert OFFICIAL_THEME.blue == "#00D2FF"
    assert OFFICIAL_THEME.green == "#00FF66"
    assert OFFICIAL_THEME.amber == "#FFB800"
    assert OFFICIAL_THEME.purple == "#C084FC"
    assert OFFICIAL_THEME.red == "#FF3366"


def test_f1_to_f8_tab_switching() -> None:
    """Тестирует прямое переключение всех 8 вкладок через клавиши F1..F8."""
    # F1: SPLASH
    for k in ("\x1bOP", "\x1b[[A", "\x1b[11~", "f1", "F1"):
        assert handle_key_action(k, "DASH") == ("SPLASH", True)

    # F2: DASH
    for k in ("\x1bOQ", "\x1b[[B", "\x1b[12~", "f2", "F2"):
        assert handle_key_action(k, "SPLASH") == ("DASH", True)

    # F3: POCKET
    for k in ("\x1bOR", "\x1b[[C", "\x1b[13~", "f3", "F3"):
        assert handle_key_action(k, "DASH") == ("POCKET", True)

    # F4: NOTES
    for k in ("\x1bOS", "\x1b[[D", "\x1b[14~", "f4", "F4"):
        assert handle_key_action(k, "DASH") == ("NOTES", True)

    # F5: EXEC
    for k in ("\x1b[15~", "f5", "F5"):
        assert handle_key_action(k, "DASH") == ("EXEC", True)

    # F6: CONFIG
    for k in ("\x1b[17~", "f6", "F6"):
        assert handle_key_action(k, "DASH") == ("CONFIG", True)

    # F7: DEV
    for k in ("\x1b[18~", "f7", "F7"):
        assert handle_key_action(k, "DASH") == ("DEV", True)

    # F8: CONNECT
    for k in ("\x1b[19~", "f8", "F8"):
        assert handle_key_action(k, "DASH") == ("CONNECT", True)


def test_tab_and_shift_tab_navigation() -> None:
    """Тестирует циклическое переключение всех 8 вкладок по Tab и Shift+Tab."""
    order = MODES_ORDER
    # Прямой цикл Tab
    for i, mode in enumerate(order):
        expected_next = order[(i + 1) % len(order)]
        assert handle_key_action("\t", mode) == (expected_next, True)

    # Обратный цикл Shift+Tab
    for i, mode in enumerate(order):
        expected_prev = order[(i - 1) % len(order)]
        assert handle_key_action("\x1b[Z", mode) == (expected_prev, True)
        assert handle_key_action("shift+tab", mode) == (expected_prev, True)


def test_letters_do_not_switch_modes_or_quit() -> None:
    """Проверяет, что буквы (w, q, r, c, a и т.д.) не переключают экраны и не выходят."""
    letters = ["w", "W", "q", "Q", "r", "R", "c", "C", "a", "A", "d", "e", "p", "n", "x", "z"]
    for letter in letters:
        assert handle_key_action(letter, "DASH") == ("DASH", True)
        assert handle_key_action(letter, "POCKET") == ("POCKET", True)
        assert handle_key_action(letter, "NOTES") == ("NOTES", True)
        assert handle_key_action(letter, "EXEC") == ("EXEC", True)
        assert handle_key_action(letter, "SPLASH") == ("SPLASH", True)

    # Выход только по специальным управляющим символам и командам
    assert handle_key_action("\x03", "DASH") == ("DASH", False)  # Ctrl+C
    assert handle_key_action("\x11", "DASH") == ("DASH", False)  # Ctrl+Q
    assert handle_key_action(":q", "DASH") == ("DASH", False)
    assert handle_key_action("exit", "DASH") == ("DASH", False)
    assert handle_key_action("quit", "DASH") == ("DASH", False)


def test_scroll_system_up_down_pgup_pgdn_home_end() -> None:
    """Тестирует полную систему скролла: Arrow Up/Down, Page Up/Down, Home, End и границы."""
    state: dict[str, Any] = {
        "pocket_files": [{"name": f"f_{i}"} for i in range(30)],
        "notes_list": [{"text": f"n_{i}"} for i in range(25)],
        "exec_history": [(f"c_{i}", f"o_{i}", 0) for i in range(20)],
        "dev_logs": [f"log_{i}" for i in range(20)],
        "scroll_offsets": {"POCKET": 0, "NOTES": 0, "EXEC": 0, "DEV": 0},
    }

    # --- POCKET (page_size = 10, total = 30, max_offset = 20) ---
    assert handle_scroll_action("\x1b[B", "POCKET", state) is True  # 1 вниз
    assert state["scroll_offsets"]["POCKET"] == 1

    assert handle_scroll_action("\x1b[6~", "POCKET", state) is True  # PgDn (+10)
    assert state["scroll_offsets"]["POCKET"] == 11

    assert handle_scroll_action("\x1b[F", "POCKET", state) is True  # End
    assert state["scroll_offsets"]["POCKET"] == 20

    assert handle_scroll_action("\x1b[B", "POCKET", state) is True  # Ниже конца не идет
    assert state["scroll_offsets"]["POCKET"] == 20

    assert handle_scroll_action("\x1b[A", "POCKET", state) is True  # 1 вверх
    assert state["scroll_offsets"]["POCKET"] == 19

    assert handle_scroll_action("\x1b[5~", "POCKET", state) is True  # PgUp (-10)
    assert state["scroll_offsets"]["POCKET"] == 9

    assert handle_scroll_action("\x1b[H", "POCKET", state) is True  # Home
    assert state["scroll_offsets"]["POCKET"] == 0

    assert handle_scroll_action("\x1b[A", "POCKET", state) is True  # Выше начала не идет
    assert state["scroll_offsets"]["POCKET"] == 0

    # --- NOTES (page_size = 6, total = 25, max_offset = 19) ---
    assert handle_scroll_action("\x1b[B", "NOTES", state) is True
    assert state["scroll_offsets"]["NOTES"] == 1
    assert handle_scroll_action("\x1b[6~", "NOTES", state) is True
    assert state["scroll_offsets"]["NOTES"] == 7
    assert handle_scroll_action("\x1b[F", "NOTES", state) is True
    assert state["scroll_offsets"]["NOTES"] == 19
    assert handle_scroll_action("\x1b[H", "NOTES", state) is True
    assert state["scroll_offsets"]["NOTES"] == 0

    # --- EXEC (page_size = 4, total = 20, max_offset = 16) ---
    assert handle_scroll_action("\x1b[6~", "EXEC", state) is True
    assert state["scroll_offsets"]["EXEC"] == 4
    assert handle_scroll_action("\x1b[F", "EXEC", state) is True
    assert state["scroll_offsets"]["EXEC"] == 16


def test_escape_sequence_reader_robustness() -> None:
    """Тестирует безотказное чтение escape-последовательностей терминала."""
    # F1..F8
    for code in [
        "\x1bOP",
        "\x1b[[A",
        "\x1b[11~",
        "\x1bOQ",
        "\x1b[[B",
        "\x1b[12~",
        "\x1bOR",
        "\x1b[[C",
        "\x1b[13~",
        "\x1bOS",
        "\x1b[[D",
        "\x1b[14~",
        "\x1b[15~",
        "\x1b[17~",
        "\x1b[18~",
        "\x1b[19~",
    ]:
        stream = io.StringIO(code)
        assert read_terminal_key(stream) == code

    # Стрелки и скролл
    for code in [
        "\x1b[A",
        "\x1b[B",
        "\x1b[5~",
        "\x1b[6~",
        "\x1b[H",
        "\x1b[1~",
        "\x1b[F",
        "\x1b[4~",
    ]:
        stream = io.StringIO(code)
        assert read_terminal_key(stream) == code

    # Одиночный escape
    stream = io.StringIO("\x1b")
    assert read_terminal_key(stream) == "\x1b"


def test_render_all_screens_with_scroll_indicators() -> None:
    """Тестирует отрисовку экранов с индикаторами скрытых строк."""
    theme = OFFICIAL_THEME
    state = {
        "pocket_files": [
            {"name": f"test_file_{i}.txt", "size": "1.2 MB", "status": "READY"}
            for i in range(25)
        ],
        "notes_list": [
            {"time": "14:30:00", "author": "NODE_A", "text": f"Заметка #{i}"}
            for i in range(15)
        ],
        "exec_history": [
            (f"Get-Process -Id {i}", f"Process info {i}", 0) for i in range(10)
        ],
        "dev_logs": [f"[TRACE] Network packet {i}" for i in range(16)],
        "scroll_offsets": {"POCKET": 5, "NOTES": 3, "EXEC": 2, "DEV": 4},
        "is_online": True,
        "input_buffer": "",
        "status_msg": "OK",
    }

    # Отрисовка всех основных экранов
    render_welcome_screen(theme, state)
    render_operational_header(theme, state)
    render_dashboard_mode(theme, state)
    render_pocket_mode(theme, state)
    render_notes_mode(theme, state)
    render_exec_mode(theme, state)
    render_config_mode(theme, state)
    render_dev_mode(theme, state)
    render_theme_spec(theme)
    demo_process_animations(theme, steps=1)

    # Проверка плашки табов
    render_mode_tabs("POCKET", theme)
    render_mode_tabs("DASH", theme)
    render_mode_tabs("SPLASH", theme)

    for mode in ["SPLASH", "DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT"]:
        render_current_mode(mode, theme, state)
