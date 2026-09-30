"""
Unit tests for the production TUI module (bridge_client_linux.tui).
Verifies:
  - Official theme attributes and high-vibrancy accents.
  - Keyboard action dispatcher (modes 1..6, F1..F6, Tab, W, A, Q).
  - Rendering functions for all 6 operational modes, Welcome screen, and theme spec.
  - Non-flickering process animations (Braille spinners, activity pulses).
  - Single-pass non-interactive execution.
"""

from __future__ import annotations

from unittest.mock import patch

from bridge_client_linux.tui import (
    OFFICIAL_THEME,
    demo_process_animations,
    handle_key_action,
    render_config_mode,
    render_current_mode,
    render_dashboard_mode,
    render_dev_mode,
    render_exec_mode,
    render_notes_mode,
    render_operational_header,
    render_pocket_mode,
    render_theme_spec,
    render_welcome_screen,
    run_interactive_tui,
)


def test_tui_official_theme_properties() -> None:
    """Проверяет полноту атрибутов и hex-кодов официальной темы Titanium Vivid."""
    assert OFFICIAL_THEME.name == "Titanium Vivid / Cyber-Industrial"
    assert OFFICIAL_THEME.primary == "#FFFFFF"
    assert OFFICIAL_THEME.secondary == "#7D8590"
    assert OFFICIAL_THEME.text == "#FFFFFF"
    assert OFFICIAL_THEME.blue == "#00D2FF"
    assert OFFICIAL_THEME.green == "#00FF66"
    assert OFFICIAL_THEME.amber == "#FFB800"
    assert OFFICIAL_THEME.purple == "#C084FC"
    assert OFFICIAL_THEME.red == "#FF3366"


def test_tui_key_actions() -> None:
    """Проверяет работу диспетчера клавиатурных событий."""
    # Цифровые клавиши 1..6
    assert handle_key_action("1", "POCKET") == ("DASH", True)
    assert handle_key_action("2", "DASH") == ("POCKET", True)
    assert handle_key_action("3", "DASH") == ("NOTES", True)
    assert handle_key_action("4", "DASH") == ("EXEC", True)
    assert handle_key_action("5", "DASH") == ("CONFIG", True)
    assert handle_key_action("6", "DASH") == ("DEV", True)

    # Функциональные клавиши F1..F6 (escape-последовательности)
    assert handle_key_action("\x1bOP", "DASH") == ("DASH", True)
    assert handle_key_action("\x1bOQ", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1bOR", "DASH") == ("NOTES", True)
    assert handle_key_action("\x1bOS", "DASH") == ("EXEC", True)
    assert handle_key_action("\x1b[15~", "DASH") == ("CONFIG", True)
    assert handle_key_action("\x1b[17~", "DASH") == ("DEV", True)

    # Именованные режимы
    assert handle_key_action("dash", "POCKET") == ("DASH", True)
    assert handle_key_action("pocket", "DASH") == ("POCKET", True)
    assert handle_key_action("w", "DASH") == ("WELCOME", True)
    assert handle_key_action("a", "DASH") == ("ANIM", True)

    # Tab cycling
    assert handle_key_action("\t", "DASH") == ("POCKET", True)
    assert handle_key_action("\t", "DEV") == ("DASH", True)

    # Выход
    assert handle_key_action("q", "DASH") == ("DASH", False)
    assert handle_key_action("exit", "DASH") == ("DASH", False)


def test_tui_render_modes_without_errors() -> None:
    """Проверяет рендеринг всех экранов без исключений."""
    theme = OFFICIAL_THEME
    render_welcome_screen(theme)
    render_operational_header(theme)
    render_dashboard_mode(theme)
    render_pocket_mode(theme)
    render_notes_mode(theme)
    render_exec_mode(theme)
    render_config_mode(theme)
    render_dev_mode(theme)
    render_theme_spec(theme)

    for m in ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "WELCOME"]:
        render_current_mode(m, theme)


def test_tui_animations_demo() -> None:
    """Проверяет запуск анимаций без ошибок."""
    with patch("time.sleep", return_value=None):
        demo_process_animations(OFFICIAL_THEME, steps=4)


def test_tui_single_pass_runner() -> None:
    """Проверяет single-pass запуск без входа в блокирующий интерактивный цикл."""
    run_interactive_tui(theme=OFFICIAL_THEME, initial_mode="DASH", single_pass=True)
