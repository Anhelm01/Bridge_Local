"""
tests/integration/test_resilience_simulation.py — Chaos and Resilience Integration Tests.

Phase 6 Test Suite:
1. Simulated socket drop during multi-chunk pocket file transfer (resuming from byte offset).
2. Resumable transfer contract verification: partial .part file detection, offset query,
   resuming and final SHA-256 validation.
3. Windows Sharing Violation (WinError 32 / EBUSY / PermissionError) simulation:
   concurrent file locking and verifying retry loop with exponential backoff.
4. Heartbeat fail-fast detection: when remote node stops responding, client raises
   ConnectionError/Timeout within 1.5s instead of hanging.

Rules:
- Strictly NO emojis in any files or logs. Use clean technical tags [OK], [FAIL], [WARN], [RESUME].
"""

from __future__ import annotations

import asyncio
import base64
import errno
import hashlib
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from bridge_agent_win.service import WindowsBridgeService
from bridge_client_linux.client import BridgeClient
from bridge_client_linux.exceptions import BridgeTimeoutError
from bridge_core.config import (
    BridgeConfig,
    ConnectionConfig,
    HeartbeatConfig,
    LoggingConfig,
    PocketConfig,
)
from bridge_core.heartbeat import HeartbeatManager, HeartbeatTimeoutError
from bridge_core.logger import AtomicJsonlLogger
from bridge_core.models import (
    AuditLogEntry,
    AuditStatus,
    ConnectionState,
    PocketOffsetParams,
    PocketOffsetResult,
    PocketPushParams,
    PocketPushResult,
    RpcMethod,
)
from bridge_core.pocket import PocketManager, compute_file_sha256
from bridge_core.retry import is_sharing_violation, retry_with_backoff
from bridge_core.transport import AsyncTransportClient, RpcCallError

# ---------------------------------------------------------------------------
# Async Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def running_service(
    tmp_path: Path,
) -> AsyncGenerator[tuple[WindowsBridgeService, int, Path]]:
    """Запускает WindowsBridgeService на случайном свободном порту с изолированным карманом."""
    pocket_dir = tmp_path / "server_pocket"
    pocket_dir.mkdir(parents=True, exist_ok=True)

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir), logs_subdir="logs"),
        heartbeat=HeartbeatConfig(interval_sec=2.0, timeout_sec=1.5, max_missed=2),
        logging=LoggingConfig(dev_mode=True, level="TRACE"),
    )
    svc = WindowsBridgeService(config=cfg)
    await svc.start()

    assert svc.server._server is not None
    sockets = svc.server._server.sockets
    assert sockets
    real_port = sockets[0].getsockname()[1]

    yield svc, real_port, pocket_dir

    await svc.stop()


# ---------------------------------------------------------------------------
# Сценарий 1: Имитация обрыва сокета при передаче файла по частям
# ---------------------------------------------------------------------------


class TestSocketDropResilience:
    """Сценарий 1: Обрыв сетевого соединения посреди многочанковой передачи и успешная докачка."""

    @pytest.mark.asyncio
    async def test_simulated_socket_drop_and_resume_push(
        self, running_service: tuple[WindowsBridgeService, int, Path]
    ) -> None:
        """
        Передача файла из 5 чанков.
        После отправки чанка 2 соединение аварийно разрывается.
        Клиент восстанавливает связь, опрашивает сервер об offset и завершает передачу
        начиная с чанка 3. Проверяется целостность SHA-256.
        """
        _svc, port, pocket_dir = running_service

        # Генерируем 5 чанков по 16 КБ (80 КБ)
        chunk_size = 16384
        total_chunks = 5
        full_payload = os.urandom(chunk_size * total_chunks)
        full_sha = hashlib.sha256(full_payload).hexdigest()
        file_name = "drop_simulation.bin"

        # 1. Подключаемся первым клиентом и отправляем первые 2 чанка (0 и 1)
        client1 = AsyncTransportClient(host="127.0.0.1", port=port)
        await client1.connect()

        try:
            for idx in range(2):
                offset = idx * chunk_size
                chunk_data = full_payload[offset : offset + chunk_size]
                push_params = PocketPushParams(
                    path=file_name,
                    offset=offset,
                    data_b64=base64.b64encode(chunk_data).decode("ascii"),
                    is_last=False,
                )
                raw = await client1.call(RpcMethod.POCKET_PUSH, push_params.model_dump())
                res = PocketPushResult.model_validate(raw)
                assert not res.completed
                assert res.bytes_written == chunk_size

            # Проверяем состояние сервера ДО обрыва:
            # .part файл должен существовать и иметь размер ровно 2 чанка (32 КБ)
            part_file = pocket_dir / f".{file_name}.part"
            assert part_file.exists()
            assert part_file.stat().st_size == 2 * chunk_size

            # Целевой файл еще не должен быть опубликован
            dest_file = pocket_dir / file_name
            assert not dest_file.exists()

        finally:
            # 2. Имитируем жесткий обрыв сокета (аварийный disconnect)
            await client1.close()

        # 3. Подключаемся новым клиентом (reconnect после сбоя)
        client2 = AsyncTransportClient(host="127.0.0.1", port=port)
        await client2.connect()

        try:
            # Опрашиваем сервер: какое смещение уже сохранено?
            raw_offset = await client2.call(
                RpcMethod.POCKET_OFFSET,
                PocketOffsetParams(path=file_name).model_dump(),
            )
            offset_res = PocketOffsetResult.model_validate(raw_offset)

            # Проверяем обнаружение частичного файла через контракт RPC
            assert offset_res.part_exists
            assert not offset_res.completed
            assert offset_res.offset == 2 * chunk_size

            # 4. Возобновляем отправку с чанка 2 (смещение 32 КБ) до конца
            current_offset = offset_res.offset
            while current_offset < len(full_payload):
                chunk_data = full_payload[current_offset : current_offset + chunk_size]
                is_last = (current_offset + len(chunk_data)) >= len(full_payload)

                push_params = PocketPushParams(
                    path=file_name,
                    offset=current_offset,
                    data_b64=base64.b64encode(chunk_data).decode("ascii"),
                    is_last=is_last,
                    sha256_full=full_sha if is_last else None,
                )
                raw = await client2.call(RpcMethod.POCKET_PUSH, push_params.model_dump())
                res = PocketPushResult.model_validate(raw)

                if is_last:
                    assert res.completed
                    assert res.sha256 == full_sha
                else:
                    assert not res.completed

                current_offset += len(chunk_data)

            # 5. Проверяем результат на диске сервера:
            # .part файл должен быть атомарно замещен на dest_file
            assert dest_file.exists()
            assert not part_file.exists()
            assert dest_file.stat().st_size == len(full_payload)
            assert hashlib.sha256(dest_file.read_bytes()).hexdigest() == full_sha

        finally:
            await client2.close()


# ---------------------------------------------------------------------------
# Сценарий 2: Верификация контракта возобновляемой передачи (Resumable Contract)
# ---------------------------------------------------------------------------


class TestResumableTransferContract:
    """Сценарий 2: Проверка контракта pocket.offset, детекции .part и верификации SHA-256."""

    def test_pocket_offset_params_and_result_validation(self) -> None:
        """Проверка строгой валидации Pydantic DTO моделей PocketOffset."""
        # 1. PocketOffsetParams
        params = PocketOffsetParams(path="sub/doc.txt")
        assert params.path == "sub/doc.txt"
        with pytest.raises(ValidationError):
            PocketOffsetParams(path="")

        # 2. PocketOffsetResult
        res = PocketOffsetResult(
            path="sub/doc.txt",
            offset=4096,
            part_exists=True,
            completed=False,
        )
        assert res.offset == 4096
        assert res.part_exists
        assert not res.completed

        # Roundtrip JSON
        dumped = res.model_dump()
        restored = PocketOffsetResult.model_validate(dumped)
        assert restored == res

    def test_pocket_manager_partial_file_detection(self, tmp_path: Path) -> None:
        """Проверка локальных методов детекции .part файлов и смещений в PocketManager."""
        manager = PocketManager(pocket_dir=tmp_path)
        rel_path = "data/sample.dat"

        # 1. До создания файла
        assert manager.get_partial_offset(rel_path) == 0
        offset, part_exists, completed = manager.query_file_offset(rel_path)
        assert offset == 0
        assert not part_exists
        assert not completed

        # 2. Создаем частичный .part файл
        part_path = manager.get_part_file(rel_path)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_bytes(b"A" * 1024)

        assert manager.get_partial_offset(rel_path) == 1024
        offset, part_exists, completed = manager.query_file_offset(rel_path)
        assert offset == 1024
        assert part_exists
        assert not completed

        # 3. Завершаем файл (promotion .part -> dest)
        dest_path = tmp_path / rel_path
        part_path.replace(dest_path)

        offset, part_exists, completed = manager.query_file_offset(rel_path)
        assert offset == 1024
        assert not part_exists
        assert completed

    @pytest.mark.asyncio
    async def test_high_level_client_resumable_push(
        self, running_service: tuple[WindowsBridgeService, int, Path], tmp_path: Path
    ) -> None:
        """
        Проверка высокоуровневого метода BridgeClient.pocket_push_file.
        Если на сервере уже лежит частичный .part файл, push начинает передачу со смещения.
        """
        _svc, port, server_pocket = running_service

        # Локальный файл клиента (64 КБ = 4 чанка по 16 КБ)
        chunk_size = 16384
        full_payload = os.urandom(chunk_size * 4)
        full_sha = hashlib.sha256(full_payload).hexdigest()

        client_pocket = tmp_path / "client_pocket"
        client_pocket.mkdir()
        src_file = client_pocket / "resumable_push.bin"
        src_file.write_bytes(full_payload)

        # Предустанавливаем на сервере частичный .part файл размером 32 КБ (первые 2 чанка)
        server_part = server_pocket / ".resumable_push.bin.part"
        server_part.write_bytes(full_payload[: chunk_size * 2])

        client = BridgeClient(host="127.0.0.1", port=port)
        await client.connect()

        try:
            # Запускаем push с флагом resume=True
            result = await client.pocket_push_file(
                local_file_path=src_file,
                target_rel_path="resumable_push.bin",
                chunk_size=chunk_size,
                resume=True,
            )

            assert result.completed
            assert result.sha256 == full_sha

            # Проверяем файл на сервере
            server_dest = server_pocket / "resumable_push.bin"
            assert server_dest.exists()
            assert not server_part.exists()
            assert server_dest.stat().st_size == len(full_payload)
            assert hashlib.sha256(server_dest.read_bytes()).hexdigest() == full_sha

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_high_level_client_resumable_pull(
        self, running_service: tuple[WindowsBridgeService, int, Path], tmp_path: Path
    ) -> None:
        """
        Проверка высокоуровневого метода BridgeClient.pocket_pull_file.
        Если на клиенте уже лежит частичный .part файл, pull скачивает только остаток.
        """
        _svc, port, server_pocket = running_service

        # Файл на сервере (64 КБ)
        chunk_size = 16384
        payload = os.urandom(chunk_size * 4)
        server_file = server_pocket / "server_data.bin"
        server_file.write_bytes(payload)

        client_pocket = tmp_path / "client_pocket"
        client_pocket.mkdir()
        client_dest = client_pocket / "server_data.bin"
        client_part = client_pocket / ".server_data.bin.part"

        # Предустанавливаем локальный частичный .part файл (16 КБ)
        client_part.write_bytes(payload[:chunk_size])

        cfg = BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=port),
            pocket=PocketConfig(path=str(client_pocket)),
            logging=LoggingConfig(dev_mode=True),
        )
        client = BridgeClient(config=cfg)
        await client.connect()

        try:
            pulled_path = await client.pocket_pull_file(
                remote_rel_path="server_data.bin",
                dest_local_path=client_dest,
                chunk_size=chunk_size,
                resume=True,
            )

            assert pulled_path.exists()
            assert not client_part.exists()
            assert pulled_path.stat().st_size == len(payload)
            assert hashlib.sha256(pulled_path.read_bytes()).hexdigest() == compute_file_sha256(
                server_file
            )

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_corrupted_partial_file_fails_sha256_and_cleans_up(
        self, running_service: tuple[WindowsBridgeService, int, Path]
    ) -> None:
        """
        Если частичный .part файл был поврежден на диске (битые данные),
        при финализации вычисляется SHA-256, обнаруживается несоответствие,
        операция бракуется, а поврежденный .part удаляется с диска.
        """
        _svc, port, server_pocket = running_service
        client = AsyncTransportClient(host="127.0.0.1", port=port)
        await client.connect()

        file_name = "corrupted_resume.bin"
        server_part = server_pocket / f".{file_name}.part"

        # Записываем заведомо битый первый чанк
        server_part.write_bytes(b"CORRUPTED_INITIAL_DATA")

        # Отправляем завершающий чанк с правильным ожидаемым хешем
        correct_data = b"CORRECT_INITIAL_DATA_REPLACED"
        expected_sha = hashlib.sha256(correct_data).hexdigest()

        try:
            push_params = PocketPushParams(
                path=file_name,
                offset=len(b"CORRUPTED_INITIAL_DATA"),
                data_b64=base64.b64encode(b"TAIL").decode("ascii"),
                is_last=True,
                sha256_full=expected_sha,
            )

            with pytest.raises(RpcCallError) as exc_info:
                await client.call(RpcMethod.POCKET_PUSH, push_params.model_dump())

            assert "SHA-256" in exc_info.value.message
            # Поврежденный .part файл должен быть немедленно удален
            assert not server_part.exists()
            # Целевой файл не должен быть создан
            assert not (server_pocket / file_name).exists()

        finally:
            await client.close()


# ---------------------------------------------------------------------------
# Сценарий 3: Windows Sharing Violation (WinError 32 / EBUSY / PermissionError)
# ---------------------------------------------------------------------------


class TestWindowsSharingViolationSimulation:
    """
    Сценарий 3: Имитация файловых блокировок Windows (Sharing Violation / WinError 32)
    и проверка цикла повторных попыток с экспоненциальным бэкоффом.
    """

    def test_is_sharing_violation_detection(self) -> None:
        """Проверяет распознавание кодов и признаков Windows Sharing Violation."""
        # 1. Windows WinError 32
        win_err = PermissionError(13, "[WinError 32] The process cannot access the file")
        win_err.winerror = 32
        assert is_sharing_violation(win_err)

        # 2. Linux EBUSY
        ebusy_err = OSError(errno.EBUSY, "Device or resource busy")
        assert is_sharing_violation(ebusy_err)

        # 3. Linux EACCES
        eacces_err = OSError(errno.EACCES, "Permission denied")
        assert is_sharing_violation(eacces_err)

        # 4. Произвольная ошибка не блокировки
        val_err = ValueError("Invalid parameter")
        assert not is_sharing_violation(val_err)

    def test_retry_loop_recovers_after_temporary_sharing_violation(self) -> None:
        """
        Имитирует временный конфликт совместного доступа к файлу:
        первые 2 попытки возвращают WinError 32, на 3-й попытке ресурс освобождается.
        """
        attempts = 0

        def flaky_file_operation() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                err = PermissionError(
                    13,
                    "[WinError 32] The process cannot access the file because it is being used",
                )
                err.winerror = 32
                raise err
            return "SUCCESS_DATA"

        t0 = time.perf_counter()
        result = retry_with_backoff(
            flaky_file_operation,
            max_retries=5,
            initial_delay=0.02,
            backoff_factor=2.0,
        )
        elapsed = time.perf_counter() - t0

        assert result == "SUCCESS_DATA"
        assert attempts == 3
        # Проверяем, что применялась задержка (0.02 + 0.04 = ~0.06s)
        assert elapsed >= 0.05

    def test_retry_loop_exhausts_and_raises_on_permanent_lock(self) -> None:
        """
        Если файл заблокирован непрерывно, цикл повторяет попытки до max_retries
        и пробрасывает исключение.
        """
        attempts = 0

        def locked_file_operation() -> None:
            nonlocal attempts
            attempts += 1
            err = PermissionError(13, "[WinError 32] File in use by another process")
            err.winerror = 32
            raise err

        with pytest.raises(PermissionError) as exc_info:
            retry_with_backoff(
                locked_file_operation,
                max_retries=4,
                initial_delay=0.01,
                backoff_factor=2.0,
            )

        assert attempts == 4
        assert "WinError 32" in str(exc_info.value)

    def test_atomic_jsonl_logger_recovers_from_sharing_violation(self, tmp_path: Path) -> None:
        """
        Интеграция: AtomicJsonlLogger при конкурентной блокировке лог-файла
        повторяет попытки с бэкоффом и успешно производит запись.
        """
        logger_inst = AtomicJsonlLogger(logs_dir=tmp_path)
        entry = AuditLogEntry(
            session_id="chaos-sess",
            client_ip="127.0.0.1",
            method=RpcMethod.POCKET_PUSH,
            request_id="chaos-req-1",
            status=AuditStatus.SUCCESS,
        )

        real_open = open
        call_count = 0

        def simulated_locked_open(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            # Первые 2 вызова симулируют блокировку лог-файла антивирусом
            if call_count <= 2:
                err = PermissionError(
                    13, "[WinError 32] Sharing violation: file locked by AV scanner"
                )
                err.winerror = 32
                raise err
            return real_open(*args, **kwargs)

        with patch("bridge_core.logger.open", side_effect=simulated_locked_open):
            log_file = logger_inst.write_sync(entry)

        assert log_file.exists()
        assert call_count >= 3
        entries = logger_inst.read_entries(limit=10)
        assert len(entries) == 1
        assert entries[0].request_id == "chaos-req-1"

    def test_pocket_manager_write_chunk_recovers_from_sharing_violation(
        self, tmp_path: Path
    ) -> None:
        """
        Интеграция: PocketManager.write_chunk при конфликте доступа к .part файлу
        повторяет попытки и успешно записывает чанк.
        """
        manager = PocketManager(pocket_dir=tmp_path)
        push_params = PocketPushParams(
            path="locked_file.txt",
            offset=0,
            data_b64=base64.b64encode(b"Payload with retry").decode("ascii"),
            is_last=True,
            sha256_full=hashlib.sha256(b"Payload with retry").hexdigest(),
        )

        real_open = open
        attempts = 0

        def flaky_chunk_open(*args: Any, **kwargs: Any) -> Any:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                err = PermissionError(13, "[WinError 32] File lock collision")
                err.winerror = 32
                raise err
            return real_open(*args, **kwargs)

        with patch("bridge_core.pocket.open", side_effect=flaky_chunk_open):
            target = manager.write_chunk(push_params)

        assert target is not None
        assert target.exists()
        assert target.read_bytes() == b"Payload with retry"
        assert attempts >= 3


# ---------------------------------------------------------------------------
# Сценарий 4: Fail-Fast детекция отказа Heartbeat (таймаут <= 1.5 сек)
# ---------------------------------------------------------------------------


class TestHeartbeatFailFastDetection:
    """
    Сценарий 4: При зависании/отказе удаленного узла клиент не должен зависать на
    системных сокетных таймаутах (60-120с), а гарантированно завершать probe с ошибкой
    в пределах fail-fast лимита 1.5 сек.
    """

    @pytest.mark.asyncio
    async def test_heartbeat_manager_probe_fail_fast_when_node_hangs(self) -> None:
        """
        Имитирует узел, который принимает TCP-соединение, но «зависает» и перестает
        отвечать на heartbeat-запросы.
        Probe должен прерываться ровно за timeout_sec (<= 1.5s) с переходом в UNREACHABLE.
        """

        hung_writers: list[asyncio.StreamWriter] = []

        # Запускаем «зависший» сервер: принимает соединение, но никогда не шлет ответ
        async def hung_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            hung_writers.append(writer)
            try:
                data = await reader.read(1024)
                if data:
                    while True:
                        await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()

        hung_server = await asyncio.start_server(hung_handler, "127.0.0.1", 0)
        hung_port = hung_server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=hung_port)
        await client.connect()

        # Fail-fast конфигурация: таймаут 1.5 сек, max_missed = 1
        hb_cfg = HeartbeatConfig(interval_sec=2.0, timeout_sec=1.5, max_missed=1)
        hb = HeartbeatManager(client=client, config=hb_cfg)

        t0 = time.perf_counter()
        try:
            with pytest.raises(HeartbeatTimeoutError) as exc_info:
                await hb.probe()

            elapsed = time.perf_counter() - t0

            # Проверяем, что вызов завершился оперативно около 1.5 сек (не завис на минуты)
            assert 1.4 <= elapsed <= 1.8
            assert "не ответил на heartbeat probe" in str(exc_info.value)
            # Статус узла должен немедленно стать UNREACHABLE
            assert hb.state == ConnectionState.UNREACHABLE

        finally:
            await hb.stop()
            await client.close()
            for w in hung_writers:
                w.close()
            hung_server.close()
            await hung_server.wait_closed()

    @pytest.mark.asyncio
    async def test_high_level_client_ping_fail_fast_timeout(self) -> None:
        """
        Проверка BridgeClient.ping(): при зависшем узле клиент выбрасывает
        BridgeTimeoutError строго в течение 1.5 сек.
        """
        srv_writers: list[asyncio.StreamWriter] = []

        async def unresponsive_handler(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            srv_writers.append(writer)
            try:
                chunk = await reader.read(512)
                if chunk:
                    while True:
                        await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()

        srv = await asyncio.start_server(unresponsive_handler, "127.0.0.1", 0)
        srv_port = srv.sockets[0].getsockname()[1]

        cfg = BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=srv_port),
            heartbeat=HeartbeatConfig(timeout_sec=1.5),
            logging=LoggingConfig(dev_mode=True),
        )
        client = BridgeClient(config=cfg)
        await client.connect()

        t0 = time.perf_counter()
        try:
            with pytest.raises(BridgeTimeoutError) as exc_info:
                await client.ping(timeout_sec=1.5)

            elapsed = time.perf_counter() - t0
            assert 1.4 <= elapsed <= 1.8
            assert "Превышен таймаут" in str(exc_info.value)

        finally:
            await client.close()
            for w in srv_writers:
                w.close()
            srv.close()
            await srv.wait_closed()

    @pytest.mark.asyncio
    async def test_heartbeat_probe_immediate_failure_on_closed_port(self) -> None:
        """
        При попытке probe к полностью мертвому/закрытому порту, ошибка возникает
        мгновенно (< 0.5 сек) без ожидания таймаута, и статус переходит в UNREACHABLE.
        """
        import socket

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead_port = s.getsockname()[1]
        s.close()

        dead_client = AsyncTransportClient(host="127.0.0.1", port=dead_port, connect_timeout=0.2)
        hb_cfg = HeartbeatConfig(timeout_sec=1.5, max_missed=1)
        hb = HeartbeatManager(client=dead_client, config=hb_cfg)

        t0 = time.perf_counter()
        with pytest.raises(HeartbeatTimeoutError):
            await hb.probe()

        elapsed = time.perf_counter() - t0
        # Мгновенная ошибка соединения
        assert elapsed < 0.6
        assert hb.state == ConnectionState.UNREACHABLE
