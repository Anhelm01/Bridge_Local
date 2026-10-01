"""
bridge_agent_win.process_killer — Надежное уничтожение дерева процессов (Process Tree Killer).

Решает проблему зависших фоновых подпроцессов в Windows и Linux:
  - При таймауте завершает не только родительский powershell.exe, но и ВСЕ его дочерние процессы
    (например, запущенные скриптом curl, python, ffmpeg, ping или вечные циклы).
  - На Windows: использует комбинацию taskkill /F /T /PID и psutil (если доступен).
  - На Linux (для Mock-режима и тестов): использует группы процессов (os.killpg) и psutil.
  - Возвращает список убитых PID'ов для отчёта в JsonRpcErrorResponse и аудит-логе.
  - Подробная Dev-Mode трассировка времени завершения и затронутых процессов.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import sys
import time

logger = logging.getLogger(__name__)


def kill_process_tree(pid: int, timeout_sec: float = 3.0) -> list[int]:
    """
    Принудительно уничтожает процесс и всё его дерево дочерних процессов.

    Args:
        pid: Идентификатор родительского процесса.
        timeout_sec: Максимальное время ожидания завершения.

    Returns:
        Список PID'ов процессов, которые были отправлены на уничтожение.
    """
    t0 = time.perf_counter_ns()
    killed_pids: list[int] = [pid]

    if pid <= 0:
        return []

    # 1. Попытка через psutil (если установлена библиотека)
    try:
        import psutil

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                killed_pids.append(child.pid)

            # Сначала отправляем SIGTERM / terminate
            for proc in [*children, parent]:
                with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    proc.kill()

            # Ожидаем завершения без перехвата os.waitpid
            # (чтобы не ломать returncode у вызывающего Popen)
            deadline = time.time() + timeout_sec
            procs = [*children, parent]
            for proc in procs:
                while time.time() < deadline:
                    try:
                        if not proc.is_running() or proc.status() == getattr(
                            psutil, "STATUS_ZOMBIE", "zombie"
                        ):
                            break
                        time.sleep(0.01)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break

            # Финальная зачистка: если кто-то остался жив, добиваем
            for proc in procs:
                with contextlib.suppress(Exception):
                    if proc.is_running() and proc.status() != getattr(
                        psutil, "STATUS_ZOMBIE", "zombie"
                    ):
                        proc.kill()

            elapsed_us = (time.perf_counter_ns() - t0) // 1000
            logger.info(
                "[DEV-KILLER] Дерево PID %d (всего %d процессов) убито через psutil за %d µs: %s",
                pid,
                len(killed_pids),
                elapsed_us,
                killed_pids,
            )
            return killed_pids
        except psutil.NoSuchProcess:
            logger.debug("[DEV-KILLER] Процесс PID %d уже завершился", pid)
            return killed_pids
    except ImportError:
        pass

    # 2. Нативная реализация для Windows: taskkill /F /T /PID
    if sys.platform == "win32":
        try:
            # /F = Force, /T = Tree (убивает все дочерние)
            cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            elapsed_us = (time.perf_counter_ns() - t0) // 1000
            logger.info(
                "[DEV-KILLER-WIN] taskkill PID %d завершился (exit=%d) за %d µs: %s",
                pid,
                res.returncode,
                elapsed_us,
                res.stdout.strip(),
            )
            return killed_pids
        except Exception as e:
            logger.error("[DEV-KILLER-WIN] Сбой вызова taskkill для PID %d: %s", pid, e)
            return killed_pids

    # 3. Нативная реализация для POSIX / Linux (Mock-режим)
    try:
        current_pgid = os.getpgrp()
        try:
            pgid = os.getpgid(pid)
            # ВАЖНО: Ни в коем случае не стрелять по текущей группе процессов
            # (в ней живёт pytest/текущий процесс)
            if pgid != current_pgid and pgid > 0:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)

        elapsed_us = (time.perf_counter_ns() - t0) // 1000
        logger.info(
            "[DEV-KILLER-POSIX] Процесс PID %d убит через SIGKILL за %d µs",
            pid,
            elapsed_us,
        )
    except Exception as e:
        logger.error("[DEV-KILLER-POSIX] Сбой при убийстве PID %d: %s", pid, e)

    return killed_pids
