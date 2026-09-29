"""
tests/unit/test_pocket.py — Модульные тесты для подсистемы «Карман» (Pocket Storage Engine).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from pathlib import Path

import pytest

from bridge_core.models import (
    PocketFileInfo,
    PocketManifestResult,
    PocketPullParams,
    PocketPushParams,
)
from bridge_core.pocket import (
    PocketManager,
    PocketWatcher,
    compute_file_sha256,
)
from bridge_core.security import PathTraversalError


@pytest.fixture
def pocket_dir(tmp_path: Path) -> Path:
    p = tmp_path / "pocket"
    p.mkdir()
    return p


@pytest.fixture
def manager(pocket_dir: Path) -> PocketManager:
    return PocketManager(pocket_dir=pocket_dir, dev_logging=True)


def test_compute_file_sha256(pocket_dir: Path) -> None:
    test_file = pocket_dir / "sample.txt"
    content = b"Hello, Bridge Local Pocket Engine!"
    test_file.write_bytes(content)

    expected_sha = hashlib.sha256(content).hexdigest()
    assert compute_file_sha256(test_file) == expected_sha


def test_scan_manifest_basic(manager: PocketManager, pocket_dir: Path) -> None:
    # Создаём несколько файлов и подпапку
    (pocket_dir / "file1.txt").write_text("file 1 content", encoding="utf-8")
    (pocket_dir / "subfolder").mkdir()
    (pocket_dir / "subfolder" / "file2.bin").write_bytes(b"\x00\x01\x02\x03\x04")

    manifest = manager.scan_manifest()
    assert manifest.file_count == 2
    assert len(manifest.files) == 2

    paths = [f.path for f in manifest.files]
    assert "file1.txt" in paths
    assert "subfolder/file2.bin" in paths

    total_expected = len(b"file 1 content") + 5
    assert manifest.total_size_bytes == total_expected


def test_scan_manifest_ignores_logs_and_hidden(manager: PocketManager, pocket_dir: Path) -> None:
    # Обычный файл
    (pocket_dir / "normal.txt").write_text("normal", encoding="utf-8")

    # Папка logs (должна игнорироваться)
    logs_dir = pocket_dir / "logs"
    logs_dir.mkdir()
    (logs_dir / "2026-09-30.jsonl").write_text('{"event": 1}', encoding="utf-8")

    # Скрытая папка .notes (должна игнорироваться)
    notes_dir = pocket_dir / ".notes"
    notes_dir.mkdir()
    (notes_dir / "notes.jsonl").write_text('{"note": 1}', encoding="utf-8")

    # Скрытый файл и временный .part файл
    (pocket_dir / ".hidden").write_text("secret", encoding="utf-8")
    (pocket_dir / ".upload.part").write_text("temp part", encoding="utf-8")

    manifest = manager.scan_manifest()
    assert manifest.file_count == 1
    assert manifest.files[0].path == "normal.txt"


def test_read_chunk_single_and_multi(manager: PocketManager, pocket_dir: Path) -> None:
    content = b"0123456789" * 100  # 1000 байт
    (pocket_dir / "data.bin").write_bytes(content)

    # 1. Чтение маленьким чанком 400 байт
    data1, is_last1, total1 = manager.read_chunk(
        PocketPullParams(path="data.bin", offset=0, chunk_size=400)
    )
    assert len(data1) == 400
    assert not is_last1
    assert total1 == 1000
    assert data1 == content[:400]

    # 2. Второй чанк
    data2, is_last2, _total2 = manager.read_chunk(
        PocketPullParams(path="data.bin", offset=400, chunk_size=400)
    )
    assert len(data2) == 400
    assert not is_last2
    assert data2 == content[400:800]

    # 3. Финальный чанк
    data3, is_last3, _total3 = manager.read_chunk(
        PocketPullParams(path="data.bin", offset=800, chunk_size=400)
    )
    assert len(data3) == 200
    assert is_last3
    assert data3 == content[800:]


def test_read_chunk_errors(manager: PocketManager) -> None:
    with pytest.raises(FileNotFoundError):
        manager.read_chunk(PocketPullParams(path="nonexistent.txt"))

    with pytest.raises(PathTraversalError):
        manager.read_chunk(PocketPullParams(path="../../etc/passwd"))


def test_write_chunk_single_part(manager: PocketManager, pocket_dir: Path) -> None:
    content = b"Simple single chunk payload"
    sha = hashlib.sha256(content).hexdigest()

    params = PocketPushParams(
        path="simple.txt",
        offset=0,
        data_b64=base64.b64encode(content).decode("ascii"),
        is_last=True,
        sha256_full=sha,
    )

    result_path = manager.write_chunk(params)
    assert result_path is not None
    assert result_path.exists()
    assert result_path.read_bytes() == content

    # Временного .part файла не должно остаться
    part_file = pocket_dir / ".simple.txt.part"
    assert not part_file.exists()


def test_write_chunk_multi_part(manager: PocketManager, pocket_dir: Path) -> None:
    chunk1 = b"Part 1 "
    chunk2 = b"Part 2 "
    chunk3 = b"Part 3 Complete!"
    full_content = chunk1 + chunk2 + chunk3
    full_sha = hashlib.sha256(full_content).hexdigest()

    p1 = PocketPushParams(
        path="sub/multi.txt",
        offset=0,
        data_b64=base64.b64encode(chunk1).decode("ascii"),
        is_last=False,
    )
    assert manager.write_chunk(p1) is None

    p2 = PocketPushParams(
        path="sub/multi.txt",
        offset=len(chunk1),
        data_b64=base64.b64encode(chunk2).decode("ascii"),
        is_last=False,
    )
    assert manager.write_chunk(p2) is None

    p3 = PocketPushParams(
        path="sub/multi.txt",
        offset=len(chunk1) + len(chunk2),
        data_b64=base64.b64encode(chunk3).decode("ascii"),
        is_last=True,
        sha256_full=full_sha,
    )
    final_path = manager.write_chunk(p3)
    assert final_path is not None
    assert final_path.exists()
    assert final_path.read_bytes() == full_content


def test_write_chunk_corrupted_sha256_rejection(manager: PocketManager, pocket_dir: Path) -> None:
    content = b"Valid content"
    wrong_sha = "0000000000000000000000000000000000000000000000000000000000000000"

    params = PocketPushParams(
        path="corrupted.bin",
        offset=0,
        data_b64=base64.b64encode(content).decode("ascii"),
        is_last=True,
        sha256_full=wrong_sha,
    )

    with pytest.raises(ValueError, match="Нарушение целостности"):
        manager.write_chunk(params)

    # Целевой файл не должен быть создан, а временный .part должен быть удалён
    assert not (pocket_dir / "corrupted.bin").exists()
    assert not (pocket_dir / ".corrupted.bin.part").exists()


def test_write_chunk_path_traversal(manager: PocketManager) -> None:
    params = PocketPushParams(
        path="../outside.txt",
        offset=0,
        data_b64=base64.b64encode(b"danger").decode("ascii"),
        is_last=True,
    )
    with pytest.raises(PathTraversalError):
        manager.write_chunk(params)


def test_compare_manifests() -> None:
    sha_a = "a" * 64
    sha_b = "b" * 64
    sha_c = "c" * 64

    # Локальный манифест
    f_synced = PocketFileInfo(
        path="common.txt", sha256=sha_a, size_bytes=10, mtime_iso="2026-09-30T00:00:00Z"
    )
    f_local_only = PocketFileInfo(
        path="local.txt", sha256=sha_b, size_bytes=20, mtime_iso="2026-09-30T00:00:00Z"
    )
    f_local_older = PocketFileInfo(
        path="conflict.txt", sha256=sha_b, size_bytes=30, mtime_iso="2026-09-30T00:00:00Z"
    )

    # Удалённый манифест
    f_remote_only = PocketFileInfo(
        path="remote.txt", sha256=sha_c, size_bytes=40, mtime_iso="2026-09-30T00:00:00Z"
    )
    f_remote_newer = PocketFileInfo(
        path="conflict.txt", sha256=sha_c, size_bytes=35, mtime_iso="2026-09-30T01:00:00Z"
    )

    local_manifest = PocketManifestResult(
        files=[f_synced, f_local_only, f_local_older],
        total_size_bytes=60,
        file_count=3,
    )
    remote_manifest = PocketManifestResult(
        files=[f_synced, f_remote_only, f_remote_newer],
        total_size_bytes=85,
        file_count=3,
    )

    diff = PocketManager.compare_manifests(local=local_manifest, remote=remote_manifest)

    # common.txt совпадает
    assert diff.synced == ["common.txt"]

    # remote.txt нужно скачать, и conflict.txt тоже нужно скачать так как remote_newer свежее
    pull_paths = [f.path for f in diff.to_pull]
    assert "remote.txt" in pull_paths
    assert "conflict.txt" in pull_paths

    # local.txt нужно отправить
    push_paths = [f.path for f in diff.to_push]
    assert "local.txt" in push_paths


@pytest.mark.asyncio
async def test_pocket_watcher_debounced(pocket_dir: Path) -> None:
    events: list[list[str]] = []

    def on_change(paths: list[str]) -> None:
        events.append(paths)

    watcher = PocketWatcher(pocket_dir=pocket_dir, on_change_callback=on_change, debounce_sec=0.1)
    watcher.start()

    try:
        # Создаём несколько файлов быстро подряд
        (pocket_dir / "watch1.txt").write_text("1")
        (pocket_dir / "watch2.txt").write_text("2")

        # Ждём завершения дебаунса
        await asyncio.sleep(0.3)

        # Должен быть вызван коллбэк
        assert len(events) >= 1
    finally:
        watcher.stop()
