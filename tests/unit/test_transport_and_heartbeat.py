"""
Интеграционные юнит-тесты для transport.py и heartbeat.py.

Проверяет:
  - Полный сетевой цикл AsyncTransportServer <-> AsyncTransportClient через loopback TCP.
  - Диспетчеризацию JSON-RPC методов и возвращение результатов.
  - Обработку серверных ошибок RpcCallError и неизвестных методов.
  - Работу HeartbeatManager: успешный probe, вычисление RTT, сохранение pong.
  - Fail-Fast сценарий: мгновенное обнаружение остановки сервера и смена состояния на UNREACHABLE.
"""

from __future__ import annotations

from typing import Any

import pytest

from bridge_core.config import HeartbeatConfig
from bridge_core.heartbeat import HeartbeatManager, HeartbeatTimeoutError
from bridge_core.models import (
    ConnectionState,
    JsonRpcRequest,
    NodeOS,
    NodeStatus,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.transport import (
    AsyncTransportClient,
    AsyncTransportServer,
    RpcCallError,
)


@pytest.fixture
async def tcp_server() -> Any:
    """Фикстура: запускает AsyncTransportServer на случайном свободном порту loopback."""
    server = AsyncTransportServer(host="127.0.0.1", port=0, dev_logging=True)

    # Регистрируем обработчик ping
    async def handle_ping(params: dict[str, Any], session_info: dict[str, Any]) -> dict[str, Any]:
        pong = PongResult(
            agent_os=NodeOS.WINDOWS,
            cpu_percent=15.0,
            memory_used_mb=2048,
            uptime_seconds=5000,
            status=NodeStatus.READY,
        )
        return pong.model_dump()

    # Регистрируем обработчик эхо
    async def handle_echo(params: dict[str, Any], session_info: dict[str, Any]) -> dict[str, Any]:
        return {"echo": params.get("msg", "")}

    # Регистрируем обработчик ошибки
    async def handle_fail(params: dict[str, Any], session_info: dict[str, Any]) -> dict[str, Any]:
        raise RpcCallError(code=-32002, message="Искусственная ошибка для теста")

    server.register_handler(RpcMethod.HEARTBEAT_PING, handle_ping)
    server.register_handler("test.echo", handle_echo)
    server.register_handler("test.fail", handle_fail)

    await server.start()
    assert server._server is not None
    port = server._server.sockets[0].getsockname()[1]

    yield server, port

    await server.stop()


class TestTransportAndHeartbeat:
    """Тесты сетевого транспорта и Heartbeat механизма."""

    @pytest.mark.asyncio
    async def test_rpc_echo_call(self, tcp_server: Any) -> None:
        _server, port = tcp_server
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=2.0)

        req = JsonRpcRequest(method="test.echo", params={"msg": "Привет сокет!"})
        resp = await client.call_rpc(req)

        assert resp.id == req.id
        assert resp.result == {"echo": "Привет сокет!"}

        await client.close()

    @pytest.mark.asyncio
    async def test_rpc_custom_error_handling(self, tcp_server: Any) -> None:
        _server, port = tcp_server
        client = AsyncTransportClient(host="127.0.0.1", port=port)

        req = JsonRpcRequest(method="test.fail")
        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(req)

        assert exc_info.value.code == -32002
        assert "Искусственная ошибка" in exc_info.value.message

        await client.close()

    @pytest.mark.asyncio
    async def test_rpc_method_not_found(self, tcp_server: Any) -> None:
        _server, port = tcp_server
        client = AsyncTransportClient(host="127.0.0.1", port=port)

        req = JsonRpcRequest(method="non_existent_method")
        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(req)

        assert exc_info.value.code == RpcErrorCode.METHOD_NOT_FOUND

        await client.close()

    @pytest.mark.asyncio
    async def test_heartbeat_manager_probe_success(self, tcp_server: Any) -> None:
        _server, port = tcp_server
        client = AsyncTransportClient(host="127.0.0.1", port=port)

        state_changes: list[tuple[ConnectionState, ConnectionState]] = []

        def on_change(old_s: ConnectionState, new_s: ConnectionState) -> None:
            state_changes.append((old_s, new_s))

        hb_cfg = HeartbeatConfig(timeout_sec=1.5, interval_sec=1.0)
        hb = HeartbeatManager(client=client, config=hb_cfg, on_state_change=on_change)

        assert hb.state == ConnectionState.DISCONNECTED

        # Проводим быстрый probe
        rtt_ms = await hb.probe()
        assert rtt_ms >= 0.0
        assert hb.state == ConnectionState.CONNECTED
        assert hb.last_pong is not None
        assert hb.last_pong.agent_os == NodeOS.WINDOWS
        assert hb.last_pong.cpu_percent == 15.0

        await hb.stop()
        await client.close()

    @pytest.mark.asyncio
    async def test_heartbeat_fail_fast_on_server_stop(self, tcp_server: Any) -> None:
        """Проверяем, что при остановке сервера probe завершается с ошибкой <= 1.5 с."""
        server, port = tcp_server
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=1.0)

        hb_cfg = HeartbeatConfig(timeout_sec=1.0, max_missed=1)
        hb = HeartbeatManager(client=client, config=hb_cfg)

        # Сначала успешный probe
        await hb.probe()
        assert hb.state == ConnectionState.CONNECTED

        # Останавливаем сервер (эмуляция падения Windows или разрыва сети)
        await server.stop()
        await client.close()

        # Повторный probe должен немедленно упасть и перевести в UNREACHABLE
        with pytest.raises(HeartbeatTimeoutError):
            await hb.probe(timeout_sec=1.0)

        assert hb.state == ConnectionState.UNREACHABLE
        await hb.stop()
