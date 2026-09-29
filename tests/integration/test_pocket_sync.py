"""
tests/integration/test_pocket_sync.py — Интеграционные тесты сквозного взаимодействия
подсистем «Карман» (Pocket Sync) и «Записки» (Notes) через сетевой RPC транспорт.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest

from bridge_agent_win.service import WindowsBridgeService
from bridge_core.config import BridgeConfig, ConnectionConfig, LoggingConfig, PocketConfig
from bridge_core.models import (
    NodeOS,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteMarkReadParams,
    NoteMarkReadResult,
    NoteSendParams,
    PocketManifestResult,
    PocketPullParams,
    PocketPullResult,
    PocketPushParams,
    PocketPushResult,
    RpcErrorCode,
    RpcMethod,
)
from bridge_core.pocket import PocketManager, sync_pocket
from bridge_core.transport import AsyncTransportClient, RpcCallError


@pytest.fixture
async def running_service(tmp_path: Path):
    """Фикстура: запускает WindowsBridgeService на свободном порту с изолированным карманом."""
    pocket_dir = tmp_path / "server_pocket"
    pocket_dir.mkdir()

    cfg = BridgeConfig(
        connection=ConnectionConfig(host="127.0.0.1", port=0),
        pocket=PocketConfig(path=str(pocket_dir)),
        logging=LoggingConfig(dev_mode=True),
    )
    svc = WindowsBridgeService(config=cfg)
    await svc.start()

    # Извлекаем назначенный ОС ephemeral-порт
    assert svc.server._server is not None
    sockets = svc.server._server.sockets
    assert sockets
    real_port = sockets[0].getsockname()[1]

    yield svc, real_port, pocket_dir

    await svc.stop()


@pytest.mark.asyncio
async def test_integration_pocket_manifest_rpc(running_service) -> None:
    _svc, port, pocket_dir = running_service

    # Создаём тестовые файлы на сервере
    (pocket_dir / "doc1.txt").write_text("Hello from server pocket", encoding="utf-8")
    (pocket_dir / "sub").mkdir()
    (pocket_dir / "sub" / "doc2.bin").write_bytes(b"\x01\x02\x03\x04")

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        raw_manifest = await client.call(RpcMethod.POCKET_MANIFEST)
        manifest = PocketManifestResult.model_validate(raw_manifest)

        assert manifest.file_count == 2
        paths = [f.path for f in manifest.files]
        assert "doc1.txt" in paths
        assert "sub/doc2.bin" in paths
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_pocket_pull_and_push_rpc(running_service) -> None:
    _svc, port, pocket_dir = running_service

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        # 1. PUSH: Клиент загружает файл на сервер
        payload = b"Client pushed content 12345"
        payload_sha = hashlib.sha256(payload).hexdigest()

        push_params = PocketPushParams(
            path="uploaded.txt",
            offset=0,
            data_b64=base64.b64encode(payload).decode("ascii"),
            is_last=True,
            sha256_full=payload_sha,
        )
        raw_push = await client.call(RpcMethod.POCKET_PUSH, push_params.model_dump())
        push_res = PocketPushResult.model_validate(raw_push)

        assert push_res.completed
        assert push_res.sha256 == payload_sha
        assert (pocket_dir / "uploaded.txt").read_bytes() == payload

        # 2. PULL: Клиент скачивает этот файл обратно
        pull_params = PocketPullParams(path="uploaded.txt", offset=0, chunk_size=1024)
        raw_pull = await client.call(RpcMethod.POCKET_PULL, pull_params.model_dump())
        pull_res = PocketPullResult.model_validate(raw_pull)

        assert pull_res.is_last
        downloaded_bytes = base64.b64decode(pull_res.data_b64)
        assert downloaded_bytes == payload
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_pocket_large_file_multichunk(running_service) -> None:
    _svc, port, pocket_dir = running_service

    # 512 КБ бинарных данных (8 чанков по 64 КБ)
    large_data = os.urandom(512 * 1024)
    full_sha = hashlib.sha256(large_data).hexdigest()
    chunk_size = 64 * 1024

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        # Отправляем чанками
        offset = 0
        total_size = len(large_data)
        while offset < total_size:
            chunk = large_data[offset : offset + chunk_size]
            is_last = (offset + len(chunk)) >= total_size
            push_params = PocketPushParams(
                path="large_file.bin",
                offset=offset,
                data_b64=base64.b64encode(chunk).decode("ascii"),
                is_last=is_last,
                sha256_full=full_sha if is_last else None,
            )
            raw_res = await client.call(RpcMethod.POCKET_PUSH, push_params.model_dump())
            res = PocketPushResult.model_validate(raw_res)
            if is_last:
                assert res.completed
                assert res.sha256 == full_sha
            offset += len(chunk)

        # Проверяем, что файл на сервере полностью идентичен
        server_file = pocket_dir / "large_file.bin"
        assert server_file.exists()
        assert server_file.stat().st_size == total_size
        assert hashlib.sha256(server_file.read_bytes()).hexdigest() == full_sha
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_sync_pocket_bidirectional(running_service, tmp_path: Path) -> None:
    _svc, port, server_pocket = running_service

    # Настраиваем клиентский локальный карман
    client_pocket_dir = tmp_path / "client_pocket"
    client_pocket_dir.mkdir()
    client_manager = PocketManager(pocket_dir=client_pocket_dir)

    # Локальный файл на клиенте (должен отправиться на сервер)
    (client_pocket_dir / "client_only.txt").write_text("client secret", encoding="utf-8")

    # Удалённый файл на сервере (должен скачаться на клиент)
    (server_pocket / "server_only.txt").write_text("server payload", encoding="utf-8")

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        summary = await sync_pocket(client=client, local_manager=client_manager, direction="both")

        assert "server_only.txt" in summary.pulled
        assert "client_only.txt" in summary.pushed
        assert len(summary.errors) == 0

        # Проверяем, что файлы появились по обе стороны
        assert (client_pocket_dir / "server_only.txt").exists()
        assert (server_pocket / "client_only.txt").exists()
        assert (client_pocket_dir / "server_only.txt").read_text(
            encoding="utf-8"
        ) == "server payload"
        assert (server_pocket / "client_only.txt").read_text(encoding="utf-8") == "client secret"

        # Повторный sync должен определить, что всё уже синхронизировано
        summary2 = await sync_pocket(client=client, local_manager=client_manager, direction="both")
        assert len(summary2.pulled) == 0
        assert len(summary2.pushed) == 0
        assert len(summary2.synced) == 2
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_notes_flow_rpc(running_service) -> None:
    _svc, port, _pocket_dir = running_service

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        # 1. Отправляем заметку
        send_params = NoteSendParams(
            text="Срочно проверить службу на Windows",
            author_os=NodeOS.LINUX,
            target_node="win-srv",
        )
        raw_delivery = await client.call(RpcMethod.NOTES_SEND, send_params.model_dump())
        assert raw_delivery["note_id"]
        assert raw_delivery["status"] == "delivered"
        note_id = raw_delivery["note_id"]

        # 2. Получаем историю заметок
        raw_hist = await client.call(
            RpcMethod.NOTES_HISTORY, NoteHistoryParams(limit=10).model_dump()
        )
        hist = NoteHistoryResult.model_validate(raw_hist)
        assert hist.total_count == 1
        assert hist.notes[0].note_id == note_id
        assert hist.notes[0].text == "Срочно проверить службу на Windows"
        assert hist.notes[0].status == "delivered"

        # 3. Квитируем прочтение (mark_read)
        mark_params = NoteMarkReadParams(note_ids=[note_id])
        raw_mark = await client.call(RpcMethod.NOTES_MARK_READ, mark_params.model_dump())
        mark_res = NoteMarkReadResult.model_validate(raw_mark)
        assert mark_res.marked_count == 1

        # 4. Проверяем, что в истории статус обновился на 'read'
        raw_hist2 = await client.call(
            RpcMethod.NOTES_HISTORY, NoteHistoryParams(limit=10).model_dump()
        )
        hist2 = NoteHistoryResult.model_validate(raw_hist2)
        assert hist2.notes[0].status == "read"
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_pocket_tampered_sha_rejected(running_service) -> None:
    _svc, port, pocket_dir = running_service

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        bad_sha = "f" * 64
        push_params = PocketPushParams(
            path="spoofed.txt",
            offset=0,
            data_b64=base64.b64encode(b"original data").decode("ascii"),
            is_last=True,
            sha256_full=bad_sha,
        )

        with pytest.raises(RpcCallError) as exc_info:
            await client.call(RpcMethod.POCKET_PUSH, push_params.model_dump())

        assert exc_info.value.code == RpcErrorCode.POCKET_SYNC_ERROR
        # Файл не должен сохраниться на сервере
        assert not (pocket_dir / "spoofed.txt").exists()
        assert not (pocket_dir / ".spoofed.txt.part").exists()
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_audit_log_records_pocket_and_notes(running_service) -> None:
    _svc, port, pocket_dir = running_service

    client = AsyncTransportClient(host="127.0.0.1", port=port)
    await client.connect()

    try:
        # Делаем вызовы manifest, push и note send
        await client.call(RpcMethod.POCKET_MANIFEST)
        await client.call(
            RpcMethod.POCKET_PUSH,
            PocketPushParams(
                path="logged.txt",
                offset=0,
                data_b64=base64.b64encode(b"logged").decode("ascii"),
                is_last=True,
                sha256_full=hashlib.sha256(b"logged").hexdigest(),
            ).model_dump(),
        )
        await client.call(
            RpcMethod.NOTES_SEND,
            NoteSendParams(text="test note", author_os=NodeOS.LINUX).model_dump(),
        )
    finally:
        await client.disconnect()

    # Проверяем аудит-лог
    logs_dir = pocket_dir / "logs"
    assert logs_dir.exists()
    log_files = list(logs_dir.glob("*.jsonl"))
    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8")
    assert "pocket.manifest" in content
    assert "pocket.push" in content
    assert "notes.send" in content
