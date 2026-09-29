"""
Интеграционные тесты сквозного взаимодействия всех слоёв Bridge Local.

Тестирует совместную работу:
  - Слой 1: Сетевой транспорт (AsyncTransportClient, Length-Prefix Framing, JSON-RPC).
  - Слой 2: Служба-демон агента (WindowsBridgeService, диспетчеризация методов).
  - Слой 3: Выполнение процессов (PowerShellExecutor, ProcessTreeKiller, WindowsOutputDecoder).
  - Слой 4: Безопасность (PSKAuthenticator, HMAC-SHA256, Nonce, защита от Replay-атак).
  - Слой 5: Хранилище аудита (AtomicJsonlLogger, карман pocket/logs/YYYY-MM-DD.jsonl).
  - Слой 6: Мониторинг доступности (HeartbeatManager, Fail-Fast probe <= 1.5s).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from bridge_agent_win.service import WindowsBridgeService
from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    HeartbeatConfig,
    PocketConfig,
)
from bridge_core.heartbeat import HeartbeatManager, HeartbeatTimeoutError
from bridge_core.models import (
    AuditStatus,
    ConnectionState,
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
async def full_stack_environment(tmp_path: Path) -> Any:
    """
    Разворачивает полноценный стек:
      - WindowsBridgeService с временным карманом и динамическим портом.
      - Каталог pocket/logs/.
    """
    pocket_dir = tmp_path / "shared_pocket"
    config = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
    )

    service = WindowsBridgeService(config)
    await service.start()

    assert service.server._server is not None
    port = service.server._server.sockets[0].getsockname()[1]

    yield service, port, pocket_dir

    await service.stop()


class TestLayerInteractions:
    """Сквозные тесты взаимодействия слоёв."""

    @pytest.mark.asyncio
    async def test_full_roundtrip_exec_and_audit(self, full_stack_environment: Any) -> None:
        """
        Сценарий 1: Полный цикл клиент -> сеть -> служба -> процесс -> декодер -> логгер -> карман.
        """
        service, port, pocket_dir = full_stack_environment

        # Клиент подключается к службе
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=3.0)
        await client.connect()
        assert client.is_connected

        # 1. Отправляем команду с кириллицей
        exec_params = ExecRequestParams(
            command='echo "Сквозной тест слоев: УСПЕХ"',
            timeout_sec=5,
        )
        req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=exec_params.model_dump(),
        )

        resp = await client.call_rpc(req)

        # 2. Проверяем ответ клиенту
        assert resp.id == req.id
        assert resp.result["exit_code"] == 0
        assert "Сквозной тест слоев: УСПЕХ" in resp.result["stdout"]
        assert resp.result["duration_ms"] >= 0

        # 3. Проверяем физический файл лога на диске в кармане
        logs_dir = pocket_dir / "logs"
        log_files = list(logs_dir.glob("*.jsonl"))
        assert len(log_files) == 1

        entries = service.audit_logger.read_entries()
        assert len(entries) >= 1
        entry = entries[0]

        assert entry.method == RpcMethod.EXEC_RUN
        assert entry.status == AuditStatus.SUCCESS
        assert "Сквозной тест слоев: УСПЕХ" in (entry.command or "")
        assert entry.exit_code == 0
        assert entry.duration_ms is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_authenticated_session_and_replay_rejection(self, tmp_path: Path) -> None:
        """
        Сценарий 2: PSK-аутентификация с HMAC и пресечение Replay-атаки с фиксацией в аудит.
        """
        pocket_dir = tmp_path / "auth_pocket"
        secret_token = "vault-super-secret-key-42"

        config = BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=0, psk_token=secret_token),
            pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
        )
        service = WindowsBridgeService(config)
        await service.start()

        assert service.server._server is not None
        port = service.server._server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=port)
        auth = PSKAuthenticator(psk_token=secret_token)

        # 1. Запрос с корректной HMAC-подписью
        headers_1 = auth.generate_auth_header()
        req_1 = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params={"command": 'echo "auth 1 ok"', **headers_1},
        )
        resp_1 = await client.call_rpc(req_1)
        assert resp_1.result["exit_code"] == 0

        # 2. Попытка повторить тот же пакет с тем же nonce (Replay Attack)
        req_replay = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params={"command": 'echo "replay attack"', **headers_1},
        )
        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(req_replay)

        assert exc_info.value.code == RpcErrorCode.AUTH_FAILED
        assert "Replay" in exc_info.value.message or "аутентификации" in exc_info.value.message

        # 3. Проверяем, что попытка атаки зафиксирована в логе аудита кармана со статусом ERROR
        entries = service.audit_logger.read_entries()
        assert any(e.status == AuditStatus.ERROR for e in entries)

        await client.close()
        await service.stop()

    @pytest.mark.asyncio
    async def test_timeout_process_kill_and_connection_reuse(
        self, full_stack_environment: Any
    ) -> None:
        """
        Сценарий 3: Зависание процесса -> срабатывание Process Tree Killer
        -> запись таймаута в аудит -> канал остаётся работоспособным.
        """
        service, port, _ = full_stack_environment
        client = AsyncTransportClient(host="127.0.0.1", port=port)

        # 1. Запускаем команду сна на 10 сек с лимитом 1 сек
        timeout_req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=ExecRequestParams(command="sleep 10", timeout_sec=1).model_dump(),
        )

        with pytest.raises(RpcCallError) as exc_info:
            await client.call_rpc(timeout_req)

        assert exc_info.value.code == RpcErrorCode.COMMAND_TIMEOUT
        assert exc_info.value.data["timeout_sec"] == 1

        # 2. Проверяем запись таймаута в аудит-логе
        entries = service.audit_logger.read_entries()
        latest = entries[0]
        assert latest.status == AuditStatus.TIMEOUT
        assert latest.timed_out is True

        # 3. КРИТИЧЕСКИ ВАЖНО: Канал связи НЕ должен умереть! Проверяем переиспользование сокета
        alive_req = JsonRpcRequest(
            method=RpcMethod.EXEC_RUN,
            params=ExecRequestParams(command='echo "канал все еще жив"').model_dump(),
        )
        resp_alive = await client.call_rpc(alive_req)
        assert resp_alive.result["exit_code"] == 0
        assert "канал все еще жив" in resp_alive.result["stdout"]

        await client.close()

    @pytest.mark.asyncio
    async def test_concurrent_clients_interaction(self, full_stack_environment: Any) -> None:
        """
        Сценарий 4: Несколько клиентов одновременно шлют команды и пинги.
        Проверяет устойчивость AsyncTransportServer и отсутствие коллизий в AtomicJsonlLogger.
        """
        service, port, _ = full_stack_environment

        async def client_worker(idx: int) -> None:
            c = AsyncTransportClient(host="127.0.0.1", port=port)
            # Пинг
            pong_resp = await c.call_rpc(JsonRpcRequest(method=RpcMethod.HEARTBEAT_PING))
            pong = PongResult.model_validate(pong_resp.result)
            assert pong.status == NodeStatus.READY

            # Команда
            cmd_resp = await c.call_rpc(
                JsonRpcRequest(
                    method=RpcMethod.EXEC_RUN,
                    params=ExecRequestParams(command=f'echo "worker {idx}"').model_dump(),
                )
            )
            assert cmd_resp.result["exit_code"] == 0
            assert f"worker {idx}" in cmd_resp.result["stdout"]
            await c.close()

        # Запускаем 5 одновременных клиентов
        tasks = [client_worker(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # Все 5 команд должны быть атомарно записаны в карман
        entries = service.audit_logger.read_entries(limit=50)
        worker_entries = [e for e in entries if "worker" in (e.command or "")]
        assert len(worker_entries) == 5

    @pytest.mark.asyncio
    async def test_heartbeat_liveness_and_failfast_detection(
        self, full_stack_environment: Any
    ) -> None:
        """
        Сценарий 5: Фоновый HeartbeatManager отслеживает пульс службы
        и fail-fast реагирует на падение.
        """
        service, port, _ = full_stack_environment
        client = AsyncTransportClient(host="127.0.0.1", port=port, connect_timeout=1.0)

        hb_config = HeartbeatConfig(interval_sec=0.5, timeout_sec=1.0, max_missed=1)
        hb = HeartbeatManager(client=client, config=hb_config)

        # 1. Проверяем успешный probe
        rtt = await hb.probe()
        assert rtt >= 0
        assert hb.state == ConnectionState.CONNECTED
        assert hb.last_pong is not None
        assert hb.last_pong.agent_os == NodeOS.WINDOWS

        # 2. Имитируем падение службы (остановка сервера)
        await service.stop()
        await client.close()

        # 3. Следующий probe мгновенно переводит узел в UNREACHABLE без зависания
        with pytest.raises(HeartbeatTimeoutError):
            await hb.probe(timeout_sec=1.0)

        assert hb.state == ConnectionState.UNREACHABLE
        await hb.stop()
