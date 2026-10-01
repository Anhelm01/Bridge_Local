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

from unittest.mock import AsyncMock, MagicMock, patch

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
from bridge_client_linux.tui.app import dispatch_tui_action
from bridge_core.models import ExecResult, NoteDeliveryResult, PocketPushResult


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
    # Цифровые клавиши 1..7
    assert handle_key_action("1", "POCKET") == ("DASH", True)
    assert handle_key_action("2", "DASH") == ("POCKET", True)
    assert handle_key_action("3", "DASH") == ("NOTES", True)
    assert handle_key_action("4", "DASH") == ("EXEC", True)
    assert handle_key_action("5", "DASH") == ("CONFIG", True)
    assert handle_key_action("6", "DASH") == ("DEV", True)
    assert handle_key_action("7", "DASH") == ("CONNECT", True)

    # Функциональные клавиши F1..F7 (escape-последовательности)
    assert handle_key_action("\x1bOP", "DASH") == ("DASH", True)
    assert handle_key_action("\x1bOQ", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1bOR", "DASH") == ("NOTES", True)
    assert handle_key_action("\x1bOS", "DASH") == ("EXEC", True)
    assert handle_key_action("\x1b[15~", "DASH") == ("CONFIG", True)
    assert handle_key_action("\x1b[17~", "DASH") == ("DEV", True)
    assert handle_key_action("\x1b[18~", "DASH") == ("CONNECT", True)

    # Именованные режимы
    assert handle_key_action("dash", "POCKET") == ("DASH", True)
    assert handle_key_action("pocket", "DASH") == ("POCKET", True)
    assert handle_key_action("connect", "DASH") == ("CONNECT", True)
    assert handle_key_action("w", "DASH") == ("WELCOME", True)
    assert handle_key_action("a", "DASH") == ("ANIM", True)

    # Tab cycling
    assert handle_key_action("\t", "DASH") == ("POCKET", True)
    assert handle_key_action("\t", "DEV") == ("CONNECT", True)
    assert handle_key_action("\t", "CONNECT") == ("DASH", True)

    # Выход
    assert handle_key_action("q", "DASH") == ("DASH", False)
    assert handle_key_action("exit", "DASH") == ("DASH", False)


def test_tui_render_modes_without_errors() -> None:
    """Проверяет рендеринг всех экранов без исключений."""
    from bridge_client_linux.tui.screens import render_connect_mode

    theme = OFFICIAL_THEME
    render_welcome_screen(theme)
    render_operational_header(theme)
    render_dashboard_mode(theme)
    render_pocket_mode(theme)
    render_notes_mode(theme)
    render_exec_mode(theme)
    render_config_mode(theme)
    render_dev_mode(theme)
    render_connect_mode(theme)
    render_theme_spec(theme)

    for m in ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT", "WELCOME"]:
        render_current_mode(m, theme)


def test_tui_animations_demo() -> None:
    """Проверяет запуск анимаций без ошибок."""
    with patch("time.sleep", return_value=None):
        demo_process_animations(OFFICIAL_THEME, steps=4)


def test_tui_single_pass_runner() -> None:
    """Проверяет single-pass запуск без входа в блокирующий интерактивный цикл."""
    run_interactive_tui(theme=OFFICIAL_THEME, initial_mode="DASH", single_pass=True)


def test_tui_dispatch_action(tmp_path) -> None:
    """Проверяет обработчик команд ввода TUI (EXEC, POCKET, NOTES, DASH)."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # 1. Режим EXEC
    mock_client.exec = AsyncMock(
        return_value=ExecResult(
            exit_code=0,
            stdout="Service running\n",
            stderr="",
            duration_ms=45,
            started_at="2026-09-30T12:00:00Z",
            completed_at="2026-09-30T12:00:01Z",
        )
    )
    state = {
        "exec_history": [],
        "pocket_files": [],
        "notes_list": [],
        "status_msg": "",
    }
    dispatch_tui_action("EXEC", "Get-Service", state, client=mock_client)
    assert len(state["exec_history"]) == 1
    assert state["exec_history"][0][0] == "Get-Service"
    assert "Service running" in state["exec_history"][0][1]
    assert state["exec_history"][0][2] == 0
    assert "Команда выполнена" in state["status_msg"]

    # 2. Режим POCKET: несуществующий файл
    dispatch_tui_action("POCKET", "/nonexistent/path/file.txt", state, client=mock_client)
    assert "Файл не найден" in state["status_msg"]

    # 3. Режим POCKET: существующий файл
    test_f = tmp_path / "valid.txt"
    test_f.write_text("content", encoding="utf-8")
    mock_client.pocket_push_file = AsyncMock(
        return_value=PocketPushResult(
            path="valid.txt",
            offset=0,
            bytes_written=7,
            is_last=True,
            completed=True,
            sha256="abc12345" * 8,
        )
    )
    dispatch_tui_action("POCKET", str(test_f), state, client=mock_client)
    assert len(state["pocket_files"]) == 1
    assert state["pocket_files"][0]["name"] == "valid.txt"
    assert "отправлен в Карман" in state["status_msg"]

    # 4. Режим NOTES
    mock_client.note_send = AsyncMock(
        return_value=NoteDeliveryResult(
            note_id="note-12345678",
            timestamp="2026-09-30T12:00:00Z",
            delivered_to=["WIN-PC"],
            status="delivered",
        )
    )
    dispatch_tui_action("NOTES", "Привет на Windows!", state, client=mock_client)
    assert len(state["notes_list"]) == 1
    assert state["notes_list"][0]["text"] == "Привет на Windows!"
    assert "Заметка отправлена" in state["status_msg"]
