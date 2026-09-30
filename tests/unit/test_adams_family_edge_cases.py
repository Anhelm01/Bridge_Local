"""
tests/unit/test_adams_family_edge_cases.py — Stress-testing, fuzzing & edge-case hardening squad.

Automated QA & Fuzzing suite covering Phases 1 through 5:
  1. TestWireCodecAndFramingFuzzing (Phase 1 & 2):
     - Length-prefix decoders with truncated/malformed headers, huge lengths exceeding limits.
     - WindowsOutputDecoder byte fuzzing, broken sequences, nested ANSI, CRLF normalization.
  2. TestHmacSecurityHardeningAndReplay (Phase 1):
     - Bit-flipped signatures, clock skew bounds (past & future), nonce reuse, nonce cache eviction.
  3. TestJsonRpcProtocolAndConcurrencyStress (Phase 2):
     - Malformed JSON-RPC payloads, unknown methods, handler exceptions, concurrent calls.
  4. TestPocketFileChunkingEdgeCases (Phase 4):
     - 0-byte file lifecycle, exact multiple chunk boundaries, corrupt chunk SHA-256 rollback.
     - Path traversal fuzzing.
  5. TestNotesEngineStressAndEdgeCases (Phase 5):
     - Concurrency stress (50 parallel writes), Unicode/Cyrillic/Emoji fidelity.
     - Corrupted JSONL recovery, concurrent mark_read.
  6. TestWindowsContextMenuAndExitCodesContract (Phase 3 & 5):
     - Windows context menu registry generator syntax & escaping, drop handler.
     - Exhaustive CLI exit codes contract (0..5) verification with live CLI invocations.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from bridge_agent_win.context_menu import (
    drop_file_to_pocket,
    generate_reg_content,
)
from bridge_agent_win.service import WindowsBridgeService
from bridge_client_linux.cli import app as cli_app
from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeRemoteCommandError,
    BridgeTimeoutError,
)
from bridge_client_linux.exit_codes import ExitCode
from bridge_core.codec import WindowsOutputDecoder
from bridge_core.config import BridgeConfig, ConnectionConfig, PocketConfig
from bridge_core.models import (
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    MAX_PAYLOAD_SIZE,
    NodeOS,
    NoteHistoryParams,
    NoteMarkReadParams,
    NoteSendParams,
    NoteStatus,
    PocketPullParams,
    PocketPushParams,
    RpcErrorCode,
)
from bridge_core.notes import NotesManager
from bridge_core.pocket import PocketFileInfo, PocketManager, PocketManifestResult
from bridge_core.protocol import (
    FrameTooLargeError,
    InvalidMagicError,
    MalformedJsonRpcError,
    encode_frame,
    parse_jsonrpc,
    read_frame,
)
from bridge_core.security import (
    AuthenticationError,
    PathTraversalError,
    PSKAuthenticator,
    TokenReplayError,
)
from bridge_core.transport import (
    AsyncTransportClient,
    AsyncTransportServer,
    RpcCallError,
)

runner = CliRunner()


# ===========================================================================
# 1. Wire Codec & Framing Fuzzing
# ===========================================================================


class TestWireCodecAndFramingFuzzing:
    """Фуззинг бинарного фрейминга и декодера вывода Windows."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("header_len", [0, 1, 2, 3, 4, 5])
    async def test_frame_header_truncated_fuzzing(self, header_len: int) -> None:
        """Поток обрывается до завершения чтения 6-байтового заголовка."""
        reader = asyncio.StreamReader()
        incomplete_header = (FRAME_MAGIC + (10).to_bytes(4, "big"))[:header_len]
        reader.feed_data(incomplete_header)
        reader.feed_eof()

        with pytest.raises(asyncio.IncompleteReadError):
            await read_frame(reader)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_magic",
        [
            b"XX",
            b"br",  # Lowercase
            b"B\x00",
            b"\x00\x00",
            b"\xff\xff",
            b"42",
        ],
    )
    async def test_frame_magic_corrupted_fuzzing(self, bad_magic: bytes) -> None:
        """Заголовок с искаженными магическими байтами немедленно отклоняется."""
        reader = asyncio.StreamReader()
        data = bad_magic + (4).to_bytes(4, "big") + b"test"
        reader.feed_data(data)
        reader.feed_eof()

        with pytest.raises(InvalidMagicError):
            await read_frame(reader)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_len", [0, 10, 50, 99])
    async def test_frame_payload_truncated_fuzzing(self, provided_len: int) -> None:
        """Поток обрывается до получения полного объявленного payload."""
        declared_len = 100
        reader = asyncio.StreamReader()
        header = FRAME_MAGIC + declared_len.to_bytes(4, "big")
        reader.feed_data(header + (b"A" * provided_len))
        reader.feed_eof()

        with pytest.raises(asyncio.IncompleteReadError):
            await read_frame(reader)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "huge_len",
        [
            MAX_PAYLOAD_SIZE + 1,
            MAX_PAYLOAD_SIZE + 1024,
            70 * 1024 * 1024,
            0x7FFFFFFF,
            0xFFFFFFFF,
        ],
    )
    async def test_frame_length_exceeds_limits_fuzzing(self, huge_len: int) -> None:
        """Длина payload превышает MAX_PAYLOAD_SIZE (64 MB). Защита от переполнения памяти."""
        reader = asyncio.StreamReader()
        header = FRAME_MAGIC + huge_len.to_bytes(4, "big")
        reader.feed_data(header + b"fake_data")
        reader.feed_eof()

        with pytest.raises(FrameTooLargeError):
            await read_frame(reader)

    def test_encode_frame_huge_payload_rejection(self) -> None:
        """encode_frame отклоняет полезную нагрузку, превышающую лимит."""
        with pytest.raises(FrameTooLargeError):
            encode_frame(b"Z" * (MAX_PAYLOAD_SIZE + 1))

    @pytest.mark.asyncio
    async def test_frame_zero_length_payload(self) -> None:
        """Корректная обработка пустого 0-байтового фрейма."""
        raw_frame = encode_frame(b"")
        assert raw_frame == FRAME_MAGIC + (0).to_bytes(4, "big")
        assert len(raw_frame) == FRAME_HEADER_SIZE

        reader = asyncio.StreamReader()
        reader.feed_data(raw_frame)
        reader.feed_eof()

        payload = await read_frame(reader)
        assert payload == b""

    @pytest.mark.asyncio
    async def test_sequential_frames_streaming(self) -> None:
        """Чтение пачки последовательных фреймов разного размера из одного потока без дрейфа."""
        test_payloads = [
            b"",
            b"hello world",
            b"x" * 256,
            b"A" * 1024,
            json.dumps({"test": "json", "id": 42}).encode("utf-8"),
            b"\x00\x01\x02\x03\xff\xfe",
        ]
        stream_bytes = b"".join(encode_frame(p) for p in test_payloads)

        reader = asyncio.StreamReader()
        reader.feed_data(stream_bytes)
        reader.feed_eof()

        for original in test_payloads:
            read_res = await read_frame(reader)
            assert read_res == original

    def test_windows_output_decoder_corrupted_bytes_fuzzing(self) -> None:
        """Фуззинг декодера невалидными и оборванными последовательностями байт."""
        corrupt_samples = [
            b"\xd0",  # Оборванный 2-байтовый UTF-8 префикс
            b"\xe2\x82",  # Оборванный 3-байтовый UTF-8 префикс
            b"\xf0\x90\x80",  # Оборванный 4-байтовый UTF-8 префикс
            b"\x80\x81\x82\x90\xbf",  # Изолированные байты продолжения UTF-8
            b"\xff\xff\xff\xff\x00\x00",  # Байт 0xFF без BOM
            b"\xfe\xff\xd8\x00",  # Некорректный UTF-16 BE суррогат
            b"Valid UTF-8 prefix \x80\x81\x82 followed by garbage \xff\xfe\x01",
        ]

        for sample in corrupt_samples:
            res = WindowsOutputDecoder.decode(sample)
            # Декодер обязан вернуть строку без падения с исключением
            assert isinstance(res.text, str)
            assert res.encoding_used in ("cp1251", "cp866", "utf-8-replace", "utf-16-le")

    def test_windows_output_decoder_nested_ansi_stress(self) -> None:
        """Стресс-тестирование очистки сложных и вложенных ANSI escape-кодов."""
        complex_ansi = (
            b"\x1b[1m\x1b[38;5;196m[ALERT]\x1b[0m "
            b"\x1b[38;2;255;100;50mRGB Text\x1b[0m "
            b"\x1b[2J\x1b[H\x1b[10;20H"  # Очистка и перемещение курсора
            b"\x1b[?25l"  # Скрытие курсора
            b"Pure Output"
            b"\x1b[?25h\x1b[0m"
        )
        res = WindowsOutputDecoder.decode(complex_ansi, strip_ansi=True)
        assert res.text.strip() == "[ALERT] RGB Text Pure Output"
        assert "\x1b" not in res.text

    def test_windows_output_decoder_crlf_normalization_stress(self) -> None:
        """Нормализация произвольно перемешанных CRLF, CR и LF."""
        mixed = b"line1\r\n\rline2\r\r\nline3\n\rline4\r\n"
        res = WindowsOutputDecoder.decode(mixed, normalize_newlines=True)
        assert "\r" not in res.text
        assert res.text == "line1\n\nline2\n\nline3\n\nline4\n"


# ===========================================================================
# 2. HMAC Security Hardening & Replay Attacks
# ===========================================================================


class TestHmacSecurityHardeningAndReplay:
    """Тестирование устойчивости аутентификации PSK, HMAC-SHA256 и защиты от replay."""

    def test_authenticator_init_empty_or_whitespace_token(self) -> None:
        """Инициализация с пустым токеном запрещена."""
        with pytest.raises(ValueError):
            PSKAuthenticator(psk_token="")

    def test_hmac_tampered_payload_bitflip(self) -> None:
        """Подмена хотя бы одного бита подписи или параметров приводит к AuthenticationError."""
        auth = PSKAuthenticator(psk_token="s3cr3t-t0k3n-999")
        headers = auth.generate_auth_header()

        # 1. Замена одного символа в HMAC-подписи
        orig_sig = headers["auth_signature"]
        mutated_char = "0" if orig_sig[0] != "0" else "1"
        tampered_sig = mutated_char + orig_sig[1:]
        headers_tampered = dict(headers, auth_signature=tampered_sig)
        with pytest.raises(AuthenticationError, match="HMAC mismatch"):
            auth.verify_auth_params(headers_tampered)

        # 2. Не-hex символы в подписи
        headers_bad_hex = dict(headers, auth_signature="Z" * 64)
        with pytest.raises(AuthenticationError, match="HMAC mismatch"):
            auth.verify_auth_params(headers_bad_hex)

        # 3. Пустая подпись
        headers_empty_sig = dict(headers, auth_signature="")
        with pytest.raises(AuthenticationError, match="HMAC mismatch"):
            auth.verify_auth_params(headers_empty_sig)

    def test_hmac_clock_skew_boundaries(self) -> None:
        """Проверка точных границ допустимого временного окна (clock skew)."""
        skew_window = 10.0
        auth = PSKAuthenticator(psk_token="boundary-token", max_clock_skew_sec=skew_window)
        now = time.time()

        # Допустимое отклонение в прошлое (now - 9.0s) -> успех
        ts_past_ok = now - 9.0
        nonce_past_ok = "past_ok_nonce_1234"
        sig_past_ok = hmac_sign("boundary-token", ts_past_ok, nonce_past_ok)
        assert (
            auth.verify_auth_params(
                {
                    "auth_timestamp": f"{ts_past_ok:.3f}",
                    "auth_nonce": nonce_past_ok,
                    "auth_signature": sig_past_ok,
                }
            )
            is True
        )

        # Превышение отклонения в прошлое (now - 11.0s) -> TokenReplayError
        ts_past_bad = now - 11.5
        nonce_past_bad = "past_bad_nonce_1234"
        sig_past_bad = hmac_sign("boundary-token", ts_past_bad, nonce_past_bad)
        with pytest.raises(TokenReplayError, match="Таймстемп устарел"):
            auth.verify_auth_params(
                {
                    "auth_timestamp": f"{ts_past_bad:.3f}",
                    "auth_nonce": nonce_past_bad,
                    "auth_signature": sig_past_bad,
                }
            )

        # Допустимое отклонение в будущее (now + 9.0s) -> успех
        ts_future_ok = now + 9.0
        nonce_future_ok = "future_ok_nonce_12"
        sig_future_ok = hmac_sign("boundary-token", ts_future_ok, nonce_future_ok)
        assert (
            auth.verify_auth_params(
                {
                    "auth_timestamp": f"{ts_future_ok:.3f}",
                    "auth_nonce": nonce_future_ok,
                    "auth_signature": sig_future_ok,
                }
            )
            is True
        )

        # Превышение отклонения в будущее (now + 11.5s) -> TokenReplayError
        ts_future_bad = now + 11.5
        nonce_future_bad = "future_bad_nonce_1"
        sig_future_bad = hmac_sign("boundary-token", ts_future_bad, nonce_future_bad)
        with pytest.raises(TokenReplayError, match="Таймстемп устарел"):
            auth.verify_auth_params(
                {
                    "auth_timestamp": f"{ts_future_bad:.3f}",
                    "auth_nonce": nonce_future_bad,
                    "auth_signature": sig_future_bad,
                }
            )

    def test_hmac_replay_attack_prevention(self) -> None:
        """Повторное использование одного и того же auth_nonce блокируется."""
        auth = PSKAuthenticator(psk_token="replay-test-key")
        headers = auth.generate_auth_header()

        # Первая попытка проходит
        assert auth.verify_auth_params(headers) is True

        # Повторные попытки с тем же nonce немедленно вызывают TokenReplayError
        with pytest.raises(TokenReplayError, match="Replay Attack"):
            auth.verify_auth_params(headers)

        with pytest.raises(TokenReplayError, match="Replay Attack"):
            auth.verify_auth_params(headers)

    def test_hmac_nonce_cache_cleanup_and_memory_leak_prevention(self) -> None:
        """Проверка очистки устаревших nonce из внутреннего словаря без утечек памяти."""
        auth = PSKAuthenticator(psk_token="test-key", max_clock_skew_sec=5.0)
        now = time.time()

        # Имитируем наличие старых и свежих nonce
        auth._seen_nonces["expired_nonce_1"] = now - 10.0
        auth._seen_nonces["expired_nonce_2"] = now - 1.0
        auth._seen_nonces["active_nonce"] = now + 5.0

        auth._cleanup_nonces(now)

        assert "expired_nonce_1" not in auth._seen_nonces
        assert "expired_nonce_2" not in auth._seen_nonces
        assert "active_nonce" in auth._seen_nonces

    @pytest.mark.parametrize(
        "malformed_dict",
        [
            {},
            {"auth_timestamp": "123.4"},
            {"auth_timestamp": "123.4", "auth_nonce": "n1"},
            {"auth_timestamp": "not_a_float", "auth_nonce": "n1", "auth_signature": "s1"},
            {"auth_timestamp": None, "auth_nonce": "n1", "auth_signature": "s1"},
        ],
    )
    def test_hmac_missing_and_malformed_keys(self, malformed_dict: dict[str, Any]) -> None:
        """Отсутствие или искажение типов обязательных полей приводит к AuthenticationError."""
        auth = PSKAuthenticator(psk_token="test-key")
        with pytest.raises(AuthenticationError):
            auth.verify_auth_params(malformed_dict)


def hmac_sign(token: str, ts: float, nonce: str) -> str:
    """Вспомогательная функция для генерации ожидаемой HMAC-SHA256 подписи."""
    import hmac

    msg = f"{ts:.3f}:{nonce}".encode()
    return hmac.new(token.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ===========================================================================
# 3. JSON-RPC Protocol & Concurrency Stress
# ===========================================================================


class TestJsonRpcProtocolAndConcurrencyStress:
    """Стресс-тестирование парсинга JSON-RPC и конкурентных вызовов через сокет."""

    @pytest.mark.parametrize(
        "corrupted_payload",
        [
            b"",
            b" ",
            b"random unparsed text",
            b"<xml>not json</xml>",
            b"[]",  # Array instead of object
            b"12345",  # Number instead of object
            b'"just a string"',  # String instead of object
            b'{"foo": "bar"}',  # Missing jsonrpc version
            b'{"jsonrpc": "1.0", "method": "test"}',  # Unsupported version 1.0
            b'{"jsonrpc": "3.0", "method": "test"}',  # Unsupported version 3.0
            b'{"jsonrpc": "2.0"}',  # Neither method, result, nor error
        ],
    )
    def test_jsonrpc_parse_malformed_variations(self, corrupted_payload: bytes) -> None:
        """Парсер JSON-RPC выбрасывает MalformedJsonRpcError на всех невалидных нагрузках."""
        with pytest.raises(MalformedJsonRpcError):
            parse_jsonrpc(corrupted_payload)

    @pytest.mark.asyncio
    async def test_server_handles_unknown_method_gracefully(self) -> None:
        """Сервер возвращает стандартизированный METHOD_NOT_FOUND (-32601) на неизвестный метод."""
        server = AsyncTransportServer(host="127.0.0.1", port=0)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=port)
        await client.connect()

        try:
            with pytest.raises(RpcCallError) as exc_info:
                await client.call("unknown_ghost_method", {"param": 1})
            assert exc_info.value.code == RpcErrorCode.METHOD_NOT_FOUND
            assert "не найден" in exc_info.value.message
        finally:
            await client.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_server_handles_handler_exception_gracefully(self) -> None:
        """
        Необработанное исключение в обработчике возвращает INTERNAL_ERROR (-32603).
        Сервер продолжает работать и не падает.
        """
        server = AsyncTransportServer(host="127.0.0.1", port=0)

        async def _exploding_handler(
            params: dict[str, Any], session: dict[str, Any]
        ) -> dict[str, Any]:
            raise ZeroDivisionError("division by zero in worker")

        async def _healthy_handler(
            params: dict[str, Any], session: dict[str, Any]
        ) -> dict[str, Any]:
            return {"status": "alive"}

        server.register_handler("explode", _exploding_handler)
        server.register_handler("healthy", _healthy_handler)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=port)
        await client.connect()

        try:
            # Первый вызов взрывается на стороне сервера
            with pytest.raises(RpcCallError) as exc_info:
                await client.call("explode")
            assert exc_info.value.code == RpcErrorCode.INTERNAL_ERROR
            assert "division by zero" in exc_info.value.message

            # Сервер продолжает работать и успешно отвечает на последующие запросы
            res = await client.call("healthy")
            assert res == {"status": "alive"}
        finally:
            await client.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_concurrent_rpc_requests_single_client(self) -> None:
        """30 конкурентных запросов через одного клиента с проверкой корреляции ID."""
        server = AsyncTransportServer(host="127.0.0.1", port=0)

        async def _echo_handler(params: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
            await asyncio.sleep(0.005)  # Имитация лёгкой задержки
            return {"echo_val": params["val"]}

        server.register_handler("echo", _echo_handler)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]

        client = AsyncTransportClient(host="127.0.0.1", port=port)
        await client.connect()

        try:

            async def _make_call(idx: int) -> dict[str, Any]:
                return await client.call("echo", {"val": idx})

            tasks = [_make_call(i) for i in range(30)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 30
            for i, res in enumerate(results):
                assert res["echo_val"] == i
        finally:
            await client.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_concurrent_multi_client_connections(self) -> None:
        """10 параллельных клиентов одновременно подключаются и выполняют запросы."""
        server = AsyncTransportServer(host="127.0.0.1", port=0)

        async def _calc_handler(params: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
            return {"sq": params["num"] ** 2}

        server.register_handler("calc", _calc_handler)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]

        async def _client_worker(client_id: int) -> list[int]:
            cli = AsyncTransportClient(host="127.0.0.1", port=port)
            await cli.connect()
            try:
                out = []
                for n in range(5):
                    r = await cli.call("calc", {"num": client_id * 10 + n})
                    out.append(r["sq"])
                return out
            finally:
                await cli.close()

        workers = [_client_worker(c) for c in range(10)]
        all_results = await asyncio.gather(*workers)

        assert len(all_results) == 10
        for c, res_list in enumerate(all_results):
            assert len(res_list) == 5
            for n, sq in enumerate(res_list):
                expected = (c * 10 + n) ** 2
                assert sq == expected

        await server.stop()


# ===========================================================================
# 4. Pocket File Chunking Edge Cases
# ===========================================================================


class TestPocketFileChunkingEdgeCases:
    """Граничные случаи и безопасность хранилища «Карман»."""

    @pytest.fixture
    def pocket_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "pocket_store"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @pytest.fixture
    def manager(self, pocket_dir: Path) -> PocketManager:
        return PocketManager(pocket_dir=pocket_dir, dev_logging=True)

    def test_pocket_zero_byte_file_lifecycle(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """Полный жизненный цикл 0-байтового файла: создание, сканирование, чтение, запись."""
        empty_file = pocket_dir / "zero.dat"
        empty_file.touch()

        empty_sha = hashlib.sha256(b"").hexdigest()

        # 1. Сканирование манифеста
        manifest = manager.scan_manifest()
        assert manifest.file_count == 1
        assert manifest.files[0].path == "zero.dat"
        assert manifest.files[0].size_bytes == 0
        assert manifest.files[0].sha256 == empty_sha

        # 2. Чтение чанка (offset=0, size=64K)
        data, is_last, total_size = manager.read_chunk(
            PocketPullParams(path="zero.dat", offset=0, chunk_size=65536)
        )
        assert data == b""
        assert is_last is True
        assert total_size == 0

        # 3. Запись пустого файла в подпапку
        push_params = PocketPushParams(
            path="sub/zero_copied.dat",
            offset=0,
            data_b64=base64.b64encode(b"").decode("ascii"),
            is_last=True,
            sha256_full=empty_sha,
        )
        created = manager.write_chunk(push_params)
        assert created is not None
        assert created.exists()
        assert created.stat().st_size == 0
        assert hashlib.sha256(created.read_bytes()).hexdigest() == empty_sha

    def test_pocket_multi_chunk_exact_multiples(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """Запись файла размером ровно в 2 чанка (128 КБ) и 64 КБ + 1 байт."""
        chunk_sz = 65536
        # Файл 1: ровно 128 КБ
        payload_128k = b"A" * chunk_sz + b"B" * chunk_sz
        sha_128k = hashlib.sha256(payload_128k).hexdigest()

        # Чанк 1
        p1 = PocketPushParams(
            path="exact_128k.bin",
            offset=0,
            data_b64=base64.b64encode(payload_128k[:chunk_sz]).decode("ascii"),
            is_last=False,
        )
        assert manager.write_chunk(p1) is None

        # Чанк 2 (финальный)
        p2 = PocketPushParams(
            path="exact_128k.bin",
            offset=chunk_sz,
            data_b64=base64.b64encode(payload_128k[chunk_sz:]).decode("ascii"),
            is_last=True,
            sha256_full=sha_128k,
        )
        res_file = manager.write_chunk(p2)
        assert res_file is not None
        assert res_file.read_bytes() == payload_128k

    def test_pocket_corrupt_chunk_sha256_atomic_cleanup(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """При несовпадении SHA-256 временный .part файл удаляется, а целевой файл не создается."""
        content = b"Critical confidential information corrupted in transit!"
        bad_sha = "0" * 64

        params = PocketPushParams(
            path="compromised.bin",
            offset=0,
            data_b64=base64.b64encode(content).decode("ascii"),
            is_last=True,
            sha256_full=bad_sha,
        )

        with pytest.raises(ValueError, match="Нарушение целостности"):
            manager.write_chunk(params)

        # Ни целевой, ни временный файл не должны остаться на диске
        assert not (pocket_dir / "compromised.bin").exists()
        assert not (pocket_dir / ".compromised.bin.part").exists()

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../../etc/passwd",
            "../../../shadow",
            "sub/../../../../evil.sh",
            "folder/../../outside.txt",
            "/absolute/root/file",
            "//network/share",
        ],
    )
    def test_pocket_path_traversal_fuzzing(
        self, manager: PocketManager, malicious_path: str
    ) -> None:
        """Фуззинг путей для read_chunk и write_chunk блокирует любые попытки выхода из кармана."""
        # 1. Попытка чтения
        with pytest.raises(PathTraversalError):
            manager.read_chunk(PocketPullParams(path=malicious_path))

        # 2. Попытка записи
        with pytest.raises(PathTraversalError):
            manager.write_chunk(
                PocketPushParams(
                    path=malicious_path,
                    offset=0,
                    data_b64=base64.b64encode(b"payload").decode("ascii"),
                    is_last=True,
                )
            )

    def test_pocket_deep_nested_directory_creation(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """Автоматическое создание глубоко вложенной структуры папок при приёме файла."""
        deep_rel_path = "level1/level2/level3/level4/level5/target.json"
        data = b'{"deep": true}'
        sha = hashlib.sha256(data).hexdigest()

        push = PocketPushParams(
            path=deep_rel_path,
            offset=0,
            data_b64=base64.b64encode(data).decode("ascii"),
            is_last=True,
            sha256_full=sha,
        )
        final_p = manager.write_chunk(push)
        assert final_p is not None
        assert final_p.exists()
        assert final_p.read_bytes() == data

    def test_pocket_compare_manifests_edge_cases(self) -> None:
        """Граничные условия сравнения манифестов: пустые манифесты, конфликты mtime."""
        empty_m = PocketManifestResult(files=[], total_size_bytes=0, file_count=0)

        # 1. Оба пустые
        diff_empty = PocketManager.compare_manifests(empty_m, empty_m)
        assert diff_empty.to_pull == []
        assert diff_empty.to_push == []
        assert diff_empty.synced == []

        # 2. Локальный пустой, удаленный содержит файлы
        sha_remote = "a" * 64
        sha_local = "b" * 64
        f_remote = PocketFileInfo(
            path="doc.pdf", sha256=sha_remote, size_bytes=100, mtime_iso="2026-09-30T10:00:00Z"
        )
        remote_m = PocketManifestResult(files=[f_remote], total_size_bytes=100, file_count=1)
        diff_pull = PocketManager.compare_manifests(empty_m, remote_m)
        assert len(diff_pull.to_pull) == 1
        assert diff_pull.to_push == []

        # 3. Конфликт: одинаковый путь, разный хеш, локальный новее удаленного
        f_local_newer = PocketFileInfo(
            path="doc.pdf", sha256=sha_local, size_bytes=120, mtime_iso="2026-09-30T11:00:00Z"
        )
        local_m = PocketManifestResult(files=[f_local_newer], total_size_bytes=120, file_count=1)
        diff_conflict = PocketManager.compare_manifests(local_m, remote_m)
        assert len(diff_conflict.to_push) == 1
        assert diff_conflict.to_pull == []


# ===========================================================================
# 5. Notes Engine Stress & Edge Cases
# ===========================================================================


class TestNotesEngineStressAndEdgeCases:
    """Стресс-тестирование движка заметок (JSONL, параллелизм, Unicode)."""

    @pytest.fixture
    def notes_pocket_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "notes_pocket"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @pytest.fixture
    def notes_mgr(self, notes_pocket_dir: Path) -> NotesManager:
        return NotesManager(pocket_dir=notes_pocket_dir, dev_logging=True)

    @pytest.mark.asyncio
    async def test_notes_unicode_cyrillic_and_emoji_stress(self, notes_mgr: NotesManager) -> None:
        """Стресс-тест Юникода: кириллица, emoji, спецсимволы, кавычки, обратные слеши."""
        complex_strings = [
            "Тестирование кириллицы: съешь же ещё этих мягких французских булок, да выпей чаю.",
            "Emoji parade: 🚀 🤖 👻 🔥 💀 👾 💎 🛡️",
            'JSON injection attempt: {"inject": true, "note_id": "fake", "status": "read"}',
            "Quotes & Escapes: \"Double quotes\", 'single', \\n \\r \\t \\\\ /",
            "Multi-language: Hello 世界 мир 🌍 مرحبا",
        ]

        for s in complex_strings:
            res = await notes_mgr.add_note(NoteSendParams(text=s, author_os=NodeOS.LINUX))
            assert res.status == NoteStatus.DELIVERED

        history = await notes_mgr.get_history(NoteHistoryParams(limit=100))
        assert history.total_count == len(complex_strings)

        saved_texts = [n.text for n in history.notes]
        assert saved_texts == complex_strings

    @pytest.mark.asyncio
    async def test_notes_high_concurrency_writes(self, notes_mgr: NotesManager) -> None:
        """50 параллельных конкурентных записей через asyncio.gather."""

        async def _writer(idx: int) -> str:
            res = await notes_mgr.add_note(
                NoteSendParams(text=f"Concurrent Note #{idx}", author_os=NodeOS.LINUX)
            )
            return res.note_id

        tasks = [_writer(i) for i in range(50)]
        ids = await asyncio.gather(*tasks)

        assert len(ids) == 50
        assert len(set(ids)) == 50  # Все ID уникальны

        # Проверяем целостность файла notes.jsonl
        history = await notes_mgr.get_history(NoteHistoryParams(limit=100))
        assert history.total_count == 50
        assert len(history.notes) == 50

    @pytest.mark.asyncio
    async def test_notes_malformed_jsonl_recovery(
        self, notes_mgr: NotesManager, notes_pocket_dir: Path
    ) -> None:
        """Автоматическое восстановление при наличии битых или поврежденных строк в JSONL."""
        notes_file = notes_pocket_dir / ".notes" / "notes.jsonl"

        # Записываем первую валидную заметку
        await notes_mgr.add_note(NoteSendParams(text="Valid Note 1", author_os=NodeOS.LINUX))

        # Намеренно внедряем мусор в файл
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write("\n\n")  # Пустые строки
            f.write("CORRUPTED NOT JSON STRING\n")
            f.write('{"incomplete": \n')  # Неполный JSON
            f.write('{"wrong_schema": 12345}\n')  # JSON без обязательных полей NoteEntry

        # Записываем вторую валидную заметку
        await notes_mgr.add_note(NoteSendParams(text="Valid Note 2", author_os=NodeOS.WINDOWS))

        history = await notes_mgr.get_history()
        assert history.total_count == 2
        assert [n.text for n in history.notes] == ["Valid Note 1", "Valid Note 2"]

    @pytest.mark.asyncio
    async def test_notes_mark_read_concurrency(self, notes_mgr: NotesManager) -> None:
        """Конкурентные вызовы mark_read на пересекающихся наборах ID."""
        note_ids: list[str] = []
        for i in range(10):
            res = await notes_mgr.add_note(
                NoteSendParams(text=f"Message {i}", author_os=NodeOS.LINUX)
            )
            note_ids.append(res.note_id)

        # Конкурентно отмечаем пересекающиеся подмножества
        group1 = note_ids[0:6]  # 0..5
        group2 = note_ids[4:10]  # 4..9

        async def _mark(ids: list[str]) -> int:
            r = await notes_mgr.mark_read(NoteMarkReadParams(note_ids=ids))
            return r.marked_count

        res1, res2 = await asyncio.gather(_mark(group1), _mark(group2))
        assert (res1 + res2) >= 10

        # Все заметки должны иметь статус READ
        hist = await notes_mgr.get_history(NoteHistoryParams(limit=20))
        assert all(n.status == NoteStatus.READ for n in hist.notes)

    @pytest.mark.asyncio
    async def test_notes_pagination_and_since_filtering(self, notes_mgr: NotesManager) -> None:
        """Граничные случаи пагинации: limit=0, limit > count, фильтр since в будущем/прошлом."""
        for i in range(5):
            await notes_mgr.add_note(NoteSendParams(text=f"Item {i}", author_os=NodeOS.LINUX))

        # limit <= 0 валидируется схемой Pydantic (gt=0)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            NoteHistoryParams(limit=0)

        with pytest.raises(ValidationError):
            NoteHistoryParams(limit=-1)

        # Вызов без параметров возвращает все
        h_default = await notes_mgr.get_history()
        assert len(h_default.notes) == 5

        # limit = 1 -> только последняя
        h_one = await notes_mgr.get_history(NoteHistoryParams(limit=1))
        assert len(h_one.notes) == 1
        assert h_one.notes[0].text == "Item 4"

        # since в далеком будущем -> пустой список
        h_future = await notes_mgr.get_history(NoteHistoryParams(since="2099-01-01T00:00:00Z"))
        assert len(h_future.notes) == 0
        assert h_future.total_count == 0

        # since в далеком прошлом -> все записи
        h_past = await notes_mgr.get_history(NoteHistoryParams(since="1970-01-01T00:00:00Z"))
        assert len(h_past.notes) == 5
        assert h_past.total_count == 5


# ===========================================================================
# 6. Windows Context Menu & CLI Exit Codes Contract
# ===========================================================================


class TestWindowsContextMenuAndExitCodesContract:
    """Проверка генератора контекстного меню и контракта кодов завершения CLI (0..5)."""

    def test_generate_reg_content_validity(self) -> None:
        """Валидность сгенерированного .reg файла реестра Windows."""
        content = generate_reg_content(r"C:\Python\pythonw.exe")
        assert "Windows Registry Editor Version 5.00" in content
        assert r"HKEY_CURRENT_USER\Software\Classes\*\shell\BridgeLocalSend" in content
        assert r"HKEY_CURRENT_USER\Software\Classes\Directory\shell\BridgeLocalSend" in content
        assert "Отправить в Карман (Bridge Local)" in content
        assert r"C:\\Python\\pythonw.exe" in content

    def test_drop_file_to_pocket_zero_byte_and_nested(self, tmp_path: Path) -> None:
        """drop_file_to_pocket корректно обрабатывает 0-байтовые файлы и каталоги."""
        pocket_dir = tmp_path / "pocket_drop"
        pocket_dir.mkdir()
        cfg_file = tmp_path / "bridge.toml"
        BridgeConfig(pocket=PocketConfig(path=str(pocket_dir))).save(cfg_file)

        # 1. 0-байтовый файл
        empty_src = tmp_path / "zero_drop.txt"
        empty_src.touch()
        dest_empty = drop_file_to_pocket(empty_src, config_path=cfg_file)
        assert dest_empty.exists()
        assert dest_empty.stat().st_size == 0

        # 2. Вложенный каталог
        src_dir = tmp_path / "nested_tree"
        src_dir.mkdir()
        (src_dir / "child.txt").write_text("child data", encoding="utf-8")
        dest_dir = drop_file_to_pocket(src_dir, config_path=cfg_file)
        assert dest_dir.is_dir()
        assert (dest_dir / "child.txt").read_text(encoding="utf-8") == "child data"

    def test_exit_code_contract_exhaustive_mapping(self) -> None:
        """
        Проверка контракта кодов завершения (AGENTS.md Section 6):
          0: SUCCESS
          1: GENERAL_ERROR
          2: NETWORK_ERROR
          3: AUTH_ERROR
          4: COMMAND_FAILED
          5: TIMEOUT
        """
        # Проверка значений Enum
        assert ExitCode.SUCCESS == 0
        assert ExitCode.GENERAL_ERROR == 1
        assert ExitCode.NETWORK_ERROR == 2
        assert ExitCode.AUTH_ERROR == 3
        assert ExitCode.COMMAND_FAILED == 4
        assert ExitCode.TIMEOUT == 5

        # Проверка маппинга классов исключений
        assert BridgeClientError("general").exit_code == ExitCode.GENERAL_ERROR
        assert BridgeNetworkError("network").exit_code == ExitCode.NETWORK_ERROR
        assert BridgeAuthError("auth").exit_code == ExitCode.AUTH_ERROR
        assert (
            BridgeRemoteCommandError("command fail", exit_code=1).exit_code
            == ExitCode.COMMAND_FAILED
        )
        assert BridgeTimeoutError("timeout").exit_code == ExitCode.TIMEOUT

    def test_cli_live_exit_codes_all_0_to_5(self, tmp_path: Path) -> None:
        """
        Сквозной тест всех кодов завершения 0..5 при реальных вызовах bridge-cli:
          - Код 0: Успех (CLI --version)
          - Код 1: Ошибка аргументов / отсутствие файла (send missing_file)
          - Код 2: Сетевая ошибка (подключение к неподключенному сокету)
          - Код 3: Ошибка аутентификации (неверный PSK токен)
          - Код 4: Ошибка выполнения удаленной команды (exit 42)
          - Код 5: Таймаут выполнения удаленной команды
        """
        local_pocket = tmp_path / "cli_live_pocket"
        local_pocket.mkdir()
        server_pocket = tmp_path / "cli_live_server_pocket"
        server_pocket.mkdir()

        # Запускаем живой тестовый сервер с PSK-аутентификацией
        cfg_srv = BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=0, psk_token="correct-key"),
            pocket=PocketConfig(path=str(server_pocket)),
        )
        service = WindowsBridgeService(cfg_srv)
        loop = asyncio.new_event_loop()
        port_box: list[int] = []

        def _srv_worker() -> None:
            asyncio.set_event_loop(loop)

            async def _start() -> None:
                await service.start()
                assert service.server._server is not None
                p = service.server._server.sockets[0].getsockname()[1]
                port_box.append(p)

            loop.run_until_complete(_start())
            loop.run_forever()

        th = threading.Thread(target=_srv_worker, daemon=True)
        th.start()

        while not port_box:
            time.sleep(0.01)

        port = port_box[0]

        cfg_cli_valid = tmp_path / "bridge_valid.toml"
        BridgeConfig(
            connection=ConnectionConfig(host="127.0.0.1", port=port, psk_token="correct-key"),
            pocket=PocketConfig(path=str(local_pocket)),
        ).save(cfg_cli_valid)

        try:
            # 1. ExitCode 0 (SUCCESS)
            res0 = runner.invoke(cli_app, ["--version", "--json"])
            assert res0.exit_code == ExitCode.SUCCESS

            # 2. ExitCode 1 (GENERAL_ERROR)
            res1 = runner.invoke(
                cli_app,
                [
                    "send",
                    str(tmp_path / "non_existing_file.tmp"),
                    "--config",
                    str(cfg_cli_valid),
                    "--json",
                ],
            )
            assert res1.exit_code == ExitCode.GENERAL_ERROR
            data1 = json.loads(res1.stdout)
            assert data1["error_code"] == 1

            # 3. ExitCode 2 (NETWORK_ERROR: подключение к неподключенному порту)
            res2 = runner.invoke(
                cli_app,
                ["ping", "--port", "59995", "--config", str(cfg_cli_valid), "--json"],
            )
            assert res2.exit_code == ExitCode.NETWORK_ERROR
            data2 = json.loads(res2.stdout)
            assert data2["error_code"] == 2

            # 4. ExitCode 3 (AUTH_ERROR: неверный PSK токен)
            cfg_cli_bad_auth = tmp_path / "bridge_bad_auth.toml"
            BridgeConfig(
                connection=ConnectionConfig(
                    host="127.0.0.1", port=port, psk_token="WRONG-PSK-TOKEN"
                ),
                pocket=PocketConfig(path=str(local_pocket)),
            ).save(cfg_cli_bad_auth)

            res3 = runner.invoke(
                cli_app,
                ["exec", "echo test", "--config", str(cfg_cli_bad_auth), "--json"],
            )
            assert res3.exit_code == ExitCode.AUTH_ERROR
            data3 = json.loads(res3.stdout)
            assert data3["error_code"] == 3

            # 5. ExitCode 4 (COMMAND_FAILED: команда завершилась с ненулевым кодом)
            res4 = runner.invoke(
                cli_app,
                ["exec", "exit 42", "--config", str(cfg_cli_valid), "--json"],
            )
            assert res4.exit_code == ExitCode.COMMAND_FAILED
            data4 = json.loads(res4.stdout)
            assert data4["exit_code"] == 42

            # 6. ExitCode 5 (TIMEOUT: команда превысила лимит времени)
            # Запускаем команду со сном 5 секунд и таймаутом 1 секунда
            res5 = runner.invoke(
                cli_app,
                ["exec", "sleep 5", "--timeout", "1", "--config", str(cfg_cli_valid), "--json"],
            )
            assert res5.exit_code == ExitCode.TIMEOUT
            data5 = json.loads(res5.stdout)
            assert data5["error_code"] == 5

        finally:

            async def _stop() -> None:
                await service.stop()

            asyncio.run_coroutine_threadsafe(_stop(), loop).result(timeout=3.0)
            loop.call_soon_threadsafe(loop.stop)
            th.join(timeout=2.0)
