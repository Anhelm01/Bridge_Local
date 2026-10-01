"""
Unit tests for interactive TUI buttons, keyboard navigation, and rendering.
Verifies that all 6 modes, welcome screen, theme spec, animations, and key actions work flawlessly.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from ref.AI.ascii_preview import (
    OFFICIAL_THEME,
    demo_process_animations,
    handle_key_action,
    main,
    render_config_mode,
    render_current_mode,
    render_dashboard_mode,
    render_dev_mode,
    render_exec_mode,
    render_notes_mode,
    render_pocket_mode,
    render_theme_spec,
    render_welcome_screen,
    resolve_args,
)


def test_official_theme_attributes():
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


def test_key_action_buttons():
    """Тестирует переключение всех 6 вкладок и управляющих клавиш."""
    # Цифровые клавиши [1..6]
    assert handle_key_action("1", "POCKET") == ("DASH", True)
    assert handle_key_action("2", "DASH") == ("POCKET", True)
    assert handle_key_action("3", "DASH") == ("NOTES", True)
    assert handle_key_action("4", "DASH") == ("EXEC", True)
    assert handle_key_action("5", "DASH") == ("CONFIG", True)
    assert handle_key_action("6", "DASH") == ("DEV", True)

    # Функциональные клавиши F1..F6 (escape sequences)
    assert handle_key_action("\x1bOP", "DASH") == ("DASH", True)
    assert handle_key_action("\x1bOQ", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1bOR", "DASH") == ("NOTES", True)
    assert handle_key_action("\x1bOS", "DASH") == ("EXEC", True)
    assert handle_key_action("\x1b[15~", "DASH") == ("CONFIG", True)
    assert handle_key_action("\x1b[17~", "DASH") == ("DEV", True)

    # Именованные режимы
    assert handle_key_action("dev", "DASH") == ("DEV", True)
    assert handle_key_action("logs", "DASH") == ("DEV", True)
    assert handle_key_action("w", "DASH") == ("WELCOME", True)
    assert handle_key_action("a", "DASH") == ("ANIM", True)

    # Циклическое переключение по Tab
    assert handle_key_action("\t", "DASH") == ("POCKET", True)
    assert handle_key_action("\t", "POCKET") == ("NOTES", True)
    assert handle_key_action("\t", "NOTES") == ("EXEC", True)
    assert handle_key_action("\t", "EXEC") == ("CONFIG", True)
    assert handle_key_action("\t", "CONFIG") == ("DEV", True)
    assert handle_key_action("\t", "DEV") == ("DASH", True)

    # Выход по [Q] / Escape / Ctrl+C
    assert handle_key_action("q", "DASH") == ("DASH", False)
    assert handle_key_action("Q", "DASH") == ("DASH", False)
    assert handle_key_action("\x1b", "DASH") == ("DASH", False)
    assert handle_key_action("\x03", "DASH") == ("DASH", False)


def test_render_all_screens_without_exceptions():
    """Тестирует отрисовку каждого экрана на отсутствие любых падений и исключений."""
    # Все 6 оперативных окон
    render_dashboard_mode(OFFICIAL_THEME)
    render_pocket_mode(OFFICIAL_THEME)
    render_notes_mode(OFFICIAL_THEME)
    render_exec_mode(OFFICIAL_THEME)
    render_config_mode(OFFICIAL_THEME)
    render_dev_mode(OFFICIAL_THEME)

    # Экран приветствия (Neofetch), спецификация темы, анимации
    render_welcome_screen(OFFICIAL_THEME)
    render_theme_spec(OFFICIAL_THEME)
    demo_process_animations(OFFICIAL_THEME)

    # Диспетчер render_current_mode для каждого ключа
    test_modes = [
        "DASH",
        "POCKET",
        "NOTES",
        "EXEC",
        "CONFIG",
        "DEV",
        "WELCOME",
        "ANIM",
        "UNKNOWN",
    ]
    for mode in test_modes:
        render_current_mode(mode, OFFICIAL_THEME)


def test_cli_argument_resolution():
    """Тестирует парсер аргументов командной строки."""
    assert resolve_args(["welcome"]) == "welcome"
    assert resolve_args(["dev"]) == "dev"
    assert resolve_args(["logs"]) == "logs"
    assert resolve_args(["modes"]) == "modes"
    assert resolve_args(["all"]) == "all"
    assert resolve_args(["spec"]) == "spec"
    assert resolve_args(["tui"]) == "tui"
    assert resolve_args(["interactive"]) == "interactive"
    assert resolve_args(["dash"]) == "dash"
    assert resolve_args(["pocket"]) == "pocket"
    assert resolve_args(["notes"]) == "notes"
    assert resolve_args(["exec"]) == "exec"
    assert resolve_args(["config"]) == "config"


def test_main_cli_execution():
    """Тестирует запуск main() с различными аргументами без падений."""
    with patch.object(sys, "argv", ["preview.py", "spec"]):
        main()

    with patch.object(sys, "argv", ["preview.py", "welcome"]):
        main()

    with patch.object(sys, "argv", ["preview.py", "dev"]):
        main()

    with patch.object(sys, "argv", ["preview.py", "dash"]):
        main()

    with patch.object(sys, "argv", ["preview.py", "modes"]):
        main()
