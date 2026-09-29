"""
tests/unit/test_notes.py — Модульные тесты для подсистемы «Записки» (Notes).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bridge_core.models import (
    NodeOS,
    NoteHistoryParams,
    NoteMarkReadParams,
    NoteSendParams,
    NoteStatus,
)
from bridge_core.notes import NotesManager


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    p = tmp_path / "pocket"
    p.mkdir()
    return p


@pytest.fixture
def manager(notes_dir: Path) -> NotesManager:
    return NotesManager(pocket_dir=notes_dir, dev_logging=True)


@pytest.mark.asyncio
async def test_add_note_basic(manager: NotesManager, notes_dir: Path) -> None:
    params = NoteSendParams(
        text="Привет из Linux!",
        author_os=NodeOS.LINUX,
        target_node="win-pc",
    )
    result = await manager.add_note(params)

    assert result.note_id
    assert result.status == NoteStatus.DELIVERED
    assert result.received_at

    # Проверяем, что файл notes.jsonl создан в pocket/.notes/
    notes_file = notes_dir / ".notes" / "notes.jsonl"
    assert notes_file.exists()
    content = notes_file.read_text(encoding="utf-8")
    assert "Привет из Linux!" in content
    assert result.note_id in content


@pytest.mark.asyncio
async def test_get_history_empty(manager: NotesManager) -> None:
    history = await manager.get_history()
    assert history.total_count == 0
    assert history.notes == []


@pytest.mark.asyncio
async def test_get_history_limit_and_since(manager: NotesManager) -> None:
    # Добавляем 5 заметок с небольшими паузами для разных timestamp
    note_ids: list[str] = []
    for i in range(5):
        res = await manager.add_note(NoteSendParams(text=f"Записка {i}", author_os=NodeOS.LINUX))
        note_ids.append(res.note_id)

    # 1. Запрос всей истории
    all_hist = await manager.get_history(NoteHistoryParams(limit=10))
    assert all_hist.total_count == 5
    assert len(all_hist.notes) == 5

    # 2. Лимит 2 последних
    limit_hist = await manager.get_history(NoteHistoryParams(limit=2))
    assert limit_hist.total_count == 5
    assert len(limit_hist.notes) == 2
    assert limit_hist.notes[0].text == "Записка 3"
    assert limit_hist.notes[1].text == "Записка 4"

    # 3. Фильтр since
    middle_ts = all_hist.notes[2].timestamp
    since_hist = await manager.get_history(NoteHistoryParams(since=middle_ts))
    assert len(since_hist.notes) == 3
    assert since_hist.notes[0].text == "Записка 2"


@pytest.mark.asyncio
async def test_mark_read(manager: NotesManager) -> None:
    n1 = await manager.add_note(NoteSendParams(text="msg 1", author_os=NodeOS.LINUX))
    n2 = await manager.add_note(NoteSendParams(text="msg 2", author_os=NodeOS.WINDOWS))

    # Отмечаем первую прочитанной
    res = await manager.mark_read(NoteMarkReadParams(note_ids=[n1.note_id]))
    assert res.marked_count == 1

    hist = await manager.get_history()
    notes_by_id = {n.note_id: n for n in hist.notes}
    assert notes_by_id[n1.note_id].status == NoteStatus.READ
    assert notes_by_id[n2.note_id].status == NoteStatus.DELIVERED

    # Повторная отметка той же записки не должна увеличивать счётчик
    res2 = await manager.mark_read(NoteMarkReadParams(note_ids=[n1.note_id]))
    assert res2.marked_count == 0


@pytest.mark.asyncio
async def test_corrupted_lines_tolerance(manager: NotesManager, notes_dir: Path) -> None:
    # Записываем нормальную заметку, битую строку, и еще одну нормальную
    await manager.add_note(NoteSendParams(text="valid 1", author_os=NodeOS.LINUX))

    notes_file = notes_dir / ".notes" / "notes.jsonl"
    with open(notes_file, "a", encoding="utf-8") as f:
        f.write("THIS_IS_NOT_JSON\n")

    await manager.add_note(NoteSendParams(text="valid 2", author_os=NodeOS.WINDOWS))

    hist = await manager.get_history()
    # Битая строка должна быть пропущена
    assert hist.total_count == 2
    assert [n.text for n in hist.notes] == ["valid 1", "valid 2"]


@pytest.mark.asyncio
async def test_concurrent_add_notes(manager: NotesManager) -> None:
    # Параллельное добавление 20 записок
    async def _add(i: int) -> str:
        res = await manager.add_note(NoteSendParams(text=f"concurrent {i}", author_os=NodeOS.LINUX))
        return res.note_id

    ids = await asyncio.gather(*[_add(i) for i in range(20)])
    assert len(ids) == 20

    hist = await manager.get_history(NoteHistoryParams(limit=50))
    assert hist.total_count == 20
