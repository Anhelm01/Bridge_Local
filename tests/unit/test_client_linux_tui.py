"""
Unit tests for Mini HUD Bridge Local v0.3.0.

Тестирует единственный интерфейс: Micro/Mini HUD.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

from bridge_client_linux.tui import (
    OFFICIAL_THEME,
    dispatch_omnibar_action,
    dispatch_tui_action,
    get_live_context,
    render_current_mode,
    render_mini_hud,
    run_interactive_tui,
)
from bridge_client_linux.tui.app import probe_target_socket, read_terminal_key


def test_official_theme_attributes() -> None:
    """Проверяет атрибуты официальной темы Titanium Vivid."""
    assert OFFICIAL_THEME.name == "Titanium Vivid / Cyber-Industrial"
    assert OFFICIAL_THEME.primary == "#FFFFFF"
    assert OFFICIAL_THEME.secondary == "#7D8590"
    assert OFFICIAL_THEME.text == "#FFFFFF"
    assert OFFICIAL_THEME.blue == "#00D2FF"
    assert OFFICIAL_THEME.green == "#00FF66"
    assert OFFICIAL_THEME.amber == "#FFB800"
    assert OFFICIAL_THEME.purple == "#C084FC"
    assert OFFICIAL_THEME.red == "#FF3366"


def test_render_mini_hud_offline() -> None:
    """Mini HUD корректно рендерится в режиме OFFLINE."""
    state = {
        "is_online": False,
        "tgt_address": "192.168.100.6:9732",
        "tgt_node": "WIN-PC",
        "last_error": False,
        "pocket_count": 0,
        "input_buffer": "",
    }
    render_mini_hud(OFFICIAL_THEME, state)


def test_render_mini_hud_online() -> None:
    """Mini HUD корректно рендерится в режиме ONLINE."""
    state = {
        "is_online": True,
        "latency_ms": 4.5,
        "tgt_address": "192.168.100.6:9732",
        "tgt_node": "WIN-PC",
        "last_error": False,
        "pocket_count": 3,
        "input_buffer": "note Hello",
    }
    render_mini_hud(OFFICIAL_THEME, state)


def test_render_mini_hud_error() -> None:
    """Mini HUD корректно рендерится в состоянии ERROR."""
    state = {
        "is_online": False,
        "tgt_address": "192.168.100.6:9732",
        "last_error": True,
        "pocket_count": 1,
        "input_buffer": "",
    }
    render_mini_hud(OFFICIAL_THEME, state)


def test_render_current_mode_always_mini() -> None:
    """render_current_mode всегда рисует Mini HUD независимо от mode."""
    state = {"is_online": False, "pocket_count": 0, "input_buffer": ""}
    for mode in ("MINI", "MAIN", "DASH", "POCKET", "NOTES", "whatever"):
        render_current_mode(mode, OFFICIAL_THEME, state)


def test_read_terminal_key_timeout() -> None:
    """read_terminal_key возвращает '' при пустом потоке (таймаут)."""
    stream = io.StringIO("")
    result = read_terminal_key(stream, timeout_sec=0.0)
    assert result == ""


def test_probe_target_socket_offline() -> None:
    """probe_target_socket возвращает False для закрытого порта."""
    is_online, latency = probe_target_socket("127.0.0.1", 59997, timeout_sec=0.1)
    assert is_online is False
    assert latency == 0.0


def test_dispatch_omnibar_unknown_command() -> None:
    """Неизвестная команда вызывает подсказку об ошибке."""
    state: dict[str, Any] = {
        "last_error": False,
        "last_output": "",
        "tgt_host": "127.0.0.1",
        "tgt_port": 9732,
    }
    dispatch_omnibar_action("some_totally_unknown_xyz", state, client=None)
    assert state["last_error"] is True
    assert "Неизвестно" in state["last_output"]


def test_dispatch_omnibar_clear() -> None:
    """Команда clear очищает last_output и last_summary."""
    state: dict[str, Any] = {
        "last_error": True,
        "last_output": "Some previous output",
        "last_summary": "prev",
        "tgt_host": "127.0.0.1",
        "tgt_port": 9732,
    }
    dispatch_omnibar_action("clear", state, client=None)
    assert state["last_output"] == ""
    assert state["last_summary"] == ""
    assert state["last_error"] is False


def test_dispatch_omnibar_quit_flag() -> None:
    """Команда q/quit устанавливает флаг _quit."""
    state: dict[str, Any] = {"last_error": False, "last_output": "", "tgt_host": "127.0.0.1", "tgt_port": 9732}
    dispatch_omnibar_action("q", state, client=None)
    assert state.get("_quit") is True

    state2: dict[str, Any] = {"last_error": False, "last_output": "", "tgt_host": "127.0.0.1", "tgt_port": 9732}
    dispatch_omnibar_action("quit", state2, client=None)
    assert state2.get("_quit") is True


def test_dispatch_tui_action_delegates_to_omnibar() -> None:
    """dispatch_tui_action всегда направляет в omnibar."""
    state: dict[str, Any] = {"last_error": False, "last_output": "", "tgt_host": "127.0.0.1", "tgt_port": 9732}
    dispatch_tui_action("POCKET", "clear", state, client=None)
    assert state["last_output"] == ""
    assert state["last_error"] is False


def test_dispatch_omnibar_connect_parses_address() -> None:
    """connect обновляет tgt_host и tgt_port в state."""
    state: dict[str, Any] = {
        "last_error": False,
        "last_output": "",
        "tgt_host": "192.168.1.1",
        "tgt_port": 9732,
    }
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(False, 0.0)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_omnibar_action("connect 10.0.0.50:9800", state, client=None)
    assert state["tgt_host"] == "10.0.0.50"
    assert state["tgt_port"] == 9800


def test_run_interactive_tui_single_pass() -> None:
    """single_pass=True рисует один кадр и возвращает управление."""
    with patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(False, 0.0)):
        run_interactive_tui(
            theme=OFFICIAL_THEME,
            single_pass=True,
            state={"is_online": False, "pocket_count": 0, "input_buffer": ""},
        )


def test_get_live_context_defaults() -> None:
    """get_live_context возвращает корректные ключи по умолчанию."""
    ctx = get_live_context({"is_online": False})
    assert "tgt_host" in ctx
    assert "tgt_port" in ctx
    assert "tgt_address" in ctx
    assert "is_online" in ctx
    assert "pocket_count" in ctx
    assert isinstance(ctx["pocket_count"], int)
