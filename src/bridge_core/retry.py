"""
bridge_core.retry — Утилиты повторных попыток с экспоненциальным бэкоффом (Chaos Resilience).

Обеспечивает устойчивость к:
  - Windows Sharing Violation (WinError 32: ERROR_SHARING_VIOLATION).
  - Блокировкам файлов другими процессами (антивирус, индексатор, резервное копирование).
  - Временным сетевым и файловым коллизиям (EBUSY, EACCES, PermissionError).
"""

from __future__ import annotations

import asyncio
import errno
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_sharing_violation(exc: BaseException) -> bool:
    """
    Проверяет, вызвана ли ошибка конфликтом совместного доступа (Windows Sharing Violation).

    Распознает:
      - PermissionError (включая Windows WinError 32: ERROR_SHARING_VIOLATION).
      - OSError с атрибутом winerror == 32.
      - OSError с кодами errno EBUSY или EACCES.
      - Строковые маркеры WinError 32, EBUSY или "used by another process".
    """
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        if getattr(exc, "winerror", None) == 32:
            return True
        if exc.errno in (errno.EBUSY, errno.EACCES):
            return True
    err_str = str(exc)
    return "WinError 32" in err_str or "EBUSY" in err_str or "used by another process" in err_str


def retry_with_backoff[T](
    func: Callable[..., T],
    max_retries: int = 5,
    initial_delay: float = 0.02,
    backoff_factor: float = 2.0,
    max_delay: float = 1.0,
    retry_on: Callable[[BaseException], bool] = is_sharing_violation,
) -> T:
    """
    Выполняет синхронную функцию с повторными попытками при ошибках совместного доступа.

    При обнаружении конфликта блокировки повторяет попытку с экспоненциальной задержкой.
    """
    attempt = 0
    delay = initial_delay
    while True:
        try:
            attempt += 1
            result = func()
            if attempt > 1:
                logger.info(
                    "[OK] Операция выполнена успешно после %d попыток (блокировка снята)",
                    attempt,
                )
            return result
        except BaseException as exc:
            if attempt >= max_retries or not retry_on(exc):
                logger.error(
                    "[FAIL] Превышен лимит повторов (%d/%d попыток): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                raise
            logger.warning(
                "[WARN] Конфликт доступа к файлу (WinError 32 / EBUSY / Lock): "
                "повтор через %.3fs (попытка %d/%d)...",
                delay,
                attempt,
                max_retries,
            )
            time.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)


async def async_retry_with_backoff[T](
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    max_retries: int = 5,
    initial_delay: float = 0.02,
    backoff_factor: float = 2.0,
    max_delay: float = 1.0,
    retry_on: Callable[[BaseException], bool] = is_sharing_violation,
) -> T:
    """
    Асинхронная версия выполнения корутины с повторами и экспоненциальным бэкоффом.
    """
    attempt = 0
    delay = initial_delay
    while True:
        try:
            attempt += 1
            result = await coro_fn()
            if attempt > 1:
                logger.info(
                    "[OK] Асинхронная операция выполнена успешно после %d попыток",
                    attempt,
                )
            return result
        except BaseException as exc:
            if attempt >= max_retries or not retry_on(exc):
                logger.error(
                    "[FAIL] Превышен лимит асинхронных повторов (%d/%d): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                raise
            logger.warning(
                "[WARN] Асинхронный конфликт блокировки: повтор через %.3fs (попытка %d/%d)...",
                delay,
                attempt,
                max_retries,
            )
            await asyncio.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)
