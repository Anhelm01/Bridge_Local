"""
bridge_agent_win.executor — Исполнитель команд PowerShell с таймаутами и UTF-8 кодировкой.

Реализует:
  - Безопасный запуск PowerShell с повышенными привилегиями (-ExecutionPolicy Bypass -NoProfile).
  - Принудительную установку UTF-8 кодировки консоли (chcp 65001 и $OutputEncoding).
  - Контроль таймаута с вызовом Process Tree Killer при превышении лимита времени.
  - Декодирование вывода через WindowsOutputDecoder (устранение mojibake).
  - Кроссплатформенный Mock-фоллбэк для локальной разработки и тестирования под Linux.
  - Dev-Mode Hyper-Logging: дампинг PID, аргументов, микросекундных замеров и exit-кодов.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime

from bridge_agent_win.process_killer import kill_process_tree
from bridge_core.codec import WindowsOutputDecoder
from bridge_core.models import (
    ExecRequestParams,
    ExecResult,
    ExecTimeoutErrorData,
    RpcErrorCode,
)
from bridge_core.transport import RpcCallError

logger = logging.getLogger(__name__)


class PowerShellExecutor:
    """
    Движок удаленного выполнения команд PowerShell на стороне агента Windows.
    """

    def __init__(
        self,
        powershell_bin: str | None = None,
        allow_posix_fallback: bool = True,
        dev_logging: bool = True,
    ) -> None:
        self.dev_logging = dev_logging
        self.allow_posix_fallback = allow_posix_fallback

        # Ищем доступный бинарник powershell/pwsh
        self.powershell_bin = powershell_bin or self._detect_powershell()
        logger.info(
            "[EXECUTOR] Инициализирован: binary=%s (platform=%s, posix_fallback=%s)",
            self.powershell_bin,
            sys.platform,
            self.allow_posix_fallback,
        )

    def _detect_powershell(self) -> str | None:
        """Детектирует наличие PowerShell в системе (pwsh / powershell.exe)."""
        candidates = ["powershell.exe", "powershell", "pwsh"]
        for cand in candidates:
            path = shutil.which(cand)
            if path:
                return path
        return None

    def _build_command_args(self, command: str) -> list[str]:
        """
        Формирует список аргументов запуска PowerShell с гарантией UTF-8 консоли.
        """
        # Префикс инициализации UTF-8 в PowerShell сессии
        utf8_init = (
            "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new(); "
        )
        full_command = utf8_init + command

        if self.powershell_bin:
            return [
                self.powershell_bin,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                full_command,
            ]

        # Если powershell нет (например на чистом Linux в mock-режиме)
        if self.allow_posix_fallback and sys.platform != "win32":
            logger.debug("[EXECUTOR-MOCK] PowerShell не найден, фоллбэк на /bin/bash")
            return ["/bin/bash", "-c", command]

        raise FileNotFoundError("PowerShell (powershell.exe или pwsh) не найден в PATH системы")

    async def execute(self, params: ExecRequestParams) -> ExecResult:
        """
        Асинхронно выполняет команду PowerShell с контролем таймаута.

        Args:
            params: Параметры выполнения (команда, таймаут, рабочий каталог, env).

        Returns:
            ExecResult с кодом возврата, stdout, stderr и длительностью.

        Raises:
            RpcCallError(COMMAND_TIMEOUT): При превышении таймаута выполнения.
        """
        t0 = time.perf_counter_ns()
        started_at = datetime.now(UTC).isoformat()

        cmd_args = self._build_command_args(params.command)

        # Переменные окружения процесса
        proc_env = os.environ.copy()
        proc_env["PYTHONIOENCODING"] = "utf-8"
        if params.env:
            proc_env.update(params.env)

        logger.info(
            "[DEV-EXEC-START] Команда: %.120s (timeout=%ds, admin=%s, dir=%s)",
            params.command,
            params.timeout_sec,
            params.run_as_admin,
            params.working_dir,
        )

        # Настройка группы процессов для надёжного завершения дерева
        kwargs: dict[str, object] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": params.working_dir,
            "env": proc_env,
        }

        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

        proc = await asyncio.create_subprocess_exec(*cmd_args, **kwargs)  # type: ignore[arg-type]
        pid = proc.pid
        logger.debug("[DEV-EXEC] Процесс запущен: PID=%d", pid)

        try:
            raw_stdout, raw_stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(params.timeout_sec),
            )
            timed_out = False
            killed_pids: list[int] = []

        except TimeoutError as err:
            timed_out = True
            logger.warning(
                "[DEV-EXEC-TIMEOUT] PID %d превысил таймаут %ds! Убиваем дерево...",
                pid,
                params.timeout_sec,
            )
            killed_pids = kill_process_tree(pid)

            # Пытаемся забрать остаточный вывод, если успел накопиться
            try:
                raw_stdout, raw_stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=0.5,
                )
            except Exception:
                raw_stdout, raw_stderr = b"", b""

            duration_ms = int((time.perf_counter_ns() - t0) // 1_000_000)
            completed_at = datetime.now(UTC).isoformat()

            decoded_partial = WindowsOutputDecoder.decode(raw_stdout).text
            timeout_data = ExecTimeoutErrorData(
                timeout_sec=params.timeout_sec,
                duration_ms=duration_ms,
                partial_stdout=decoded_partial[:1000],
                processes_killed=killed_pids,
            )

            raise RpcCallError(
                code=RpcErrorCode.COMMAND_TIMEOUT,
                message=f"Команда превысила лимит времени ({params.timeout_sec} сек)",
                data=timeout_data.model_dump(),
            ) from err

        duration_ms = int((time.perf_counter_ns() - t0) // 1_000_000)
        completed_at = datetime.now(UTC).isoformat()

        # Декодируем вывод с нормализацией и устранением mojibake
        decoded_stdout = WindowsOutputDecoder.decode(raw_stdout)
        decoded_stderr = WindowsOutputDecoder.decode(raw_stderr)

        exit_code = proc.returncode if proc.returncode is not None else -1

        logger.info(
            "[DEV-EXEC-DONE] PID %d завершился (exit=%d, duration=%d ms, out=%d ch, err=%d ch)",
            pid,
            exit_code,
            duration_ms,
            len(decoded_stdout.text),
            len(decoded_stderr.text),
        )

        return ExecResult(
            exit_code=exit_code,
            stdout=decoded_stdout.text,
            stderr=decoded_stderr.text,
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
            timed_out=timed_out,
            encoding_detected=decoded_stdout.encoding_used,
        )
