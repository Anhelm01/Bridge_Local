"""
Тесты для bridge_core.protocol — фрейминг, валидация и парсинг JSON-RPC.
"""

from __future__ import annotations

import asyncio

import pytest

from bridge_core.models import (
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    MAX_PAYLOAD_SIZE,
    JsonRpcError,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
)
from bridge_core.protocol import (
    FrameTooLargeError,
    InvalidMagicError,
    MalformedJsonRpcError,
    encode_frame,
    encode_jsonrpc,
    parse_jsonrpc,
    read_frame,
    write_frame,
)


class TestFraming:
    """Тесты бинарного фрейминга (encode_frame, read_frame, write_frame)."""

    def test_encode_frame_structure(self) -> None:
        payload = b"hello"
        frame = encode_frame(payload)
        assert frame[:2] == FRAME_MAGIC
        assert len(frame) == FRAME_HEADER_SIZE + len(payload)

    def test_encode_frame_string_utf8(self) -> None:
        frame = encode_frame("Привет мир")
        expected_len = len("Привет мир".encode())
        assert len(frame) == FRAME_HEADER_SIZE + expected_len

    def test_encode_frame_too_large(self) -> None:
        with pytest.raises(FrameTooLargeError):
            encode_frame(b"x" * (MAX_PAYLOAD_SIZE + 1))

    @pytest.mark.asyncio
    async def test_read_write_frame_roundtrip(self) -> None:
        """Проверяем запись и чтение фрейма через реальный loopback сокет."""
        received_payload: bytes | None = None

        async def handle_client(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            nonlocal received_payload
            received_payload = await read_frame(r)
            w.close()
            await w.wait_closed()

        server = await asyncio.start_server(handle_client, host="127.0.0.1", port=0)
        port = server.sockets[0].getsockname()[1]

        _client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
        test_payload = b'{"jsonrpc": "2.0", "id": "1", "method": "test"}'
        await write_frame(client_writer, test_payload)

        # Ждём получения сервером
        await asyncio.sleep(0.05)
        client_writer.close()
        await client_writer.wait_closed()
        server.close()
        await server.wait_closed()

        assert received_payload == test_payload

    @pytest.mark.asyncio
    async def test_read_frame_invalid_magic(self) -> None:
        reader = asyncio.StreamReader()
        bad_frame = b"XX\x00\x00\x00\x05hello"
        reader.feed_data(bad_frame)
        reader.feed_eof()

        with pytest.raises(InvalidMagicError):
            await read_frame(reader)

    @pytest.mark.asyncio
    async def test_read_frame_too_large(self) -> None:
        reader = asyncio.StreamReader()
        # Длина 1000 при лимите 500
        header = FRAME_MAGIC + (1000).to_bytes(4, "big")
        reader.feed_data(header + b"x" * 1000)
        reader.feed_eof()

        with pytest.raises(FrameTooLargeError):
            await read_frame(reader, max_payload_size=500)


class TestJsonRpcParsing:
    """Тесты парсера JSON-RPC сообщений."""

    def test_parse_request(self) -> None:
        req = JsonRpcRequest(method="exec.run", params={"cmd": "dir"})
        raw = encode_jsonrpc(req)
        parsed = parse_jsonrpc(raw)
        assert isinstance(parsed, JsonRpcRequest)
        assert parsed.method == "exec.run"
        assert parsed.params == {"cmd": "dir"}

    def test_parse_response(self) -> None:
        resp = JsonRpcResponse(id="123", result={"status": "ok"})
        raw = encode_jsonrpc(resp)
        parsed = parse_jsonrpc(raw)
        assert isinstance(parsed, JsonRpcResponse)
        assert parsed.id == "123"
        assert parsed.result == {"status": "ok"}

    def test_parse_error_response(self) -> None:
        err = JsonRpcErrorResponse(
            id="456",
            error=JsonRpcError(code=-32001, message="Timeout occurred"),
        )
        raw = encode_jsonrpc(err)
        parsed = parse_jsonrpc(raw)
        assert isinstance(parsed, JsonRpcErrorResponse)
        assert parsed.error.code == -32001

    def test_parse_malformed_json(self) -> None:
        with pytest.raises(MalformedJsonRpcError):
            parse_jsonrpc(b"{not json}")

    def test_parse_invalid_version(self) -> None:
        with pytest.raises(MalformedJsonRpcError):
            parse_jsonrpc(b'{"jsonrpc": "1.0", "method": "test"}')

    def test_parse_not_dict(self) -> None:
        with pytest.raises(MalformedJsonRpcError):
            parse_jsonrpc(b'["list", "not", "dict"]')
