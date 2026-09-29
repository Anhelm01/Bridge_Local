"""
Тесты для bridge_core.models — валидация всех DTO контрактов.

Покрывает:
  - Сериализацию / десериализацию каждой модели (roundtrip).
  - Валидацию ограничений полей (min, max, required).
  - Генерацию значений по умолчанию (uuid, timestamps).
  - Корректность enum-значений.
  - Контракты JSON-RPC обёрток.
  - Wire protocol константы.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from bridge_core.models import (
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    MAX_PAYLOAD_SIZE,
    AuditLogEntry,
    AuditStatus,
    ConnectionState,
    ExecRequestParams,
    ExecResult,
    ExecTimeoutErrorData,
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    NodeOS,
    NodeStatus,
    NoteDeliveryResult,
    NoteEntry,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteSendParams,
    NoteStatus,
    PingParams,
    PocketFileInfo,
    PocketManifestResult,
    PocketPullParams,
    PocketPushParams,
    PongResult,
    RpcErrorCode,
    RpcMethod,
)

# ===================================================================
# Enums
# ===================================================================


class TestEnums:
    """Тесты перечислений."""

    def test_node_os_values(self) -> None:
        assert NodeOS.LINUX == "linux"
        assert NodeOS.WINDOWS == "windows"

    def test_node_status_values(self) -> None:
        assert NodeOS(NodeOS.LINUX) == NodeOS.LINUX
        assert NodeStatus.READY == "ready"
        assert NodeStatus.BUSY == "busy"
        assert NodeStatus.SHUTTING_DOWN == "shutting_down"

    def test_connection_state_values(self) -> None:
        assert ConnectionState.DISCONNECTED == "disconnected"
        assert ConnectionState.CONNECTED == "connected"
        assert ConnectionState.UNREACHABLE == "unreachable"

    def test_audit_status_values(self) -> None:
        assert AuditStatus.SUCCESS == "success"
        assert AuditStatus.TIMEOUT == "timeout"

    def test_note_status_values(self) -> None:
        assert NoteStatus.DELIVERED == "delivered"
        assert NoteStatus.READ == "read"


# ===================================================================
# JSON-RPC 2.0
# ===================================================================


class TestJsonRpc:
    """Тесты JSON-RPC обёрток."""

    def test_request_defaults(self) -> None:
        req = JsonRpcRequest(method="heartbeat.ping")
        assert req.jsonrpc == "2.0"
        assert req.method == "heartbeat.ping"
        assert len(req.id) > 0  # uuid generated
        assert req.params == {}

    def test_request_custom_id(self) -> None:
        req = JsonRpcRequest(method="exec.run", id="my-id-123", params={"command": "ls"})
        assert req.id == "my-id-123"
        assert req.params == {"command": "ls"}

    def test_request_roundtrip_json(self) -> None:
        req = JsonRpcRequest(
            method="exec.run",
            id="test-1",
            params={"x": 42},
            source_node="workstation-lin",
            target_node="win-gaming",
        )
        json_str = req.model_dump_json()
        restored = JsonRpcRequest.model_validate_json(json_str)
        assert restored.method == req.method
        assert restored.id == req.id
        assert restored.params == req.params
        assert restored.source_node == "workstation-lin"
        assert restored.target_node == "win-gaming"

    def test_response_roundtrip(self) -> None:
        resp = JsonRpcResponse(id="req-1", result={"exit_code": 0, "stdout": "hello"})
        data = resp.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["result"]["exit_code"] == 0

    def test_error_response(self) -> None:
        err = JsonRpcErrorResponse(
            id="req-2",
            error=JsonRpcError(
                code=RpcErrorCode.COMMAND_TIMEOUT,
                message="Command timed out",
                data={"timeout_sec": 30},
            ),
        )
        assert err.error.code == -32001
        assert err.error.data == {"timeout_sec": 30}

    def test_error_response_no_data(self) -> None:
        err = JsonRpcErrorResponse(
            id="req-3",
            error=JsonRpcError(code=RpcErrorCode.AUTH_FAILED, message="Auth failed"),
        )
        assert err.error.data is None


# ===================================================================
# Heartbeat
# ===================================================================


class TestHeartbeat:
    """Тесты моделей Ping/Pong."""

    def test_ping_auto_timestamp(self) -> None:
        ping = PingParams(client_os=NodeOS.LINUX)
        assert ping.client_timestamp_us > 0
        assert ping.client_os == NodeOS.LINUX

    def test_pong_roundtrip(self) -> None:
        pong = PongResult(
            agent_os=NodeOS.WINDOWS,
            cpu_percent=25.5,
            memory_used_mb=4096,
            uptime_seconds=3600,
            status=NodeStatus.READY,
        )
        data = json.loads(pong.model_dump_json())
        restored = PongResult.model_validate(data)
        assert restored.cpu_percent == 25.5
        assert restored.status == NodeStatus.READY

    def test_pong_validation_cpu_range(self) -> None:
        with pytest.raises(ValidationError):
            PongResult(
                agent_os=NodeOS.WINDOWS,
                cpu_percent=150.0,  # > 100
                memory_used_mb=4096,
                uptime_seconds=3600,
                status=NodeStatus.READY,
            )


# ===================================================================
# Exec
# ===================================================================


class TestExec:
    """Тесты моделей удалённого выполнения."""

    def test_exec_request_defaults(self) -> None:
        req = ExecRequestParams(command="Get-Process")
        assert req.timeout_sec == 30
        assert req.run_as_admin is True
        assert req.working_dir is None
        assert req.env is None

    def test_exec_request_custom(self) -> None:
        req = ExecRequestParams(
            command="dir C:\\",
            timeout_sec=60,
            run_as_admin=False,
            working_dir="C:\\Users",
        )
        assert req.timeout_sec == 60
        assert req.run_as_admin is False

    def test_exec_request_empty_command_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecRequestParams(command="")

    def test_exec_request_timeout_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ExecRequestParams(command="ls", timeout_sec=0)
        with pytest.raises(ValidationError):
            ExecRequestParams(command="ls", timeout_sec=3601)

    def test_exec_result_roundtrip(self) -> None:
        result = ExecResult(
            exit_code=0,
            stdout="Hello, мир!",
            stderr="",
            duration_ms=150,
            started_at="2026-09-30T00:00:00Z",
            completed_at="2026-09-30T00:00:00.150Z",
        )
        data = json.loads(result.model_dump_json())
        restored = ExecResult.model_validate(data)
        assert restored.stdout == "Hello, мир!"
        assert restored.timed_out is False

    def test_exec_timeout_error_data(self) -> None:
        err = ExecTimeoutErrorData(
            timeout_sec=5,
            duration_ms=5012,
            partial_stdout="partial...",
            processes_killed=[1234, 5678],
        )
        assert len(err.processes_killed) == 2
        assert err.timeout_sec == 5


# ===================================================================
# Notes
# ===================================================================


class TestNotes:
    """Тесты моделей записок."""

    def test_note_send(self) -> None:
        note = NoteSendParams(text="Тестовая записка", author_os=NodeOS.LINUX)
        assert note.text == "Тестовая записка"
        assert note.author_os == NodeOS.LINUX

    def test_note_send_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NoteSendParams(text="", author_os=NodeOS.LINUX)

    def test_note_send_max_length(self) -> None:
        with pytest.raises(ValidationError):
            NoteSendParams(text="x" * 10001, author_os=NodeOS.LINUX)

    def test_note_delivery(self) -> None:
        delivery = NoteDeliveryResult(note_id="note-001")
        assert delivery.status == NoteStatus.DELIVERED
        assert len(delivery.received_at) > 0

    def test_note_history_defaults(self) -> None:
        params = NoteHistoryParams()
        assert params.limit == 50
        assert params.since is None

    def test_note_history_result(self) -> None:
        result = NoteHistoryResult(
            notes=[
                NoteEntry(
                    note_id="n1",
                    timestamp="2026-09-30T00:00:00Z",
                    author_os=NodeOS.WINDOWS,
                    text="Привет с Windows",
                    status=NoteStatus.DELIVERED,
                ),
            ],
            total_count=1,
        )
        assert len(result.notes) == 1
        assert result.notes[0].author_os == NodeOS.WINDOWS


# ===================================================================
# Pocket Sync
# ===================================================================


class TestPocketSync:
    """Тесты моделей синхронизации кармана."""

    def test_file_info(self) -> None:
        fi = PocketFileInfo(
            path="doc.pdf",
            sha256="a" * 64,
            size_bytes=1024,
            mtime_iso="2026-09-30T00:00:00Z",
        )
        assert fi.path == "doc.pdf"
        assert len(fi.sha256) == 64

    def test_file_info_bad_sha256_length(self) -> None:
        with pytest.raises(ValidationError):
            PocketFileInfo(
                path="doc.pdf",
                sha256="tooshort",
                size_bytes=1024,
                mtime_iso="2026-09-30T00:00:00Z",
            )

    def test_manifest_empty(self) -> None:
        manifest = PocketManifestResult(files=[], total_size_bytes=0, file_count=0)
        assert manifest.file_count == 0

    def test_pull_params_defaults(self) -> None:
        pull = PocketPullParams(path="file.txt")
        assert pull.offset == 0
        assert pull.chunk_size == 65536

    def test_pull_params_max_chunk(self) -> None:
        with pytest.raises(ValidationError):
            PocketPullParams(path="file.txt", chunk_size=5_000_000)  # > 4MB

    def test_push_params(self) -> None:
        push = PocketPushParams(
            path="upload.bin",
            offset=0,
            data_b64="SGVsbG8=",
            is_last=True,
            sha256_full="b" * 64,
        )
        assert push.is_last is True
        assert push.sha256_full == "b" * 64


# ===================================================================
# Audit Log
# ===================================================================


class TestAuditLog:
    """Тесты модели аудит-лога."""

    def test_audit_entry_exec(self) -> None:
        entry = AuditLogEntry(
            session_id="sess-001",
            client_ip="192.168.1.100",
            method=RpcMethod.EXEC_RUN,
            request_id="req-001",
            command="Get-Date",
            timeout_sec=30,
            exit_code=0,
            duration_ms=120,
            stdout_preview="Wednesday, September 30, 2026",
            status=AuditStatus.SUCCESS,
        )
        json_line = entry.model_dump_json()
        restored = AuditLogEntry.model_validate_json(json_line)
        assert restored.method == "exec.run"
        assert restored.status == AuditStatus.SUCCESS
        assert restored.command == "Get-Date"

    def test_audit_entry_jsonl_format(self) -> None:
        """Проверяем, что сериализация даёт валидный однострочный JSON (JSONL-совместимость)."""
        entry = AuditLogEntry(
            session_id="s1",
            client_ip="10.0.0.1",
            method="notes.send",
            request_id="r1",
            status=AuditStatus.SUCCESS,
        )
        line = entry.model_dump_json()
        # Должна быть одна строка без переносов
        assert "\n" not in line
        # Должен парситься как валидный JSON
        parsed = json.loads(line)
        assert parsed["session_id"] == "s1"

    def test_audit_entry_auto_timestamp(self) -> None:
        entry = AuditLogEntry(
            session_id="s2",
            client_ip="10.0.0.2",
            method="exec.run",
            request_id="r2",
            status=AuditStatus.ERROR,
        )
        assert len(entry.ts) > 10  # ISO timestamp generated


# ===================================================================
# Wire Protocol Constants
# ===================================================================


class TestWireProtocol:
    """Тесты констант wire protocol."""

    def test_magic_bytes(self) -> None:
        assert FRAME_MAGIC == b"\x42\x52"
        assert FRAME_MAGIC == b"BR"

    def test_header_size(self) -> None:
        assert FRAME_HEADER_SIZE == 6  # 2 (magic) + 4 (length)

    def test_max_payload(self) -> None:
        assert MAX_PAYLOAD_SIZE == 64 * 1024 * 1024

    def test_rpc_method_constants(self) -> None:
        assert RpcMethod.HEARTBEAT_PING == "heartbeat.ping"
        assert RpcMethod.EXEC_RUN == "exec.run"
        assert RpcMethod.NOTES_SEND == "notes.send"
        assert RpcMethod.POCKET_MANIFEST == "pocket.manifest"
        assert RpcMethod.POCKET_PULL == "pocket.pull"
        assert RpcMethod.POCKET_PUSH == "pocket.push"

    def test_error_codes(self) -> None:
        assert RpcErrorCode.COMMAND_TIMEOUT == -32001
        assert RpcErrorCode.AUTH_FAILED == -32003
        assert RpcErrorCode.PARSE_ERROR == -32700
