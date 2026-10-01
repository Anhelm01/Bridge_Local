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

from typing import Any
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
    # Именованные режимы
    assert handle_key_action("splash", "DASH") == ("SPLASH", True)
    assert handle_key_action("welcome", "DASH") == ("SPLASH", True)
    assert handle_key_action("w", "DASH") == ("SPLASH", True)
    assert handle_key_action("dash", "POCKET") == ("DASH", True)
    assert handle_key_action("pocket", "DASH") == ("POCKET", True)
    assert handle_key_action("notes", "DASH") == ("NOTES", True)
    assert handle_key_action("exec", "DASH") == ("EXEC", True)
    assert handle_key_action("config", "DASH") == ("CONFIG", True)
    assert handle_key_action("dev", "DASH") == ("DEV", True)
    assert handle_key_action("connect", "DASH") == ("CONNECT", True)
    assert handle_key_action("a", "DASH") == ("ANIM", True)

    # Функциональные клавиши F1..F7 сняты (не должны переключать режимы)
    assert handle_key_action("\x1bOP", "DASH") == ("DASH", True)
    assert handle_key_action("\x1bOQ", "DASH") == ("DASH", True)
    assert handle_key_action("f1", "DASH") == ("DASH", True)
    assert handle_key_action("f7", "DASH") == ("DASH", True)

    # Tab cycling (полный круг через сплэш и 7 оперативных окон)
    assert handle_key_action("\t", "SPLASH") == ("DASH", True)
    assert handle_key_action("\t", "DASH") == ("POCKET", True)
    assert handle_key_action("\t", "POCKET") == ("NOTES", True)
    assert handle_key_action("\t", "NOTES") == ("EXEC", True)
    assert handle_key_action("\t", "EXEC") == ("CONFIG", True)
    assert handle_key_action("\t", "CONFIG") == ("DEV", True)
    assert handle_key_action("\t", "DEV") == ("CONNECT", True)
    assert handle_key_action("\t", "CONNECT") == ("SPLASH", True)

    # Shift+Tab обратный цикл
    assert handle_key_action("\x1b[Z", "SPLASH") == ("CONNECT", True)
    assert handle_key_action("\x1b[Z", "DASH") == ("SPLASH", True)

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

    for m in ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT", "WELCOME", "SPLASH"]:
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


def test_tui_connect_mode_parsing_and_client_sync() -> None:
    """Проверяет обработку команд в режиме CONNECT и обновление клиента."""
    mock_client = MagicMock()
    mock_client.update_target = MagicMock()

    state: dict[str, Any] = {
        "tgt_host": "192.168.100.2",
        "tgt_port": 9732,
        "is_online": False,
        "status_msg": "",
    }

    # 1. Проверка команды тестирования связи (test / ping / connect / пустая строка)
    with patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(True, 0.42)):
        dispatch_tui_action("CONNECT", "test", state, client=mock_client)
        assert state["is_online"] is True
        assert state["latency_ms"] == 0.42
        assert "[ОНЛАЙН]" in state["status_msg"]

    # 2. Обновление только IP (сохраняет текущий порт)
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(False, 0.0)),
        patch("bridge_core.config.BridgeConfig.update_connection") as mock_upd,
    ):
        dispatch_tui_action("CONNECT", "192.168.1.55", state, client=mock_client)
        assert state["tgt_host"] == "192.168.1.55"
        assert state["tgt_port"] == 9732
        mock_client.update_target.assert_called_with(host="192.168.1.55", port=9732)
        mock_upd.assert_called_with(host="192.168.1.55", port=9732)

    # 3. Обновление IP и порта через двоеточие
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(True, 1.25)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_tui_action("CONNECT", "10.0.0.12:9800", state, client=mock_client)
        assert state["tgt_host"] == "10.0.0.12"
        assert state["tgt_port"] == 9800
        assert state["is_online"] is True
        mock_client.update_target.assert_called_with(host="10.0.0.12", port=9800)

    # 4. Обновление IP и порта через пробел
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(True, 1.10)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_tui_action("CONNECT", "connect 172.16.0.5 9900", state, client=mock_client)
        assert state["tgt_host"] == "172.16.0.5"
        assert state["tgt_port"] == 9900

    # 5. Обновление только порта (число или :порт)
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(True, 0.9)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_tui_action("CONNECT", "9755", state, client=mock_client)
        assert state["tgt_host"] == "172.16.0.5"
        assert state["tgt_port"] == 9755

    # 6. Сброс на localhost
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(True, 0.2)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_tui_action("CONNECT", "default", state, client=mock_client)
        assert state["tgt_host"] == "127.0.0.1"
        assert state["tgt_port"] == 9732

    # 7. Обновление токена безопасности
    with patch("bridge_core.config.BridgeConfig.update_connection") as mock_upd:
        dispatch_tui_action("CONNECT", "token SecretPsk999", state, client=mock_client)
        mock_client.update_target.assert_called_with(psk_token="SecretPsk999")
        mock_upd.assert_called_with(psk_token="SecretPsk999")
        assert "Ключ безопасности сохранен" in state["status_msg"]


def test_bridge_client_update_target_live() -> None:
    """Проверяет реальную переинициализацию транспорта в BridgeClient.update_target."""
    from bridge_client_linux.client import BridgeClient
    from bridge_core.config import BridgeConfig

    client = BridgeClient(config=BridgeConfig(), host="192.168.1.1", port=9732)
    assert client.host == "192.168.1.1"
    assert client.port == 9732
    assert client.transport.host == "192.168.1.1"
    assert client.transport.port == 9732

    client.update_target(host="10.0.0.99", port=9800, psk_token="NewToken123")
    assert client.host == "10.0.0.99"
    assert client.port == 9800
    assert client.psk_token == "NewToken123"
    assert client.transport.host == "10.0.0.99"
    assert client.transport.port == 9800
    assert client.authenticator is not None
