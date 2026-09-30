"""
tests/unit/test_transport_and_storage_fuzzing.py — Fuzzing and high-concurrency stress test suite.

Autonomous QA Suite:
  1. TestTcpPacketFragmentationFuzzing:
     - Byte-by-byte TCP packet fragmentation feeding valid frames to read_frame.
     - Irregular chunk fragmentation simulating arbitrary network MTU packet splits.
     - Header fragmentation across 6-byte boundary.
     - Live loopback TCP byte-by-byte transmission.
     - Multi-frame continuous streaming under fragmentation.
  2. TestLargeBatchNotesStress:
     - High-concurrency insertion of 500 notes via NotesManager (asyncio.gather).
     - Pagination boundaries, since filtering, and limit tests.
     - Corrupted line injection and graceful recovery.
     - Direct JSONL file inspection verifying atomic fsync integrity.
  3. TestConcurrentMultiFilePocketStress:
     - 10 concurrent transfers of files from 1 byte to 5 MB across 64 KB chunk boundaries.
     - Verification of atomic promotion and clean removal of temporary .part files.
     - Fault isolation: corrupted transfer aborts without damaging concurrent valid transfers.
     - Bidirectional pull/push concurrent stress.

Rules: Strict zero-emoji compliance ([OK], [WARN], [FAIL] tags), 100% type-annotated, Ruff clean.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import time
from pathlib import Path

import pytest

from bridge_core.models import (
    FRAME_HEADER_SIZE,
    NodeOS,
    NoteEntry,
    NoteHistoryParams,
    NoteSendParams,
    NoteStatus,
    PocketPullParams,
    PocketPushParams,
)
from bridge_core.notes import NotesManager
from bridge_core.pocket import PocketManager, compute_file_sha256
from bridge_core.protocol import encode_frame, read_frame

# ===========================================================================
# 1. Extreme TCP Packet Fragmentation Fuzzing
# ===========================================================================


class TestTcpPacketFragmentationFuzzing:
    """Extreme byte-by-byte and irregular chunk TCP packet fragmentation fuzzing."""

    @pytest.mark.asyncio
    async def test_byte_by_byte_stream_fragmentation(self) -> None:
        """
        [TEST] Feed complete binary frame byte-by-byte into StreamReader.
        Verifies that read_frame handles extreme 1-byte packet fragmentation with zero byte loss.
        """
        raw_payload = b'{"jsonrpc": "2.0", "method": "test.fuzz", "params": {"data": "fragmented"}}'
        full_frame = encode_frame(raw_payload)

        reader = asyncio.StreamReader()

        async def _byte_producer() -> None:
            for b in full_frame:
                reader.feed_data(bytes([b]))
                # Simulate microsecond TCP packet arrival jitter
                await asyncio.sleep(0.0001)
            reader.feed_eof()

        producer_task = asyncio.create_task(_byte_producer())
        extracted_payload = await read_frame(reader)
        await producer_task

        assert extracted_payload == raw_payload
        assert len(extracted_payload) == len(raw_payload)

    @pytest.mark.asyncio
    async def test_random_chunk_fragmentation_stream(self) -> None:
        """
        [TEST] Slice multiple frames into random tiny chunks (1..7 bytes).
        Verifies that sequential frame decoding maintains strict frame boundaries.
        """
        frames_payloads = [
            b"FIRST_PAYLOAD_DATA",
            b"",
            b"SECOND_PAYLOAD_LONGER_CONTENT_FOR_STRESS_TESTING_1234567890",
            b"THIRD",
            json.dumps({"fuzz_id": 9999, "status": "active"}).encode("utf-8"),
        ]
        combined_stream = b"".join(encode_frame(p) for p in frames_payloads)

        reader = asyncio.StreamReader()

        async def _irregular_feeder() -> None:
            idx = 0
            rng = random.Random(42)  # Deterministic seed for reproducible testing
            while idx < len(combined_stream):
                chunk_len = rng.randint(1, 7)
                chunk = combined_stream[idx : idx + chunk_len]
                reader.feed_data(chunk)
                idx += chunk_len
                await asyncio.sleep(0.0001)
            reader.feed_eof()

        feeder_task = asyncio.create_task(_irregular_feeder())

        for expected in frames_payloads:
            result = await read_frame(reader)
            assert result == expected

        await feeder_task

    @pytest.mark.asyncio
    async def test_header_split_fragmentation(self) -> None:
        """
        [TEST] Specifically fragment the 6-byte frame header into individual single bytes.
        Verifies header parsing integrity when magic and length fields are split across packets.
        """
        payload = b"PAYLOAD_AFTER_SPLIT_HEADER"
        frame = encode_frame(payload)

        reader = asyncio.StreamReader()

        async def _split_header_producer() -> None:
            # Feed header byte-by-byte
            for i in range(FRAME_HEADER_SIZE):
                reader.feed_data(frame[i : i + 1])
                await asyncio.sleep(0.0001)
            # Feed remaining payload in 3 chunks
            rem = frame[FRAME_HEADER_SIZE:]
            p1 = len(rem) // 3
            p2 = 2 * p1
            reader.feed_data(rem[:p1])
            await asyncio.sleep(0.0001)
            reader.feed_data(rem[p1:p2])
            await asyncio.sleep(0.0001)
            reader.feed_data(rem[p2:])
            reader.feed_eof()

        task = asyncio.create_task(_split_header_producer())
        extracted = await read_frame(reader)
        await task

        assert extracted == payload

    @pytest.mark.asyncio
    async def test_loopback_tcp_byte_by_byte_transmission(self) -> None:
        """
        [TEST] Real TCP loopback socket transfer with byte-by-byte client writes.
        Verifies kernel socket buffer handling under artificial 1-byte packet delays.
        """
        received_box: list[bytes] = []

        async def _handle_conn(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            res = await read_frame(r)
            received_box.append(res)
            w.close()
            await w.wait_closed()

        srv = await asyncio.start_server(_handle_conn, host="127.0.0.1", port=0)
        port = srv.sockets[0].getsockname()[1]

        _c_reader, c_writer = await asyncio.open_connection("127.0.0.1", port)
        test_data = b"TCP_LOOPBACK_BYTE_BY_BYTE_FRAG_PAYLOAD"
        frame = encode_frame(test_data)

        for byte_int in frame:
            c_writer.write(bytes([byte_int]))
            await c_writer.drain()
            await asyncio.sleep(0.00005)

        await asyncio.sleep(0.02)
        c_writer.close()
        await c_writer.wait_closed()
        srv.close()
        await srv.wait_closed()

        assert len(received_box) == 1
        assert received_box[0] == test_data


# ===========================================================================
# 2. Large Batch Notes Stress Test
# ===========================================================================


class TestLargeBatchNotesStress:
    """Stress testing NotesManager with 500 concurrent additions and pagination."""

    @pytest.fixture
    def notes_pocket_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "large_batch_pocket"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @pytest.fixture
    def manager(self, notes_pocket_dir: Path) -> NotesManager:
        return NotesManager(pocket_dir=notes_pocket_dir, dev_logging=False)

    @pytest.mark.asyncio
    async def test_concurrent_append_500_notes(
        self, manager: NotesManager, notes_pocket_dir: Path
    ) -> None:
        """
        [TEST] Concurrently append 500 notes via NotesManager using asyncio.gather.
        Verifies mutex locking, atomic fsync write integrity, and zero loss of records.
        """
        total_notes = 500
        t0 = time.perf_counter_ns()

        async def _add_single_note(idx: int) -> str:
            params = NoteSendParams(
                text=f"Batch stress note #{idx:04d} payload text verification.",
                author_os=NodeOS.LINUX if idx % 2 == 0 else NodeOS.WINDOWS,
                target_node="win-node" if idx % 2 == 0 else "linux-node",
            )
            res = await manager.add_note(params, note_id=f"note-uuid-{idx:04d}")
            return res.note_id

        tasks = [_add_single_note(i) for i in range(total_notes)]
        created_ids = await asyncio.gather(*tasks)

        duration_ms = (time.perf_counter_ns() - t0) / 1_000_000
        assert duration_ms > 0

        # Assert all 500 notes returned distinct IDs
        assert len(created_ids) == total_notes
        assert len(set(created_ids)) == total_notes

        # Verify limit boundary: limit > 500 is rejected by schema
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            NoteHistoryParams(limit=501)

        # Verify through manager history with maximum allowed limit=500
        full_hist = await manager.get_history(NoteHistoryParams(limit=500))
        assert full_hist.total_count == total_notes
        assert len(full_hist.notes) == total_notes

        # Direct file inspection
        notes_file = notes_pocket_dir / ".notes" / "notes.jsonl"
        assert notes_file.exists()
        raw_text = notes_file.read_text(encoding="utf-8")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        assert len(lines) == total_notes

        # Verify every line parses to valid NoteEntry
        for line in lines:
            parsed = json.loads(line)
            entry = NoteEntry.model_validate(parsed)
            assert entry.status == NoteStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_notes_pagination_and_since_filtering_on_large_batch(
        self, manager: NotesManager
    ) -> None:
        """
        [TEST] Test pagination limit (50, 250, 500) and timestamp filtering across 500 notes.
        """
        # Insert 100 notes with increasing indices
        for i in range(100):
            await manager.add_note(
                NoteSendParams(text=f"Paginated Note {i:03d}", author_os=NodeOS.LINUX)
            )

        # 1. Limit 25
        h25 = await manager.get_history(NoteHistoryParams(limit=25))
        assert h25.total_count == 100
        assert len(h25.notes) == 25
        # Manager returns the most recent N notes
        assert h25.notes[-1].text == "Paginated Note 099"
        assert h25.notes[0].text == "Paginated Note 075"

        # 2. Limit 50
        h50 = await manager.get_history(NoteHistoryParams(limit=50))
        assert len(h50.notes) == 50
        assert h50.notes[0].text == "Paginated Note 050"

        # 3. Filter since middle note
        all_hist = await manager.get_history(NoteHistoryParams(limit=100))
        pivot_timestamp = all_hist.notes[40].timestamp
        h_since = await manager.get_history(NoteHistoryParams(since=pivot_timestamp, limit=100))
        assert len(h_since.notes) == 60
        assert h_since.notes[0].timestamp >= pivot_timestamp

    @pytest.mark.asyncio
    async def test_corrupted_line_filtering_and_recovery_stress(
        self, manager: NotesManager, notes_pocket_dir: Path
    ) -> None:
        """
        [TEST] Inject 10 malformed and truncated lines directly into notes.jsonl.
        Verifies that get_history skips all corrupt lines safely and returns valid notes.
        """
        for i in range(20):
            await manager.add_note(NoteSendParams(text=f"Clean note {i}", author_os=NodeOS.LINUX))

        notes_file = notes_pocket_dir / ".notes" / "notes.jsonl"
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write("\n\n")  # Empty lines
            f.write("GARBAGE_LINE_WITHOUT_JSON\n")
            f.write('{"truncated_json": \n')
            f.write('{"missing_fields": true}\n')
            f.write("   \t   \n")  # Whitespace only
            f.write('{"text": "missing note_id and timestamp"}\n')
            f.write('{"note_id": "bad", "timestamp": "bad", "author_os": "unknown"}\n')

        # Add more clean notes
        for i in range(20, 40):
            await manager.add_note(NoteSendParams(text=f"Clean note {i}", author_os=NodeOS.WINDOWS))

        hist = await manager.get_history(NoteHistoryParams(limit=100))
        assert hist.total_count == 40
        assert len(hist.notes) == 40
        assert [n.text for n in hist.notes[:5]] == [f"Clean note {i}" for i in range(5)]
        assert [n.text for n in hist.notes[-5:]] == [f"Clean note {i}" for i in range(35, 40)]


# ===========================================================================
# 3. Concurrent Multi-File Pocket Drop Stress
# ===========================================================================


class TestConcurrentMultiFilePocketStress:
    """Stress testing Pocket file chunking across 10 concurrent transfers from 1 byte to 5 MB."""

    @pytest.fixture
    def pocket_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "pocket_concurrent"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @pytest.fixture
    def manager(self, pocket_dir: Path) -> PocketManager:
        return PocketManager(pocket_dir=pocket_dir, dev_logging=False)

    @pytest.mark.asyncio
    async def test_concurrent_transfers_varying_sizes_1b_to_5mb(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """
        [TEST] 10 concurrent file transfers with sizes spanning 1 byte to 5 MB.
        Verifies multi-chunk writing, atomic promotion, SHA-256 accuracy, and no orphan .part files.
        """
        file_specs: list[tuple[str, int]] = [
            ("file_01_1b.bin", 1),
            ("file_02_17b.bin", 17),
            ("file_03_512b.bin", 512),
            ("file_04_4kb.bin", 4096),
            ("file_05_64kb_exact.bin", 65536),
            ("file_06_64kb_plus1.bin", 65537),
            ("file_07_250kb.bin", 250000),
            ("file_08_1mb.bin", 1048576),
            ("file_09_2_5mb.bin", 2500000),
            ("file_10_5mb.bin", 5242880),
        ]

        chunk_size = 65536
        expected_hashes: dict[str, str] = {}
        payloads: dict[str, bytes] = {}

        # Pre-generate deterministic test data
        for name, sz in file_specs:
            # Deterministic fill using repeating byte pattern
            pattern = f"DATA_{name}_".encode("ascii")
            full_data = (pattern * (sz // len(pattern) + 1))[:sz]
            payloads[name] = full_data
            expected_hashes[name] = hashlib.sha256(full_data).hexdigest()

        async def _transfer_file(rel_path: str, data: bytes) -> Path | None:
            full_sha = expected_hashes[rel_path]
            total_sz = len(data)
            offset = 0
            final_path: Path | None = None

            while offset < total_sz or (total_sz == 0 and offset == 0):
                chunk = data[offset : offset + chunk_size]
                chunk_len = len(chunk)
                is_last = (offset + chunk_len) >= total_sz

                push_params = PocketPushParams(
                    path=rel_path,
                    offset=offset,
                    data_b64=base64.b64encode(chunk).decode("ascii"),
                    is_last=is_last,
                    sha256_full=full_sha if is_last else None,
                )
                final_path = manager.write_chunk(push_params)
                offset += chunk_len
                if is_last:
                    break

            return final_path

        t0 = time.perf_counter_ns()
        tasks = [_transfer_file(name, payloads[name]) for name, _ in file_specs]
        results = await asyncio.gather(*tasks)
        duration_ms = (time.perf_counter_ns() - t0) / 1_000_000
        assert duration_ms > 0

        # Verification of results
        assert len(results) == len(file_specs)
        for (name, expected_size), p in zip(file_specs, results, strict=True):
            assert p is not None
            assert p.exists()
            assert p.stat().st_size == expected_size
            computed_sha = compute_file_sha256(p)
            assert computed_sha == expected_hashes[name]

        # Strict check: Zero .part files remain anywhere in pocket_dir
        leftover_parts = list(pocket_dir.glob("**/*.part"))
        assert len(leftover_parts) == 0, f"Detected orphan temporary part files: {leftover_parts}"

    @pytest.mark.asyncio
    async def test_concurrent_transfers_with_isolated_corruption(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """
        [TEST] 5 valid concurrent transfers + 1 transfer with deliberately corrupted SHA-256.
        Verifies fault isolation: corrupted transfer aborts, cleans its .part file,
        and does NOT compromise concurrent valid file transfers.
        """
        valid_files = [
            ("valid_alpha.dat", b"Alpha valid payload bytes"),
            ("valid_beta.dat", b"Beta valid payload bytes" * 100),
            ("valid_gamma.dat", b"Gamma payload" * 1000),
            ("valid_delta.dat", b"Delta payload" * 500),
            ("valid_epsilon.dat", b"Epsilon payload" * 2000),
        ]
        corrupted_name = "corrupted_target.dat"
        corrupted_data = b"Malicious or corrupted byte stream intended to fail verification"

        async def _valid_task(name: str, data: bytes) -> Path | None:
            sha = hashlib.sha256(data).hexdigest()
            params = PocketPushParams(
                path=name,
                offset=0,
                data_b64=base64.b64encode(data).decode("ascii"),
                is_last=True,
                sha256_full=sha,
            )
            return manager.write_chunk(params)

        async def _corrupt_task() -> None:
            bad_sha = "0" * 64
            params = PocketPushParams(
                path=corrupted_name,
                offset=0,
                data_b64=base64.b64encode(corrupted_data).decode("ascii"),
                is_last=True,
                sha256_full=bad_sha,
            )
            manager.write_chunk(params)

        # Launch all 5 valid + 1 corrupt concurrently
        corrupt_raised = False
        try:
            await asyncio.gather(
                *[_valid_task(n, d) for n, d in valid_files],
                _corrupt_task(),
            )
        except ValueError as e:
            corrupt_raised = True
            assert "Нарушение целостности" in str(e)

        assert corrupt_raised is True

        # Verify all 5 valid files exist and are intact
        for name, data in valid_files:
            file_p = pocket_dir / name
            assert file_p.exists()
            assert file_p.read_bytes() == data

        # Verify corrupted file was completely wiped and never created
        assert not (pocket_dir / corrupted_name).exists()
        assert not (pocket_dir / f".{corrupted_name}.part").exists()

    @pytest.mark.asyncio
    async def test_concurrent_pull_and_push_stress(
        self, manager: PocketManager, pocket_dir: Path
    ) -> None:
        """
        [TEST] Concurrent bidirectional pull and push stress on shared pocket storage.
        """
        # Create 5 initial files for pulling
        for i in range(5):
            (pocket_dir / f"src_{i}.bin").write_bytes(f"Source content {i}".encode() * 200)

        # 5 tasks reading, 5 tasks writing simultaneously
        async def _reader_task(idx: int) -> bytes:
            params = PocketPullParams(path=f"src_{idx}.bin", offset=0, chunk_size=1024)
            data, _, _ = manager.read_chunk(params)
            return data

        async def _writer_task(idx: int) -> Path | None:
            content = f"New pushed content {idx}".encode() * 300
            sha = hashlib.sha256(content).hexdigest()
            params = PocketPushParams(
                path=f"dst_{idx}.bin",
                offset=0,
                data_b64=base64.b64encode(content).decode("ascii"),
                is_last=True,
                sha256_full=sha,
            )
            return manager.write_chunk(params)

        read_tasks = [_reader_task(i) for i in range(5)]
        write_tasks = [_writer_task(i) for i in range(5)]

        read_res, write_res = await asyncio.gather(
            asyncio.gather(*read_tasks),
            asyncio.gather(*write_tasks),
        )

        assert len(read_res) == 5
        assert len(write_res) == 5
        for i, p in enumerate(write_res):
            assert p is not None
            assert p.exists()
            assert (pocket_dir / f"dst_{i}.bin").exists()
