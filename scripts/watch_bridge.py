"""
scripts/watch_bridge.py — Двусторонний межмашинный монитор событий Bridge Local.

Обеспечивает гарантированное пробуждение (wake-up signal / «пинок») для автономных
агентов Antigravity на Linux и Windows:

1. Режим Агента (Windows / --role agent):
   - Отслеживает локальный каталог pocket (вычисленный канонически через BridgeConfig).
   - Мониторит pocket/.notes/notes.jsonl на предмет входящих заметок от Linux.
   - Мониторит появление и изменение файлов в pocket/ и pocket/agent_bus/.
   - Завершается с кодом 0 и выводит структурированный JSON при первом событии,
     что мгновенно пробуждает спящего агента Windows.

2. Режим Клиента (Linux / --role client):
   - Периодически опрашивает удалённый узел Windows через легкие RPC.
   - При обнаружении нового удалённого файла автоматически выполняет pocket_sync.
   - При обнаружении новой заметки или файла выводит JSON и завершается с кодом 0,
     мгновенно пробуждая спящего агента Linux.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Автоматическое добавление каталога src в sys.path
_repo_root = Path(__file__).resolve().parent.parent
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Принудительная настройка UTF-8 вывода
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bridge_core.config import BridgeConfig  # noqa: E402

IGNORED_DIRS = {".notes", "logs", ".git", "__pycache__"}
IGNORED_SUFFIXES = {".part", ".tmp", ".swp"}


def read_all_notes(notes_file: Path) -> list[dict[str, Any]]:
    """Считывает все корректные JSON-записи из notes.jsonl."""
    if not notes_file.exists():
        return []
    notes: list[dict[str, Any]] = []
    try:
        with open(notes_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                with contextlib.suppress(Exception):
                    notes.append(json.loads(stripped))
    except Exception:
        pass
    return notes


def get_pocket_files(pocket_dir: Path) -> dict[str, tuple[int, float]]:
    """Возвращает отображение relative_path -> (size, mtime) для пользовательских файлов."""
    files: dict[str, tuple[int, float]] = {}
    if not pocket_dir.exists():
        return files

    for root, dirs, filenames in os.walk(pocket_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") or any(fn.endswith(sfx) for sfx in IGNORED_SUFFIXES):
                continue
            full_p = Path(root) / fn
            rel_p = str(full_p.relative_to(pocket_dir)).replace("\\", "/")
            try:
                st = full_p.stat()
                files[rel_p] = (st.st_size, st.st_mtime)
            except OSError:
                pass
    return files


def read_preview(file_path: Path, max_chars: int = 1000) -> str:
    """Безопасное чтение превью текстового файла."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    except Exception:
        return "<binary or unreadable>"


def run_agent_watcher(
    pocket_dir: Path,
    timeout: int = 300,
    poll_interval: float = 0.5,
    ignore_author: str = "windows",
    continuous: bool = False,
) -> None:
    """Локальный мониторинг кармана и заметок на узле-агенте (Windows)."""
    notes_file = pocket_dir / ".notes" / "notes.jsonl"
    agent_bus_dir = pocket_dir / "agent_bus"
    agent_bus_dir.mkdir(parents=True, exist_ok=True)

    initial_notes = read_all_notes(notes_file)
    seen_note_ids: set[str] = {n.get("note_id") for n in initial_notes if n.get("note_id")}
    initial_files = get_pocket_files(pocket_dir)

    print(
        f"[WATCHER_READY] Agent mode: monitoring {pocket_dir} (timeout={timeout}s)...",
        flush=True,
    )

    start_time = time.time()
    while True:
        if timeout > 0 and (time.time() - start_time) > timeout:
            event = {
                "event": "timeout",
                "timestamp": datetime.now(UTC).isoformat(),
                "message": f"Timeout of {timeout}s reached with no events.",
            }
            print(json.dumps(event, ensure_ascii=False), flush=True)
            sys.exit(0)

        # 1. Проверка новых заметок от удаленного узла
        curr_notes = read_all_notes(notes_file)
        new_incoming_notes = []
        for n in curr_notes:
            nid = n.get("note_id")
            if nid and nid not in seen_note_ids:
                seen_note_ids.add(nid)
                if not ignore_author or n.get("author_os") != ignore_author:
                    new_incoming_notes.append(n)

        if new_incoming_notes:
            for note in new_incoming_notes:
                event = {
                    "event": "new_note",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "total_notes": len(curr_notes),
                    "note": note,
                }
                print(json.dumps(event, ensure_ascii=False), flush=True)
                if not continuous:
                    sys.exit(0)

        # 2. Проверка новых и измененных файлов в кармане
        curr_files = get_pocket_files(pocket_dir)
        new_files = set(curr_files.keys()) - set(initial_files.keys())
        if new_files:
            for rel_p in sorted(new_files):
                full_p = pocket_dir / rel_p
                size, _ = curr_files[rel_p]
                event = {
                    "event": "file_created",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "relative_path": rel_p,
                    "full_path": str(full_p),
                    "size_bytes": size,
                    "preview": read_preview(full_p),
                }
                print(json.dumps(event, ensure_ascii=False), flush=True)
                initial_files[rel_p] = curr_files[rel_p]
                if not continuous:
                    sys.exit(0)

        for rel_p, (sz, mt) in curr_files.items():
            if rel_p in initial_files:
                orig_sz, orig_mt = initial_files[rel_p]
                if sz != orig_sz or mt > orig_mt + 0.01:
                    full_p = pocket_dir / rel_p
                    event = {
                        "event": "file_modified",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "relative_path": rel_p,
                        "full_path": str(full_p),
                        "size_bytes": sz,
                        "preview": read_preview(full_p),
                    }
                    print(json.dumps(event, ensure_ascii=False), flush=True)
                    initial_files[rel_p] = (sz, mt)
                    if not continuous:
                        sys.exit(0)

        time.sleep(poll_interval)


async def _poll_client_loop(
    cfg: BridgeConfig,
    timeout: int = 300,
    poll_interval: float = 1.0,
    ignore_author: str = "linux",
    continuous: bool = False,
) -> None:
    """Асинхронный опрос удаленного узла клиентом (Linux)."""
    from bridge_client_linux.client import BridgeClient

    client = BridgeClient(config=cfg)
    pocket_dir = cfg.get_pocket_dir()
    agent_bus_dir = pocket_dir / "agent_bus"
    agent_bus_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[WATCHER_READY] Client mode: polling {cfg.connection.host}:{cfg.connection.port} "
        f"for remote events (timeout={timeout}s)...",
        flush=True,
    )

    seen_note_ids: set[str] = set()
    initial_remote_manifest: dict[str, Any] = {}

    # Первоначальный снимок удаленного состояния
    with contextlib.suppress(Exception):
        async with client:
            hist = await client.note_history(limit=50)
            seen_note_ids = {n.note_id for n in hist.notes if n.note_id}
            man = await client.pocket_manifest()
            initial_remote_manifest = {f.relative_path: f for f in man.files}

    start_time = time.time()
    while True:
        if timeout > 0 and (time.time() - start_time) > timeout:
            event = {
                "event": "timeout",
                "timestamp": datetime.now(UTC).isoformat(),
                "message": f"Timeout of {timeout}s reached with no remote events.",
            }
            print(json.dumps(event, ensure_ascii=False), flush=True)
            return

        try:
            async with client:
                # 1. Проверяем удаленные заметки
                hist = await client.note_history(limit=20)
                new_remote_notes = []
                for n in hist.notes:
                    if n.note_id and n.note_id not in seen_note_ids:
                        seen_note_ids.add(n.note_id)
                        if not ignore_author or n.author_os != ignore_author:
                            new_remote_notes.append(n)

                if new_remote_notes:
                    for note in new_remote_notes:
                        event = {
                            "event": "new_remote_note",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "author": note.author_os,
                            "text": note.text,
                            "note_id": note.note_id,
                        }
                        print(json.dumps(event, ensure_ascii=False), flush=True)
                        if not continuous:
                            return

                # 2. Проверяем удаленный карман на новые/обновленные файлы
                man = await client.pocket_manifest()
                curr_remote = {f.relative_path: f for f in man.files}

                has_updates = False
                for rel_p, rem_f in curr_remote.items():
                    if rel_p not in initial_remote_manifest:
                        has_updates = True
                        break
                    old_f = initial_remote_manifest[rel_p]
                    if (
                        old_f.size_bytes != rem_f.size_bytes
                        or old_f.sha256_hash != rem_f.sha256_hash
                    ):
                        has_updates = True
                        break

                if has_updates:
                    # Автоматически синхронизируем (скачиваем) обновления
                    sync_res = await client.pocket_sync(direction="pull")
                    initial_remote_manifest = curr_remote
                    event = {
                        "event": "remote_files_synced",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "pulled_count": len(sync_res.pulled_files),
                        "synced_count": len(sync_res.synced_files),
                        "files": [f.relative_path for f in sync_res.pulled_files],
                    }
                    print(json.dumps(event, ensure_ascii=False), flush=True)
                    if not continuous:
                        return

        except Exception:
            # При кратковременной сетевой недоступности не падаем, ждем следующего тика
            await asyncio.sleep(poll_interval)
            continue

        await asyncio.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bridge Local bidirectional wake-up watcher for Antigravity subagents."
    )
    parser.add_argument(
        "--role",
        choices=["auto", "agent", "client"],
        default="auto",
        help="Watcher role (auto: agent on Windows, client on Linux)",
    )
    parser.add_argument(
        "--pocket",
        type=str,
        default="",
        help="Optional path to pocket directory (defaults to BridgeConfig canonical pocket)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300, 0 for infinite)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0s)",
    )
    parser.add_argument(
        "--ignore-author",
        type=str,
        default="",
        help="Author OS to ignore to avoid self-waking (defaults to current OS)",
    )
    parser.add_argument(
        "--continuous",
        "-c",
        action="store_true",
        help="Continuous monitoring instead of single-shot exit",
    )
    args = parser.parse_args()

    cfg = BridgeConfig.load()
    pocket_dir = Path(args.pocket).resolve() if args.pocket else cfg.get_pocket_dir()

    role = args.role
    if role == "auto":
        role = "agent" if sys.platform == "win32" else "client"

    default_ignore = "windows" if role == "agent" else "linux"
    ignore_author = args.ignore_author or default_ignore

    if role == "agent":
        run_agent_watcher(
            pocket_dir=pocket_dir,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            ignore_author=ignore_author,
            continuous=args.continuous,
        )
    else:
        asyncio.run(
            _poll_client_loop(
                cfg=cfg,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
                ignore_author=ignore_author,
                continuous=args.continuous,
            )
        )


if __name__ == "__main__":
    main()
