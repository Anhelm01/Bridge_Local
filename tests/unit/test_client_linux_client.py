"""
Unit tests for BridgeClient (high-level Linux client engine).
Verifies RPC roundtrips, PSK authentication, Pocket file sync, Notes, and error mappings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge_agent_win.service import WindowsBridgeService
from bridge_client_linux.client import BridgeClient
from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeNetworkError,
)
from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    PocketConfig,
)
from bridge_core.models import NodeOS, NodeStatus


@pytest.fixture
async def test_service(tmp_path: Path):
    """Запускает WindowsBridgeService на случайном порту."""
    pocket_dir = tmp_path / "pocket_server"
    pocket_dir.mkdir(parents=True, exist_ok=True)

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    service = WindowsBridgeService(cfg)
    await service.start()

    assert service.server._server is not None
    port = service.server._server.sockets[0].getsockname()[1]

    try:
        yield service, port, pocket_dir
    finally:
        await service.stop()


@pytest.fixture
async def auth_service(tmp_path: Path):
    """Запускает WindowsBridgeService с PSK-аутентификацией."""
    pocket_dir = tmp_path / "pocket_auth_server"
    pocket_dir.mkdir(parents=True, exist_ok=True)

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0, psk_token="secret-key-1234"),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    service = WindowsBridgeService(cfg)
    await service.start()

    assert service.server._server is not None
    port = service.server._server.sockets[0].getsockname()[1]

    try:
        yield service, port, pocket_dir
    finally:
        await service.stop()


class TestBridgeClient:
    """Набор тестов для высокоуровневого клиента BridgeClient."""

    @pytest.mark.asyncio
    async def test_ping(self, test_service, tmp_path: Path):
        _, port, _ = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            pong, latency_ms = await client.ping(client_os=NodeOS.LINUX)
            assert pong.status in (NodeStatus.READY, NodeStatus.BUSY)
            assert latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_exec_echo(self, test_service, tmp_path: Path):
        _, port, _ = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            res = await client.exec("echo bridge-exec-test")
            assert res.exit_code == 0
            assert "bridge-exec-test" in res.stdout
            assert res.duration_ms >= 0
            assert not res.timed_out

    @pytest.mark.asyncio
    async def test_pocket_push_and_pull(self, test_service, tmp_path: Path):
        _, port, server_pocket = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        # 1. Создаем локальный файл и пушим его
        test_file = local_pocket / "push_me.txt"
        test_file.write_text("Hello from Linux Client Pocket!", encoding="utf-8")

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            res = await client.pocket_push_file(test_file)
            assert res.completed is True
            assert (server_pocket / "push_me.txt").exists()
            content = (server_pocket / "push_me.txt").read_text(encoding="utf-8")
            assert content == "Hello from Linux Client Pocket!"

            # 2. Создаем файл на сервере и пуллим его
            server_file = server_pocket / "from_server.bin"
            server_file.write_bytes(b"\x00\x01\x02\x03" * 1024)

            dest_local = await client.pocket_pull_file("from_server.bin")
            assert dest_local.exists()
            assert dest_local.read_bytes() == b"\x00\x01\x02\x03" * 1024

    @pytest.mark.asyncio
    async def test_pocket_sync_bidirectional(self, test_service, tmp_path: Path):
        _, port, server_pocket = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        (local_pocket / "doc_local.txt").write_text("local content", encoding="utf-8")
        (server_pocket / "doc_remote.txt").write_text("remote content", encoding="utf-8")

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            summary = await client.pocket_sync(direction="both")
            assert len(summary.errors) == 0
            assert "doc_remote.txt" in summary.pulled
            assert "doc_local.txt" in summary.pushed
            assert (local_pocket / "doc_remote.txt").exists()
            assert (server_pocket / "doc_local.txt").exists()

    @pytest.mark.asyncio
    async def test_notes_flow(self, test_service, tmp_path: Path):
        _, port, _ = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            # Отправка записки
            deliv = await client.note_send("https://example.com/spec")
            assert deliv.note_id is not None

            # Просмотр истории
            hist = await client.note_history(limit=10)
            assert hist.total_count >= 1
            sent_note = next(n for n in hist.notes if n.note_id == deliv.note_id)
            assert sent_note.text == "https://example.com/spec"

            # Отметка прочтения
            mark_res = await client.note_mark_read([deliv.note_id])
            assert mark_res.marked_count == 1

    @pytest.mark.asyncio
    async def test_system_status_summary(self, test_service, tmp_path: Path):
        _, port, _ = test_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        async with BridgeClient(config=cfg, host="127.0.0.1", port=port) as client:
            status = await client.get_system_status()
            assert status["connection"]["status"] == "online"
            assert "latency_ms" in status["connection"]
            assert "remote" in status
            assert "pocket" in status
            assert "notes" in status

    @pytest.mark.asyncio
    async def test_psk_authentication_success_and_failure(self, auth_service, tmp_path: Path):
        _, port, _ = auth_service
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg_correct = BridgeConfig(
            connection=ConnectionConfig(psk_token="secret-key-1234"),
            pocket=PocketConfig(path=str(local_pocket)),
        )
        async with BridgeClient(config=cfg_correct, host="127.0.0.1", port=port) as client:
            res = await client.exec("echo authenticated")
            assert res.exit_code == 0

        # Неверный токен -> BridgeAuthError
        cfg_wrong = BridgeConfig(
            connection=ConnectionConfig(psk_token="WRONG-TOKEN"),
            pocket=PocketConfig(path=str(local_pocket)),
        )
        async with BridgeClient(config=cfg_wrong, host="127.0.0.1", port=port) as client:
            with pytest.raises(BridgeAuthError):
                await client.exec("echo should-fail")

    @pytest.mark.asyncio
    async def test_network_error_on_invalid_port(self, tmp_path: Path):
        local_pocket = tmp_path / "pocket_client"
        local_pocket.mkdir()

        cfg = BridgeConfig(pocket=PocketConfig(path=str(local_pocket)))
        client = BridgeClient(config=cfg, host="127.0.0.1", port=59999, timeout_sec=0.5)
        with pytest.raises(BridgeNetworkError):
            await client.ping()
