"""
Тесты для bridge_core.service.BridgeService — универсальный узел на Linux (с BashExecutor).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    PocketConfig,
)
from bridge_core.executor import BashExecutor
from bridge_core.models import (
    AuditStatus,
    ExecRequestParams,
    FsFindParams,
    FsFindResult,
    FsListParams,
    FsListResult,
    JsonRpcRequest,
    NodeOS,
    NodeStatus,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteSendParams,
    PingParams,
    PocketPushParams,
    PongResult,
    RpcMethod,
)
from bridge_core.service import BridgeService
from bridge_core.transport import AsyncTransportClient


@pytest.fixture
async def running_linux_service(tmp_path: Path) -> Any:
    """Фикстура: запускает BridgeService (Linux) на случайном порту с BashExecutor."""
    pocket_dir = tmp_path / "pocket"
    pocket_dir.mkdir(parents=True, exist_ok=True)
    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    executor = BashExecutor()
    service = BridgeService(config=cfg, executor=executor, agent_os=NodeOS.LINUX)
    await service.start()

    assert service.server._server is not None
    port = service.server._server.sockets[0].getsockname()[1]

    yield service, port, pocket_dir

    await service.stop()


class TestUniversalLinuxService:
    """Тесты работы универсального сервиса на узле Linux."""

    @pytest.mark.asyncio
    async def test_linux_service_ping(self, running_linux_service: Any) -> None:
        _service, port, _ = running_linux_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        req = JsonRpcRequest(
            method=RpcMethod.HEARTBEAT_PING,
            params=PingParams(client_os=NodeOS.WINDOWS).model_dump(),
        )
        resp = await client.call_rpc(req)

        pong = PongResult.model_validate(resp.result)
        assert pong.agent_os == NodeOS.LINUX
        assert pong.status == NodeStatus.READY
        assert pong.uptime_seconds >= 0

        await client.close()

    @pytest.mark.asyncio
    async def test_linux_service_exec_bash(self, running_linux_service: Any) -> None:
        service, port, pocket_dir = running_linux_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        exec_params = ExecRequestParams(command='echo "Linux Service Exec 999"')
        req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=exec_params.model_dump(),
        )

        resp = await client.call_rpc(req)
        assert resp.result["exit_code"] == 0
        assert "Linux Service Exec 999" in resp.result["stdout"]

        # Проверяем, что запись аудита зафиксирована
        logs_dir = pocket_dir / "logs"
        assert logs_dir.exists()
        entries = service.audit_logger.read_entries()
        assert len(entries) >= 1
        latest = entries[0]
        assert latest.method == RpcMethod.EXEC_RUN
        assert latest.status == AuditStatus.SUCCESS
        assert latest.command == 'echo "Linux Service Exec 999"'
        assert latest.exit_code == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_linux_service_fs_list(self, running_linux_service: Any, tmp_path: Path) -> None:
        _service, port, _ = running_linux_service
        test_dir = tmp_path / "fs_test"
        test_dir.mkdir()
        (test_dir / "alpha.txt").write_text("aaa")
        (test_dir / "beta.log").write_text("bbb")
        (test_dir / "subdir").mkdir()

        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)
        req = JsonRpcRequest(
            method=RpcMethod.FS_LIST,
            params=FsListParams(path=str(test_dir)).model_dump(),
        )
        resp = await client.call_rpc(req)

        res = FsListResult.model_validate(resp.result)
        assert res.total_entries == 3
        names = {e.name for e in res.entries}
        assert names == {"alpha.txt", "beta.log", "subdir"}

        await client.close()

    @pytest.mark.asyncio
    async def test_linux_service_fs_find(self, running_linux_service: Any, tmp_path: Path) -> None:
        _service, port, _ = running_linux_service
        search_dir = tmp_path / "search_root"
        search_dir.mkdir()
        sub = search_dir / "nested"
        sub.mkdir()
        (search_dir / "match_one.py").write_text("print(1)")
        (sub / "match_two.py").write_text("print(2)")
        (search_dir / "ignore.txt").write_text("text")

        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)
        req = JsonRpcRequest(
            method=RpcMethod.FS_FIND,
            params=FsFindParams(pattern="*.py", directory=str(search_dir)).model_dump(),
        )
        resp = await client.call_rpc(req)

        res = FsFindResult.model_validate(resp.result)
        assert res.total_found == 2
        paths = [e.path for e in res.entries]
        assert any("match_one.py" in p for p in paths)
        assert any("match_two.py" in p for p in paths)

        await client.close()

    @pytest.mark.asyncio
    async def test_linux_service_notes_and_pocket(self, running_linux_service: Any) -> None:
        _service, port, pocket_dir = running_linux_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        # 1. Отправка заметки
        note_req = JsonRpcRequest(
            method=RpcMethod.NOTES_SEND,
            params=NoteSendParams(
                text="Симметричная заметка для Linux",
                author_os=NodeOS.LINUX,
            ).model_dump(),
        )
        note_resp = await client.call_rpc(note_req)
        assert "note_id" in note_resp.result

        # 2. Получение истории заметок
        hist_req = JsonRpcRequest(
            method=RpcMethod.NOTES_HISTORY,
            params=NoteHistoryParams(limit=10).model_dump(),
        )
        hist_resp = await client.call_rpc(hist_req)
        hist = NoteHistoryResult.model_validate(hist_resp.result)
        assert hist.total_count >= 1
        assert hist.notes[0].text == "Симметричная заметка для Linux"

        # 3. Отправка файла в карман
        push_req = JsonRpcRequest(
            method=RpcMethod.POCKET_PUSH,
            params=PocketPushParams(
                path="linux_drop.txt",
                offset=0,
                data_b64="SGVsbG8gTGludXg=",  # "Hello Linux"
                is_last=True,
            ).model_dump(),
        )
        push_resp = await client.call_rpc(push_req)
        assert push_resp.result["completed"] is True

        # Проверяем, что файл действительно в кармане
        target_file = pocket_dir / "linux_drop.txt"
        assert target_file.exists()
        assert target_file.read_text() == "Hello Linux"

        await client.close()
