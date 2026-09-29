"""
Тесты для bridge_agent_win.service — серверный демон WindowsBridgeService
и обязательный аудит в кармане.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bridge_agent_win.service import WindowsBridgeService
from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    PocketConfig,
)
from bridge_core.models import (
    AuditStatus,
    ExecRequestParams,
    JsonRpcRequest,
    NodeOS,
    NodeStatus,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.security import PSKAuthenticator
from bridge_core.transport import AsyncTransportClient, RpcCallError


@pytest.fixture
async def running_service(tmp_path: Path) -> Any:
    """Фикстура: запускает WindowsBridgeService на случайном порту с временным карманом."""
    pocket_dir = tmp_path / "pocket"
    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )
    service = WindowsBridgeService(cfg)
    await service.start()

    assert service.server._server is not None
    port = service.server._server.sockets[0].getsockname()[1]

    yield service, port, pocket_dir

    await service.stop()


class TestWindowsBridgeService:
    """Тесты работы демона службы и аудита в кармане."""

    @pytest.mark.asyncio
    async def test_service_ping_returns_metrics(self, running_service: Any) -> None:
        _service, port, _ = running_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        req = JsonRpcRequest(method=RpcMethod.HEARTBEAT_PING)
        resp = await client.call_rpc(req)

        pong = PongResult.model_validate(resp.result)
        assert pong.agent_os == NodeOS.WINDOWS
        assert pong.status == NodeStatus.READY
        assert pong.uptime_seconds >= 0

        await client.close()

    @pytest.mark.asyncio
    async def test_service_exec_writes_atomic_jsonl_log(self, running_service: Any) -> None:
        """Проверяем, что выполнение команды обязательно фиксируется в .jsonl лог кармана."""
        service, port, pocket_dir = running_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        exec_params = ExecRequestParams(command='echo "Audit Entry Test 123"')
        req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=exec_params.model_dump(),
        )

        resp = await client.call_rpc(req)
        assert resp.result["exit_code"] == 0
        assert "Audit Entry Test 123" in resp.result["stdout"]

        # Проверяем, что лог создался в кармане
        logs_dir = pocket_dir / "logs"
        assert logs_dir.exists()
        log_files = list(logs_dir.glob("*.jsonl"))
        assert len(log_files) >= 1

        # Читаем записи через AuditLogger
        entries = service.audit_logger.read_entries()
        assert len(entries) >= 1
        latest = entries[0]

        assert latest.method == RpcMethod.EXEC_RUN
        assert latest.status == AuditStatus.SUCCESS
        assert latest.command == 'echo "Audit Entry Test 123"'
        assert latest.exit_code == 0
        assert latest.duration_ms is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_service_timeout_logged_in_audit(self, running_service: Any) -> None:
        """Проверяем, что таймаут также гарантированно пишется в .jsonl аудит-лог кармана."""
        service, port, _ = running_service
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        exec_params = ExecRequestParams(command="sleep 10", timeout_sec=1)
        req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=exec_params.model_dump(),
        )

        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(req)

        assert exc_info.value.code == RpcErrorCode.COMMAND_TIMEOUT

        # Проверяем запись в логе кармана
        entries = service.audit_logger.read_entries()
        assert len(entries) >= 1
        latest = entries[0]
        assert latest.status == AuditStatus.TIMEOUT
        assert latest.timed_out is True
        assert latest.command == "sleep 10"

        await client.close()

    @pytest.mark.asyncio
    async def test_service_psk_authentication(self, tmp_path: Path) -> None:
        """Проверяем защиту сервиса PSK-токеном."""
        pocket_dir = tmp_path / "pocket_auth"
        cfg = BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=0, psk_token="correct-secret-123"),
            pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
        )
        service = WindowsBridgeService(cfg)
        await service.start()

        assert service.server._server is not None
        port = service.server._server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=port)

        # 1. Запрос БЕЗ токена -> должен отклониться с AUTH_FAILED
        req_no_auth = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params={"command": "echo no auth"},
        )
        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(req_no_auth)
        assert exc_info.value.code == RpcErrorCode.AUTH_FAILED

        # 2. Запрос С валидным токеном -> должен успешно выполниться
        auth = PSKAuthenticator(psk_token="correct-secret-123")
        auth_headers = auth.generate_auth_header()

        valid_params = {"command": "echo auth ok", **auth_headers}
        req_auth = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=valid_params,
        )
        resp = await client.call_rpc(req_auth)
        assert resp.result["exit_code"] == 0

        await client.close()
        await service.stop()
