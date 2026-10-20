"""
Unit tests for Mini HUD interactive loop — Bridge Local v0.3.0.

Тестирует чтение клавиш, omnibar и отрисовку Mini HUD.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

from bridge_client_linux.tui import (
    OFFICIAL_THEME,
    dispatch_omnibar_action,
    read_terminal_key,
    render_mini_hud,
    run_interactive_tui,
)
from bridge_client_linux.tui.app import probe_target_socket


def test_read_terminal_key_empty_timeout() -> None:
    """read_terminal_key возвращает '' при пустом потоке."""
    stream = io.StringIO("")
    result = read_terminal_key(stream, timeout_sec=0.0)
    assert result == ""


def test_read_terminal_key_single_char() -> None:
    """read_terminal_key читает одиночный символ."""
    stream = io.StringIO("a")
    with patch("select.select", return_value=([stream], [], [])):
        result = read_terminal_key(stream, timeout_sec=0.04)
    assert result == "a"


def test_probe_socket_unreachable_port() -> None:
    """probe_target_socket возвращает False для недоступного порта."""
    ok, ms = probe_target_socket("127.0.0.1", 59996, timeout_sec=0.1)
    assert ok is False
    assert ms == 0.0


def test_mini_hud_renders_offline() -> None:
    """Mini HUD рендерится без исключений в режиме OFFLINE."""
    render_mini_hud(OFFICIAL_THEME, {
        "is_online": False,
        "tgt_address": "192.168.0.1:9732",
        "tgt_node": "WIN-PC",
        "last_error": False,
        "pocket_count": 0,
        "input_buffer": "",
    })


def test_mini_hud_renders_online() -> None:
    """Mini HUD рендерится без исключений в режиме ONLINE."""
    render_mini_hud(OFFICIAL_THEME, {
        "is_online": True,
        "latency_ms": 2.1,
        "tgt_address": "192.168.0.1:9732",
        "tgt_node": "WIN-PC",
        "last_error": False,
        "pocket_count": 5,
        "input_buffer": "e dir",
        "last_summary": "[12:00:01] e dir -> exit 0",
    })


def test_mini_hud_renders_error() -> None:
    """Mini HUD рендерится в состоянии ERROR."""
    render_mini_hud(OFFICIAL_THEME, {
        "is_online": False,
        "last_error": True,
        "pocket_count": 0,
        "input_buffer": "",
    })


def test_omnibar_clear() -> None:
    """clear сбрасывает вывод."""
    state: dict[str, Any] = {"last_error": True, "last_output": "old", "last_summary": "x",
                               "tgt_host": "127.0.0.1", "tgt_port": 9732}
    dispatch_omnibar_action("clear", state)
    assert state["last_output"] == ""
    assert state["last_error"] is False


def test_omnibar_quit_sets_flag() -> None:
    """q/quit устанавливают флаг _quit."""
    for cmd in ("q", "quit", "exit", ":q"):
        state: dict[str, Any] = {"last_error": False, "last_output": "",
                                   "tgt_host": "127.0.0.1", "tgt_port": 9732}
        dispatch_omnibar_action(cmd, state)
        assert state.get("_quit") is True, f"Флаг _quit не установлен для команды '{cmd}'"


def test_omnibar_unknown_command() -> None:
    """Неизвестная команда — сообщение об ошибке с подсказкой."""
    state: dict[str, Any] = {"last_error": False, "last_output": "",
                               "tgt_host": "127.0.0.1", "tgt_port": 9732}
    dispatch_omnibar_action("flibbertigibbet", state)
    assert state["last_error"] is True
    assert "Команды:" in state["last_output"]


def test_omnibar_empty_pings_node() -> None:
    """Пустой ввод проверяет связь с узлом."""
    state: dict[str, Any] = {
        "last_error": False,
        "last_output": "",
        "tgt_host": "127.0.0.1",
        "tgt_port": 59995,
    }
    dispatch_omnibar_action("", state)
    assert "ping" in state["last_output"].lower()


def test_omnibar_connect_updates_state() -> None:
    """connect <host:port> обновляет tgt_host и tgt_port."""
    state: dict[str, Any] = {
        "last_error": False, "last_output": "",
        "tgt_host": "192.168.1.1", "tgt_port": 9732,
    }
    with (
        patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(False, 0.0)),
        patch("bridge_core.config.BridgeConfig.update_connection"),
    ):
        dispatch_omnibar_action("connect 10.0.0.7:9800", state)
    assert state["tgt_host"] == "10.0.0.7"
    assert state["tgt_port"] == 9800


def test_single_pass_non_interactive() -> None:
    """run_interactive_tui с single_pass=True не зависает."""
    with patch("bridge_client_linux.tui.app.probe_target_socket", return_value=(False, 0.0)):
        run_interactive_tui(
            theme=OFFICIAL_THEME,
            single_pass=True,
            state={"is_online": False, "pocket_count": 0, "input_buffer": ""},
        )
