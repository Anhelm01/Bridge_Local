"""
bridge_core.notes — Подсистема «Записки» (Notes & Fast Text Sharing).

Реализует:
  - Хранение заметок и коротких текстовых сообщений между узлами (Linux ↔ Windows).
  - Хранилище на базе JSONL (pocket/.notes/notes.jsonl).
  - Атомарное добавление записок и атомарное обновление статуса прочтения (delivered -> read).
  - Фильтрацию по времени (since) и пагинацию/лимит (limit).
  - Потокобезопасность через asyncio.Lock.
  - Подробное Dev-Mode логирование операций с записками.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from bridge_core.models import (
    NoteDeliveryResult,
    NoteEntry,
    NoteHistoryParams,
    NoteHistoryResult,
    NoteMarkReadParams,
    NoteMarkReadResult,
    NoteSendParams,
    NoteStatus,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Текущее время в ISO-8601 UTC."""
    return datetime.now(UTC).isoformat()


class NotesManager:
    """
    Менеджер хранения и обработки заметок (Записок).

    Записки хранятся в pocket/.notes/notes.jsonl в формате JSONL.
    Каждая строка — объект NoteEntry.
    """

    def __init__(
        self,
        pocket_dir: Path | str,
        dev_logging: bool = True,
    ) -> None:
        self.pocket_dir = Path(pocket_dir).resolve()
        self.notes_dir = self.pocket_dir / ".notes"
        self.notes_file = self.notes_dir / "notes.jsonl"
        self.dev_logging = dev_logging
        self._lock = asyncio.Lock()

        # Создаём директорию для заметок, если её нет
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    async def add_note(
        self,
        params: NoteSendParams,
        note_id: str | None = None,
    ) -> NoteDeliveryResult:
        """
        Добавляет новую записку в хранилище.

        Args:
            params: Параметры записки (текст, автор, целевой узел).
            note_id: Опциональный ID записки (если не передан, генерируется UUIDv4).

        Returns:
            NoteDeliveryResult со статусом доставки и ID записки.
        """
        async with self._lock:
            nid = note_id or str(uuid.uuid4())
            ts = _now_iso()
            entry = NoteEntry(
                note_id=nid,
                timestamp=ts,
                author_os=params.author_os,
                text=params.text,
                status=NoteStatus.DELIVERED,
            )

            line = entry.model_dump_json() + "\n"
            t0 = time.perf_counter_ns()

            # Атомарный append с принудительным сбросом буфера
            with open(self.notes_file, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

            elapsed_us = (time.perf_counter_ns() - t0) // 1000
            if self.dev_logging:
                logger.info(
                    "[DEV-NOTE-ADD] Заметка ID %s добавлена (автор: %s, длина: %d симв., %d µs)",
                    nid,
                    params.author_os,
                    len(params.text),
                    elapsed_us,
                )

            return NoteDeliveryResult(
                note_id=nid,
                received_at=ts,
                status=NoteStatus.DELIVERED,
            )

    async def get_history(
        self,
        params: NoteHistoryParams | None = None,
    ) -> NoteHistoryResult:
        """
        Возвращает историю записок с возможностью фильтрации по времени и лимиту.

        Args:
            params: Параметры выборки (limit, since).

        Returns:
            NoteHistoryResult со списком записок и общим количеством.
        """
        async with self._lock:
            if not self.notes_file.exists():
                return NoteHistoryResult(notes=[], total_count=0)

            limit = params.limit if params else 50
            since = params.since if params else None

            entries: list[NoteEntry] = []
            try:
                with open(self.notes_file, encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            data = json.loads(stripped)
                            entry = NoteEntry.model_validate(data)
                            if since and entry.timestamp < since:
                                continue
                            entries.append(entry)
                        except Exception as e:
                            logger.warning(
                                "[NOTES] Пропущена некорректная строка %d в %s: %s",
                                line_num,
                                self.notes_file,
                                e,
                            )
            except OSError as e:
                logger.error("[NOTES] Ошибка чтения файла заметок: %s", e)
                return NoteHistoryResult(notes=[], total_count=0)

            total_count = len(entries)
            # Возвращаем последние N записок (от более старых к новым, либо по запросу)
            sliced = entries[-limit:] if limit > 0 else entries

            if self.dev_logging:
                logger.debug(
                    "[DEV-NOTE-HISTORY] Возвращено %d/%d заметок (limit=%d, since=%s)",
                    len(sliced),
                    total_count,
                    limit,
                    since,
                )

            return NoteHistoryResult(notes=sliced, total_count=total_count)

    async def mark_read(self, params: NoteMarkReadParams) -> NoteMarkReadResult:
        """
        Отмечает указанные записки как прочитанные (status = read).

        Производит атомарную перезапись файла notes.jsonl через временный файл.

        Args:
            params: Список идентификаторов записок.

        Returns:
            NoteMarkReadResult с количеством обновлённых записок.
        """
        async with self._lock:
            if not self.notes_file.exists():
                return NoteMarkReadResult(marked_count=0)

            ids_to_mark = set(params.note_ids)
            if not ids_to_mark:
                return NoteMarkReadResult(marked_count=0)

            all_entries: list[NoteEntry] = []
            marked_count = 0

            with open(self.notes_file, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        entry = NoteEntry.model_validate(data)
                        if entry.note_id in ids_to_mark and entry.status != NoteStatus.READ:
                            # Обновляем статус
                            entry = NoteEntry(
                                note_id=entry.note_id,
                                timestamp=entry.timestamp,
                                author_os=entry.author_os,
                                text=entry.text,
                                status=NoteStatus.READ,
                            )
                            marked_count += 1
                        all_entries.append(entry)
                    except Exception:
                        continue

            if marked_count > 0:
                tmp_file = self.notes_dir / ".notes.jsonl.tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    for e in all_entries:
                        f.write(e.model_dump_json() + "\n")
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(tmp_file, self.notes_file)

            if self.dev_logging:
                logger.info(
                    "[DEV-NOTE-READ] Отмечено прочитанными: %d записок из %d запрошенных",
                    marked_count,
                    len(ids_to_mark),
                )

            return NoteMarkReadResult(marked_count=marked_count)
