"""
Тесты для bridge_agent_win.cli — клиентские команды P2P управления на Windows (bridge-agent exec/ping/ls/find/send/note).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from bridge_agent_win.cli import (
    _parse_client_flags,
    handle_exec_command,
    handle_find_command,
    handle_ls_command,
    handle_note_command,
    handle_ping_command,
    handle_send_command,
)
from bridge_core.models import (
    ExecResult,
    FsEntry,
    FsFindResult,
    FsListResult,
    NodeOS,
    NodeStatus,
    NoteDeliveryResult,
    NoteEntry,
    NoteHistoryResult,
    NoteStatus,
    PocketPushResult,
    PongResult,
)


class TestWinCliFlagsParser:
    """Тесты парсера флагов командной строки _parse_client_flags."""

    def test_parse_default_flags(self) -> None:
        flags, pos = _parse_client_flags(["echo", "hello"])
        assert flags["json"] is False
        assert flags["host"] is None
        assert flags["port"] is None
        assert flags["admin"] is True
        assert pos == ["echo", "hello"]

    def test_parse_all_connection_flags(self) -> None:
        args = [
            "-h", "192.168.1.100",
            "-p", "9999",
            "-t", "secret_token_123",
            "-n", "remote_linux",
            "--timeout", "45",
            "--dir", "/home/user",
            "--no-admin",
            "-j",
            "ls", "-la",
        ]
        flags, pos = _parse_client_flags(args)
        assert flags["host"] == "192.168.1.100"
        assert flags["port"] == 9999
        assert flags["token"] == "secret_token_123"
        assert flags["node"] == "remote_linux"
        assert flags["timeout"] == 45.0
        assert flags["dir"] == "/home/user"
        assert flags["admin"] is False
        assert flags["json"] is True
        assert pos == ["ls", "-la"]


class TestWinCliCommands:
    """Тесты клиентских команд Windows CLI с моком BridgeClient."""

    def test_handle_exec_command_json_success(self, capsys: Any) -> None:
        fake_result = ExecResult(
            exit_code=0,
            stdout="linux_output_123\n",
            stderr="",
            duration_ms=15,
            started_at="2026-10-11T00:00:00Z",
            completed_at="2026-10-11T00:00:00Z",
        )

        with patch("bridge_core.client.BridgeClient.exec", new_callable=AsyncMock) as mock_exec, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_exec.return_value = fake_result

            handle_exec_command(["echo", "hello", "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["exit_code"] == 0
            assert "linux_output_123" in data["stdout"]

    def test_handle_ping_command_json(self, capsys: Any) -> None:
        fake_pong = PongResult(
            agent_timestamp_us=1000,
            agent_os=NodeOS.LINUX,
            cpu_percent=1.2,
            memory_used_mb=512,
            uptime_seconds=3600,
            status=NodeStatus.READY,
        )

        with patch("bridge_core.client.BridgeClient.ping", new_callable=AsyncMock) as mock_ping, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_ping.return_value = (fake_pong, 4.5)

            handle_ping_command(["--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert len(data["pings"]) == 1
            assert data["pings"][0]["latency_ms"] == 4.5
            assert data["pings"][0]["pong"]["agent_os"] == "linux"

    def test_handle_ls_command_json(self, capsys: Any) -> None:
        fake_ls = FsListResult(
            target_path="/home/user",
            total_entries=1,
            entries=[
                FsEntry(
                    name="file.txt",
                    path="/home/user/file.txt",
                    size_bytes=100,
                    is_dir=False,
                    modified_iso="2026-10-11T00:00:00Z",
                )
            ],
        )

        with patch("bridge_core.client.BridgeClient.fs_list", new_callable=AsyncMock) as mock_ls, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_ls.return_value = fake_ls

            handle_ls_command(["/home/user", "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["total_entries"] == 1
            assert data["entries"][0]["name"] == "file.txt"

    def test_handle_find_command_json(self, capsys: Any) -> None:
        fake_find = FsFindResult(
            pattern="*.py",
            searched_directory="/home/user",
            total_found=1,
            entries=[
                FsEntry(
                    name="main.py",
                    path="/home/user/main.py",
                    size_bytes=256,
                    is_dir=False,
                    modified_iso="2026-10-11T00:00:00Z",
                )
            ],
        )

        with patch("bridge_core.client.BridgeClient.fs_find", new_callable=AsyncMock) as mock_find, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_find.return_value = fake_find

            handle_find_command(["*.py", "-p", "/home/user", "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["total_found"] == 1
            assert data["entries"][0]["name"] == "main.py"

    def test_handle_send_command_json(self, capsys: Any, tmp_path: Path) -> None:
        local_file = tmp_path / "win_send.txt"
        local_file.write_text("Hello remote pocket")

        fake_push = PocketPushResult(
            path="win_send.txt",
            offset=19,
            bytes_written=19,
            is_last=True,
            completed=True,
            sha256="abc",
        )

        with patch("bridge_core.client.BridgeClient.send_pocket_file", new_callable=AsyncMock) as mock_send, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_send.return_value = fake_push

            handle_send_command([str(local_file), "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["completed"] is True
            assert data["path"] == "win_send.txt"

    def test_handle_note_command_json(self, capsys: Any) -> None:
        fake_delivery = NoteDeliveryResult(
            note_id="note_999",
            received_at="2026-10-11T00:00:00Z",
            status=NoteStatus.DELIVERED,
        )

        with patch("bridge_core.client.BridgeClient.send_note", new_callable=AsyncMock) as mock_note, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_note.return_value = fake_delivery

            handle_note_command(["Заметка из Windows", "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["note_id"] == "note_999"
            assert data["status"] == "delivered"

    def test_handle_note_history_json(self, capsys: Any) -> None:
        fake_hist = NoteHistoryResult(
            notes=[
                NoteEntry(
                    note_id="n1",
                    text="Привет из прошлого",
                    timestamp="2026-10-11T00:00:00Z",
                    author_os=NodeOS.LINUX,
                    status=NoteStatus.DELIVERED,
                )
            ],
            total_count=1,
        )

        with patch("bridge_core.client.BridgeClient.get_note_history", new_callable=AsyncMock) as mock_hist, \
             patch("bridge_core.client.BridgeClient.connect", new_callable=AsyncMock), \
             patch("bridge_core.client.BridgeClient.close", new_callable=AsyncMock):
            mock_hist.return_value = fake_hist

            handle_note_command(["history", "--json"])

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["total_count"] == 1
            assert data["notes"][0]["text"] == "Привет из прошлого"
