"""
Тесты для bridge_core.logger — атомарный аудит-логгер .jsonl, ротация и уровень TRACE.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from bridge_core.config import LoggingConfig
from bridge_core.logger import AtomicJsonlLogger, setup_logging
from bridge_core.models import AuditLogEntry, AuditStatus


class TestAtomicJsonlLogger:
    """Тесты атомарного .jsonl логгера."""

    def test_write_sync_creates_dated_file(self, tmp_path: Path) -> None:
        logger = AtomicJsonlLogger(logs_dir=tmp_path)
        entry = AuditLogEntry(
            session_id="s1",
            client_ip="127.0.0.1",
            method="exec.run",
            request_id="req-1",
            status=AuditStatus.SUCCESS,
        )

        log_file = logger.write_sync(entry)
        assert log_file.exists()
        assert log_file.suffix == ".jsonl"
        assert log_file.parent == tmp_path

        # Проверяем содержимое
        content = log_file.read_text(encoding="utf-8").strip()
        assert "s1" in content
        assert "exec.run" in content

    @pytest.mark.asyncio
    async def test_async_write_concurrent(self, tmp_path: Path) -> None:
        """Проверяем параллельную запись 30 записей из разных корутин без повреждения строк."""
        logger = AtomicJsonlLogger(logs_dir=tmp_path)

        async def worker(idx: int) -> None:
            entry = AuditLogEntry(
                session_id=f"sess-{idx}",
                client_ip="192.168.1.1",
                method="notes.send",
                request_id=f"req-{idx}",
                status=AuditStatus.SUCCESS,
            )
            await logger.write(entry)

        # Запускаем 30 параллельных записей
        tasks = [worker(i) for i in range(30)]
        await asyncio.gather(*tasks)

        # Считываем и проверяем, что все 30 записаны и валидны
        entries = logger.read_entries(limit=100)
        assert len(entries) == 30
        session_ids = {e.session_id for e in entries}
        assert len(session_ids) == 30

    def test_read_entries_skips_corrupted_lines(self, tmp_path: Path) -> None:
        logger = AtomicJsonlLogger(logs_dir=tmp_path)
        log_file = logger._get_current_log_path()

        # Пишем одну валидную, одну битую, одну валидную
        valid1 = AuditLogEntry(
            session_id="v1",
            client_ip="1.1.1.1",
            method="test",
            request_id="r1",
            status=AuditStatus.SUCCESS,
        ).model_dump_json()
        valid2 = AuditLogEntry(
            session_id="v2",
            client_ip="1.1.1.1",
            method="test",
            request_id="r2",
            status=AuditStatus.SUCCESS,
        ).model_dump_json()

        log_file.write_text(f"{valid1}\nCORRUPTED_LINE_NOT_JSON\n{valid2}\n", encoding="utf-8")

        entries = logger.read_entries(limit=10)
        # Должны прочитаться обе валидные записи, битая пропущена
        assert len(entries) == 2
        assert {e.session_id for e in entries} == {"v1", "v2"}


class TestLoggingSetup:
    """Тесты настройки логгера и кастомного уровня TRACE."""

    def test_setup_logging_trace_level(self) -> None:
        cfg = LoggingConfig(level="TRACE", dev_mode=True, console_output=True)
        setup_logging(cfg)

        log = logging.getLogger("test_trace_logger")
        # Проверяем наличие и работу метода .trace()
        assert hasattr(log, "trace")
        # Не должно вызывать исключений
        log.trace("Тестовое TRACE-сообщение для дебага")

    def test_setup_logging_file_output(self, tmp_path: Path) -> None:
        file_path = tmp_path / "app.log"
        cfg = LoggingConfig(
            level="DEBUG",
            dev_mode=True,
            console_output=False,
            file_output=str(file_path),
        )
        setup_logging(cfg)

        log = logging.getLogger("test_file_logger")
        log.info("Сообщение для записи в файл")

        # Сбрасываем хендлеры
        for h in logging.getLogger().handlers:
            h.flush()

        assert file_path.exists()
        assert "Сообщение для записи в файл" in file_path.read_text(encoding="utf-8")
