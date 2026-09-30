"""
bridge_core.logger — Атомарный JSONL-логгер аудита и Dev-Mode Hyper-Logging.

Реализует:
  - Атомарную дозапись записей аудита в карман (pocket/logs/YYYY-MM-DD.jsonl) с fsync.
  - Потокобезопасную и асинхронную очередь с предотвращением race conditions и file lock конфликтов.
  - Кастомный уровень логирования TRACE (уровень 5) для детального сетевого и системного дампинга.
  - Управление уровнями детализации (Dev Hyper-Logging vs Release).
  - Чтение и выборку логов для ИИ-агентов (tail/search).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bridge_core.config import LoggingConfig
from bridge_core.models import AuditLogEntry
from bridge_core.retry import retry_with_backoff

# Регистрируем уровень TRACE (5), который детальнее DEBUG (10)
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def _logger_trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Метод .trace() для стандартного Logger."""
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kwargs)


# Добавляем метод trace в класс Logger, если его ещё нет
if not hasattr(logging.Logger, "trace"):
    logging.Logger.trace = _logger_trace  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Атомарный JSONL-логгер аудита
# ---------------------------------------------------------------------------


class AtomicJsonlLogger:
    """
    Потокобезопасный и корутинобезопасный логгер для записей аудита в .jsonl.

    Каждая строка пишется с flush() и os.fsync() для гарантии сохранности данных
    даже при внезапной перезагрузке или сбое питания.
    """

    def __init__(
        self, logs_dir: Path | str, auto_fsync: bool = True, dev_logging: bool = True
    ) -> None:
        self.logs_dir = Path(logs_dir)
        self.auto_fsync = auto_fsync
        self.dev_logging = dev_logging
        self._thread_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_log_path(self) -> Path:
        """Возвращает путь к лог-файлу текущего дня по UTC: YYYY-MM-DD.jsonl."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return self.logs_dir / f"{today}.jsonl"

    def write_sync(self, entry: AuditLogEntry) -> Path:
        """
        Синхронно и атомарно записывает запись аудита в файл.

        Args:
            entry: Модель записи аудита.

        Returns:
            Путь к файлу, в который была произведена запись.
        """
        t0 = time.perf_counter_ns()
        log_path = self._get_current_log_path()
        line = entry.model_dump_json() + "\n"

        def _do_write() -> Path:
            with self._thread_lock, open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                if self.auto_fsync:
                    os.fsync(f.fileno())
            return log_path

        retry_with_backoff(_do_write, max_retries=5, initial_delay=0.02)

        elapsed_us = (time.perf_counter_ns() - t0) // 1000
        if self.dev_logging and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[DEV-AUDIT-LOG] Записана строка аудита: method=%s, id=%s, path=%s, fsync=%d µs",
                entry.method,
                entry.request_id,
                log_path.name,
                elapsed_us,
            )
        return log_path

    async def write(self, entry: AuditLogEntry) -> Path:
        """
        Асинхронная обёртка для записи записи аудита через asyncio.Lock.

        Предотвращает конкурентный доступ между асинхронными тасками.
        """
        async with self._async_lock:
            # Выполняем синхронный I/O в потоке, чтобы не блокировать event loop
            return await asyncio.to_thread(self.write_sync, entry)

    def read_entries(
        self,
        date_str: str | None = None,
        limit: int = 100,
        reverse: bool = True,
    ) -> list[AuditLogEntry]:
        """
        Считывает записи аудита за указанную дату (или за сегодня).

        Args:
            date_str: Дата в формате YYYY-MM-DD (None = сегодня).
            limit: Максимальное количество записей.
            reverse: Начинать с самых свежих записей (хвост лога).

        Returns:
            Список валидированных объектов AuditLogEntry.
        """
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        log_path = self.logs_dir / f"{target_date}.jsonl"

        if not log_path.exists():
            return []

        entries: list[AuditLogEntry] = []
        with self._thread_lock:
            lines = log_path.read_text(encoding="utf-8").splitlines()

        if reverse:
            lines = list(reversed(lines))

        for raw_line in lines:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = AuditLogEntry.model_validate_json(raw_line)
                entries.append(entry)
                if len(entries) >= limit:
                    break
            except Exception as e:
                logger.warning("Пропущена повреждённая строка в логе %s: %s", log_path, e)

        return entries


# ---------------------------------------------------------------------------
# Инициализация Dev-Mode логирования
# ---------------------------------------------------------------------------


def setup_logging(config: LoggingConfig | None = None) -> None:
    """
    Настраивает форматирование и обработчики логов на основе LoggingConfig.

    Поддерживает уровень TRACE, микросекундные таймстемпы и переключение dev_mode.
    """
    cfg = config or LoggingConfig()

    level_name = cfg.level.upper()
    if not cfg.dev_mode and level_name == "TRACE":
        target_level = logging.INFO
    elif level_name == "TRACE":
        target_level = TRACE_LEVEL_NUM
    else:
        target_level = getattr(logging, level_name, logging.INFO)

    # Формат с миллисекундами и именами потоков/модулей для отладки
    if cfg.dev_mode:
        log_format = "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"
    else:
        log_format = "%(asctime)s | %(levelname)-7s | %(message)s"

    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(target_level)

    # Очищаем старые обработчики во избежание дублирования
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    if cfg.console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(target_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if cfg.file_output:
        file_path = Path(cfg.file_output)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(target_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.debug(
        "Логирование инициализировано: level=%s (num=%d), dev_mode=%s",
        level_name,
        target_level,
        cfg.dev_mode,
    )
