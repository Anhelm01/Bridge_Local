"""
Unit tests for bridge_agent_win.tray (Windows System Tray Integration).

Verifies:
  - scan_pocket_statistics (filtering of .notes, logs, and .part files).
  - check_port_listening (open vs closed TCP port).
  - Service status checking and control (SCM / sc.exe fallback).
  - BridgeTrayIcon initialization, status aggregation, and command routing.
  - Explorer folder launching and clipboard copying.
  - Standalone agent process lifecycle (start / stop).
  - CLI integration for bridge-agent tray command.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bridge_agent_win.cli import main as cli_main
from bridge_agent_win.tray import (
    IDM_COPY_ADDRESS,
    IDM_EXIT_TRAY,
    IDM_OPEN_LOGS,
    IDM_OPEN_NOTES,
    IDM_OPEN_POCKET,
    IDM_POCKET_INFO,
    IDM_RESTART_SERVICE,
    IDM_START_AGENT,
    IDM_START_SERVICE,
    IDM_STOP_AGENT,
    IDM_STOP_SERVICE,
    BridgeTrayIcon,
    TrayAgentStatus,
    check_port_listening,
    check_windows_service_status,
    copy_text_to_clipboard,
    open_directory_in_explorer,
    scan_pocket_statistics,
    start_windows_service,
    stop_windows_service,
)
from bridge_core.config import BridgeConfig, ConnectionConfig, PocketConfig


def test_scan_pocket_statistics_empty(tmp_path: Path) -> None:
    """Проверяет сканирование пустого каталога кармана."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()
    cnt, sz = scan_pocket_statistics(pocket_dir)
    assert cnt == 0
    assert sz == 0


def test_scan_pocket_statistics_filters_internal(tmp_path: Path) -> None:
    """Проверяет, что сканирование исключает .notes, logs и .part файлы."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()

    # Пользовательские файлы
    (pocket_dir / "doc.txt").write_text("Hello World", encoding="utf-8")
    (pocket_dir / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # Внутренние каталоги и временные файлы, которые должны игнорироваться
    notes_dir = pocket_dir / ".notes"
    notes_dir.mkdir()
    (notes_dir / "notes.jsonl").write_text('{"msg": 1}\n', encoding="utf-8")

    logs_dir = pocket_dir / "logs"
    logs_dir.mkdir()
    (logs_dir / "2026-10-02.jsonl").write_text('{"log": 1}\n', encoding="utf-8")

    (pocket_dir / "download.iso.part").write_bytes(b"temp data")
    (pocket_dir / ".hidden_temp").write_text("hidden", encoding="utf-8")

    cnt, sz = scan_pocket_statistics(pocket_dir)
    assert cnt == 2
    assert sz == len(b"Hello World") + 8


def test_check_port_listening() -> None:
    """Проверяет определение открытого и закрытого TCP порта."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    try:
        assert check_port_listening("127.0.0.1", port) is True
    finally:
        srv.close()

    assert check_port_listening("127.0.0.1", port) is False


def test_check_windows_service_status_fallback() -> None:
    """Проверяет корректность возврата статуса при отсутствии win32service."""
    with patch("bridge_agent_win.tray.HAS_WIN32SERVICE", False):
        res = check_windows_service_status("BridgeLocalAgent")
        assert res is None


def test_check_windows_service_status_success() -> None:
    """Проверяет получение статуса службы при доступном win32serviceutil."""
    mock_util = MagicMock()
    mock_util.QueryServiceStatus.return_value = (0, 4, 0, 0, 0, 0, 0)
    with (
        patch("bridge_agent_win.tray.HAS_WIN32SERVICE", True),
        patch("bridge_agent_win.tray.win32serviceutil", mock_util),
    ):
        res = check_windows_service_status("BridgeLocalAgent")
        assert res == 4


def test_start_and_stop_windows_service_util() -> None:
    """Проверяет управление службой через win32serviceutil."""
    mock_util = MagicMock()
    with (
        patch("bridge_agent_win.tray.HAS_WIN32SERVICE", True),
        patch("bridge_agent_win.tray.win32serviceutil", mock_util),
    ):
        assert start_windows_service("BridgeLocalAgent") is True
        mock_util.StartService.assert_called_once_with("BridgeLocalAgent")

        assert stop_windows_service("BridgeLocalAgent") is True
        mock_util.StopService.assert_called_once_with("BridgeLocalAgent")


def test_start_and_stop_windows_service_sc_fallback() -> None:
    """Проверяет fallback на вызов sc.exe при отсутствии win32service."""
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    with (
        patch("bridge_agent_win.tray.HAS_WIN32SERVICE", False),
        patch("subprocess.run", mock_run),
    ):
        assert start_windows_service("BridgeLocalAgent") is True
        assert stop_windows_service("BridgeLocalAgent") is True
        assert mock_run.call_count == 2


def test_open_directory_in_explorer(tmp_path: Path) -> None:
    """Проверяет вызов открытия проводника."""
    target_dir = tmp_path / "test_folder"
    if sys.platform == "win32":
        with patch("os.startfile") as mock_start:
            assert open_directory_in_explorer(target_dir) is True
            mock_start.assert_called_once_with(str(target_dir.resolve()))
    else:
        with patch("subprocess.Popen") as mock_popen:
            assert open_directory_in_explorer(target_dir) is True
            mock_popen.assert_called_once()


def test_copy_text_to_clipboard() -> None:
    """Проверяет запись в буфер обмена."""
    with patch("sys.platform", "linux"):
        assert copy_text_to_clipboard("test_addr") is False

    mock_cb = MagicMock()
    with (
        patch("sys.platform", "win32"),
        patch("bridge_agent_win.tray.HAS_WIN32GUI", True),
        patch("bridge_agent_win.tray.win32clipboard", mock_cb),
    ):
        assert copy_text_to_clipboard("192.168.1.10:9732") is True
        mock_cb.SetClipboardText.assert_called_once()


def test_bridge_tray_icon_status(tmp_path: Path) -> None:
    """Проверяет сбор статуса в BridgeTrayIcon."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()
    (pocket_dir / "file.bin").write_bytes(b"12345")

    cfg = BridgeConfig(
        pocket=PocketConfig(path=str(pocket_dir)),
        connection=ConnectionConfig(host="127.0.0.1", port=9999),
    )
    tray = BridgeTrayIcon(cfg)

    with (
        patch("bridge_agent_win.tray.check_port_listening", return_value=True),
        patch("bridge_agent_win.tray.check_windows_service_status", return_value=None),
    ):
        status = tray.get_status()
        assert isinstance(status, TrayAgentStatus)
        assert status.is_online is True
        assert status.is_port_listening is True
        assert status.is_service_running is False
        assert status.file_count == 1
        assert status.total_size_bytes == 5
        assert status.status_summary == "ONLINE (Standalone)"


def test_bridge_tray_icon_actions_dispatch(tmp_path: Path) -> None:
    """Проверяет диспетчеризацию действий контекстного меню."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()
    cfg = BridgeConfig(pocket=PocketConfig(path=str(pocket_dir)))
    tray = BridgeTrayIcon(cfg)

    with (
        patch.object(tray, "open_pocket") as m_pock,
        patch.object(tray, "open_logs") as m_logs,
        patch.object(tray, "open_notes") as m_notes,
        patch.object(tray, "copy_connection_address") as m_copy,
        patch.object(tray, "start_service") as m_start_svc,
        patch.object(tray, "stop_service") as m_stop_svc,
        patch.object(tray, "restart_service") as m_restart_svc,
        patch.object(tray, "start_standalone_agent") as m_start_agt,
        patch.object(tray, "stop_standalone_agent") as m_stop_agt,
        patch.object(tray, "stop") as m_stop,
    ):
        tray._dispatch_command(IDM_OPEN_POCKET)
        m_pock.assert_called_once()

        tray._dispatch_command(IDM_POCKET_INFO)
        assert m_pock.call_count == 2

        tray._dispatch_command(IDM_OPEN_LOGS)
        m_logs.assert_called_once()

        tray._dispatch_command(IDM_OPEN_NOTES)
        m_notes.assert_called_once()

        tray._dispatch_command(IDM_COPY_ADDRESS)
        m_copy.assert_called_once()

        tray._dispatch_command(IDM_START_SERVICE)
        m_start_svc.assert_called_once()

        tray._dispatch_command(IDM_STOP_SERVICE)
        m_stop_svc.assert_called_once()

        tray._dispatch_command(IDM_RESTART_SERVICE)
        m_restart_svc.assert_called_once()

        tray._dispatch_command(IDM_START_AGENT)
        m_start_agt.assert_called_once()

        tray._dispatch_command(IDM_STOP_AGENT)
        m_stop_agt.assert_called_once()

        tray._dispatch_command(IDM_EXIT_TRAY)
        m_stop.assert_called_once()


def test_bridge_tray_icon_standalone_lifecycle(tmp_path: Path) -> None:
    """Проверяет управление процессом автономного агента."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir()
    cfg = BridgeConfig(pocket=PocketConfig(path=str(pocket_dir)))
    tray = BridgeTrayIcon(cfg)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        assert tray.start_standalone_agent() is True
        assert tray._agent_process is mock_proc

        assert tray.stop_standalone_agent() is True
        mock_proc.terminate.assert_called_once()
        assert tray._agent_process is None


def test_cli_bridge_agent_tray_invocation() -> None:
    """Проверяет вызов bridge-agent tray из CLI."""
    mock_tray = MagicMock()
    with patch("bridge_agent_win.tray.BridgeTrayIcon", return_value=mock_tray):
        cli_main(["tray"])
        mock_tray.run.assert_called_once()


def test_cli_bridge_agent_help_contains_tray(capsys: pytest.CaptureFixture[str]) -> None:
    """Проверяет наличие команды tray в справке bridge-agent --help."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "tray" in captured.out
