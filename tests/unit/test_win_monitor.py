"""
Тесты консольного интерактивного монитора агента Windows (AgentConsoleMonitor).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bridge_agent_win.monitor import (
    AgentConsoleMonitor,
    ensure_windows_console_encoding,
    format_bytes,
)
from bridge_agent_win.service import WindowsBridgeService
from bridge_core.config import BridgeConfig


def test_format_bytes() -> None:
    """Проверка человекочитаемого форматирования размера байт."""
    assert format_bytes(500) == "500 Б"
    assert format_bytes(1500) == "1.5 КБ"
    assert format_bytes(1024 * 1024 * 3) == "3.0 МБ"
    assert format_bytes(1024 * 1024 * 1024 * 2) == "2.00 ГБ"


def test_ensure_windows_console_encoding() -> None:
    """Проверка безопасной настройки кодировки Windows."""
    with patch("sys.platform", "win32"), patch("os.system") as mock_sys:
        ensure_windows_console_encoding()
        mock_sys.assert_called_once_with("chcp 65001 >nul")


def test_monitor_print_banner() -> None:
    """Проверка вывода информационного баннера монитора."""
    cfg = BridgeConfig.load()
    monitor = AgentConsoleMonitor(cfg)
    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush"):
        monitor.print_banner()
        assert mock_write.called
        output = "".join(call[0][0] for call in mock_write.call_args_list)
        assert "BRIDGE LOCAL" in output
        assert "АГЕНТ WINDOWS" in output
        assert "Команды оператора" in output


def test_monitor_events_formatting() -> None:
    """Проверка форматирования всех типов событий."""
    cfg = BridgeConfig.load()
    monitor = AgentConsoleMonitor(cfg)

    with patch.object(monitor, "print_line") as mock_print:
        # 1. Записка
        monitor.on_event(
            "note_received",
            {
                "source_node": "workstation-linux",
                "client_ip": "192.168.100.1",
                "text": "Hello Windows!\nSecond line",
            },
        )
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("[NOTE]" in line for line in lines)
        assert any("Hello Windows!" in line for line in lines)

        # 2. Файл получен (push)
        mock_print.reset_mock()
        monitor.on_event(
            "file_received",
            {
                "path": "test.zip",
                "bytes": 2048,
                "client_ip": "192.168.100.1",
            },
        )
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any(
            "[POCKET]" in line and "[ВХОДЯЩИЙ]" in line and "test.zip" in line for line in lines
        )

        # 3. Файл передан (pull)
        mock_print.reset_mock()
        monitor.on_event(
            "file_requested",
            {
                "path": "report.pdf",
                "total_size": 1048576,
                "client_ip": "192.168.100.1",
            },
        )
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any(
            "[POCKET]" in line and "[ИСХОДЯЩИЙ]" in line and "report.pdf" in line for line in lines
        )

        # 4. Команда exec успешно
        mock_print.reset_mock()
        monitor.on_event(
            "exec_completed",
            {
                "command": "dir",
                "exit_code": 0,
                "stdout": "Volume in drive C",
                "stderr": "",
                "duration_ms": 15,
                "working_dir": r"C:\BridgeLocal",
                "client_ip": "192.168.100.1",
            },
        )
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("[EXEC]" in line and "[OK]" in line for line in lines)
        assert any("Volume in drive C" in line for line in lines)

        # 5. Команда exec с ошибкой
        mock_print.reset_mock()
        monitor.on_event(
            "exec_completed",
            {
                "command": "bad_cmd",
                "exit_code": 1,
                "stdout": "",
                "stderr": "Command not found",
                "duration_ms": 10,
                "working_dir": r"C:\BridgeLocal",
                "client_ip": "192.168.100.1",
            },
        )
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("[EXEC]" in line and "[FAIL: 1]" in line for line in lines)
        assert any("Command not found" in line for line in lines)


@pytest.mark.asyncio
async def test_monitor_handle_commands(tmp_path) -> None:
    """Проверка интерактивных команд оператора (help, status, notes, pocket, reset, exit)."""
    cfg = BridgeConfig.load()
    cfg.pocket.path = str(tmp_path / "pocket")
    service = WindowsBridgeService(cfg)
    monitor = AgentConsoleMonitor(cfg)

    # 1. help
    with patch.object(monitor, "print_line") as mock_print:
        await monitor.handle_command("help", service)
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("Доступные команды" in line for line in lines)

    # 2. status
    with patch.object(monitor, "print_line") as mock_print:
        await monitor.handle_command("status", service)
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("СТАТУС АГЕНТА" in line for line in lines)

    # 3. reset (сброс CWD)
    service.executor.current_working_dir = r"C:\SomeSubdir"
    with patch.object(monitor, "print_line") as mock_print:
        await monitor.handle_command("reset", service)
        assert service.executor.current_working_dir is None
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("Рабочая директория PowerShell сброшена" in line for line in lines)

    # 4. notes
    with patch.object(monitor, "print_line") as mock_print:
        await monitor.handle_command("notes", service)
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("ПОСЛЕДНИЕ ЗАМЕТКИ" in line for line in lines)

    # 5. pocket
    with patch.object(monitor, "print_line") as mock_print:
        await monitor.handle_command("pocket", service)
        lines = [c[0][0] for c in mock_print.call_args_list if c[0]]
        assert any("ФАЙЛЫ В КАРМАНЕ" in line for line in lines)

    # 6. exit
    assert not service._stop_event.is_set()
    await monitor.handle_command("q", service)
    assert service._stop_event.is_set()


@pytest.mark.asyncio
async def test_service_emits_monitor_events(tmp_path) -> None:
    """Проверка интеграции WindowsBridgeService с колбэком монитора."""
    cfg = BridgeConfig.load()
    cfg.pocket.path = str(tmp_path / "pocket")
    cfg.connection.psk_token = ""
    service = WindowsBridgeService(cfg)

    events: list[tuple[str, dict]] = []
    service.monitor_callback = lambda ev, data: events.append((ev, data))

    session_info = {"session_id": "test_sess", "peername": ("192.168.100.1", 54321)}

    # 1. Ping
    await service._handle_ping({}, session_info)
    assert any(e[0] == "client_ping" and e[1]["client_ip"] == "192.168.100.1" for e in events)

    # 2. Exec
    exec_params = {"command": "echo 'Hello Monitor'"}
    await service._handle_exec(exec_params, session_info)
    assert any(
        e[0] == "exec_completed" and "echo 'Hello Monitor'" in e[1]["command"] for e in events
    )

    # 3. Notes send
    note_params = {"text": "Note to monitor test", "author_os": "linux"}
    await service._handle_notes_send(note_params, session_info)
    assert any(
        e[0] == "note_received" and e[1]["text"] == "Note to monitor test" for e in events
    )
