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

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bridge_client_linux.tui import (
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
    """Проверяет переключение по всем F1..F8, Tab, Shift+Tab и игнорирование букв."""
    # 1. Прямая адресация F1..F8 через escape-последовательности и названия
    assert handle_key_action("\x1bOP", "DASH") == ("SPLASH", True)
    assert handle_key_action("\x1b[[A", "DASH") == ("SPLASH", True)
    assert handle_key_action("\x1b[11~", "DASH") == ("SPLASH", True)
    assert handle_key_action("f1", "DASH") == ("SPLASH", True)

    assert handle_key_action("\x1bOQ", "SPLASH") == ("DASH", True)
    assert handle_key_action("\x1b[[B", "SPLASH") == ("DASH", True)
    assert handle_key_action("\x1b[12~", "SPLASH") == ("DASH", True)
    assert handle_key_action("f2", "SPLASH") == ("DASH", True)

    assert handle_key_action("\x1bOR", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1b[[C", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1b[13~", "DASH") == ("POCKET", True)
    assert handle_key_action("f3", "DASH") == ("POCKET", True)

    assert handle_key_action("\x1bOS", "DASH") == ("NOTES", True)
    assert handle_key_action("\x1b[[D", "DASH") == ("NOTES", True)
    assert handle_key_action("\x1b[14~", "DASH") == ("NOTES", True)
    assert handle_key_action("f4", "DASH") == ("NOTES", True)

    assert handle_key_action("\x1b[15~", "DASH") == ("EXEC", True)
    assert handle_key_action("f5", "DASH") == ("EXEC", True)

    assert handle_key_action("\x1b[17~", "DASH") == ("CONFIG", True)
    assert handle_key_action("f6", "DASH") == ("CONFIG", True)

    assert handle_key_action("\x1b[18~", "DASH") == ("DEV", True)
    assert handle_key_action("f7", "DASH") == ("DEV", True)

    assert handle_key_action("\x1b[19~", "DASH") == ("CONNECT", True)
    assert handle_key_action("f8", "DASH") == ("CONNECT", True)

    # 2. Именованные строковые команды режимов
    assert handle_key_action("splash", "DASH") == ("SPLASH", True)
    assert handle_key_action("welcome", "DASH") == ("SPLASH", True)
    assert handle_key_action("dash", "POCKET") == ("DASH", True)
    assert handle_key_action("pocket", "DASH") == ("POCKET", True)
    assert handle_key_action("notes", "DASH") == ("NOTES", True)
    assert handle_key_action("exec", "DASH") == ("EXEC", True)
    assert handle_key_action("config", "DASH") == ("CONFIG", True)
    assert handle_key_action("dev", "DASH") == ("DEV", True)
    assert handle_key_action("connect", "DASH") == ("CONNECT", True)

    # 3. ОДИНОЧНЫЕ БУКВЫ НЕ ДОЛЖНЫ МЕНЯТЬ РЕЖИМ И НЕ ДОЛЖНЫ ЗАКРЫВАТЬ TUI
    for letter in ("w", "W", "q", "Q", "r", "R", "a", "A", "c", "C", "d", "p", "n", "e"):
        assert handle_key_action(letter, "DASH") == ("DASH", True)
        assert handle_key_action(letter, "POCKET") == ("POCKET", True)

    # 4. Tab cycling (полный круг через сплэш и 7 оперативных окон)
    assert handle_key_action("\t", "SPLASH") == ("DASH", True)
    assert handle_key_action("\t", "DASH") == ("POCKET", True)
    assert handle_key_action("\t", "POCKET") == ("NOTES", True)
    assert handle_key_action("\t", "NOTES") == ("EXEC", True)
    assert handle_key_action("\t", "EXEC") == ("CONFIG", True)
    assert handle_key_action("\t", "CONFIG") == ("DEV", True)
    assert handle_key_action("\t", "DEV") == ("CONNECT", True)
    assert handle_key_action("\t", "CONNECT") == ("SPLASH", True)

    # 5. Shift+Tab обратный цикл
    assert handle_key_action("\x1b[Z", "SPLASH") == ("CONNECT", True)
    assert handle_key_action("\x1b[Z", "DASH") == ("SPLASH", True)
    assert handle_key_action("shift+tab", "DASH") == ("SPLASH", True)

    # 6. Выход только по Ctrl+C, Ctrl+Q, exit, quit, :q
    assert handle_key_action("\x03", "DASH") == ("DASH", False)
    assert handle_key_action("\x11", "DASH") == ("DASH", False)
    assert handle_key_action("exit", "DASH") == ("DASH", False)
    assert handle_key_action("quit", "DASH") == ("DASH", False)
    assert handle_key_action(":q", "DASH") == ("DASH", False)

    # 7. Цифры 1..8 (прямой переход без F-клавиш)
    assert handle_key_action("1", "DASH") == ("SPLASH", True)
    assert handle_key_action("2", "SPLASH") == ("DASH", True)
    assert handle_key_action("3", "DASH") == ("POCKET", True)
    assert handle_key_action("4", "DASH") == ("NOTES", True)
    assert handle_key_action("5", "DASH") == ("EXEC", True)
    assert handle_key_action("6", "DASH") == ("CONFIG", True)
    assert handle_key_action("7", "DASH") == ("DEV", True)
    assert handle_key_action("8", "DASH") == ("CONNECT", True)

    # 8. Alt+1..Alt+8
    assert handle_key_action("\x1b1", "DASH") == ("SPLASH", True)
    assert handle_key_action("\x1b3", "DASH") == ("POCKET", True)
    assert handle_key_action("\x1b8", "DASH") == ("CONNECT", True)

    # 9. Стрелки Влево (←) и Вправо (→) и скобки [ / ]
    assert handle_key_action("\x1b[D", "DASH") == ("SPLASH", True)
    assert handle_key_action("left", "DASH") == ("SPLASH", True)
    assert handle_key_action("[", "DASH") == ("SPLASH", True)
    assert handle_key_action("\x1b[C", "DASH") == ("POCKET", True)
    assert handle_key_action("right", "DASH") == ("POCKET", True)
    assert handle_key_action("]", "DASH") == ("POCKET", True)

    # 10. Двоеточия :1..:8
    assert handle_key_action(":1", "DASH") == ("SPLASH", True)
    assert handle_key_action(":2", "SPLASH") == ("DASH", True)
    assert handle_key_action(":8", "DASH") == ("CONNECT", True)



def test_tui_scroll_actions() -> None:
    """Проверяет работу скролла (Arrow Up/Down, Page Up/Down, Home, End) и ограничение смещения."""
    state: dict[str, Any] = {
        "pocket_files": [{"name": f"f_{i}.txt"} for i in range(25)],
        "notes_list": [{"text": f"n_{i}"} for i in range(20)],
        "scroll_offsets": {"POCKET": 0, "NOTES": 0},
    }

    # 1. Скролл вниз на 1 строку в POCKET
    assert handle_scroll_action("\x1b[B", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 1

    # 2. Скролл вниз на страницу (10 строк)
    assert handle_scroll_action("\x1b[6~", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 11

    # 3. Переход в конец (max_offset = 25 - 10 = 15)
    assert handle_scroll_action("\x1b[F", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 15

    # 4. Попытка скролла ниже max_offset не превышает границу
    assert handle_scroll_action("\x1b[B", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 15

    # 5. Скролл вверх на 1 строку
    assert handle_scroll_action("\x1b[A", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 14

    # 6. Скролл вверх на страницу
    assert handle_scroll_action("\x1b[5~", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 4

    # 7. Переход в начало (Home)
    assert handle_scroll_action("\x1b[H", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 0

    # 8. Попытка скролла выше 0 не уходит в отрицательные числа
    assert handle_scroll_action("\x1b[A", "POCKET", state) is True
    assert state["scroll_offsets"]["POCKET"] == 0

    # 9. Не-скролл клавиша возвращает False
    assert handle_scroll_action("a", "POCKET", state) is False
    assert handle_scroll_action("\t", "POCKET", state) is False


def test_tui_escape_sequence_reader() -> None:
    """Проверяет парсинг escape-последовательностей без обрезания символов."""
    # F1..F8
    assert read_terminal_key(io.StringIO("\x1bOP")) == "\x1bOP"
    assert read_terminal_key(io.StringIO("\x1b[[A")) == "\x1b[[A"
    assert read_terminal_key(io.StringIO("\x1b[11~")) == "\x1b[11~"
    assert read_terminal_key(io.StringIO("\x1b[15~")) == "\x1b[15~"
    assert read_terminal_key(io.StringIO("\x1b[17~")) == "\x1b[17~"
    assert read_terminal_key(io.StringIO("\x1b[18~")) == "\x1b[18~"
    assert read_terminal_key(io.StringIO("\x1b[19~")) == "\x1b[19~"

    # Скролл: Arrow Up/Down, Page Up/Down, Home, End
    assert read_terminal_key(io.StringIO("\x1b[A")) == "\x1b[A"
    assert read_terminal_key(io.StringIO("\x1b[B")) == "\x1b[B"
    assert read_terminal_key(io.StringIO("\x1b[5~")) == "\x1b[5~"
    assert read_terminal_key(io.StringIO("\x1b[6~")) == "\x1b[6~"
    assert read_terminal_key(io.StringIO("\x1b[H")) == "\x1b[H"
    assert read_terminal_key(io.StringIO("\x1b[1~")) == "\x1b[1~"
    assert read_terminal_key(io.StringIO("\x1b[F")) == "\x1b[F"
    assert read_terminal_key(io.StringIO("\x1b[4~")) == "\x1b[4~"

    # Shift+Tab
    assert read_terminal_key(io.StringIO("\x1b[Z")) == "\x1b[Z"

    # Обычный символ
    assert read_terminal_key(io.StringIO("a")) == "a"
    assert read_terminal_key(io.StringIO("Hello")) == "H"


def test_tui_render_modes_without_errors() -> None:
    """Проверяет рендеринг всех экранов без исключений со скроллом и индикаторами."""
    from bridge_client_linux.tui.screens import render_connect_mode

    theme = OFFICIAL_THEME

    state = {
        "pocket_files": [
            {"name": f"file_{i}.txt", "size": "100 B", "status": "SYNCED"} for i in range(25)
        ],
        "notes_list": [
            {"time": "12:00:00", "author": "NODE", "text": f"Note {i}"} for i in range(20)
        ],
        "exec_history": [(f"cmd {i}", f"output {i}", 0) for i in range(15)],
        "dev_logs": [f"TRACE event {i}" for i in range(20)],
        "scroll_offsets": {"POCKET": 5, "NOTES": 3, "EXEC": 2, "DEV": 4},
        "is_online": True,
    }

    render_welcome_screen(theme, state)
    render_operational_header(theme, state)
    render_dashboard_mode(theme, state)
    render_pocket_mode(theme, state)
    render_notes_mode(theme, state)
    render_exec_mode(theme, state)
    render_config_mode(theme, state)
    render_dev_mode(theme, state)
    render_connect_mode(theme, state)
    render_theme_spec(theme)

    for m in ["DASH", "POCKET", "NOTES", "EXEC", "CONFIG", "DEV", "CONNECT", "WELCOME", "SPLASH"]:
        render_current_mode(m, theme, state)


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
