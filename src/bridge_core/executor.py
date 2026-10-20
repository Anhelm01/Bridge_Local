"""
bridge_core.executor — Платформенно-независимые исполнители команд (BaseExecutor, BashExecutor, PowerShellExecutor).

Реализует:
  - BaseExecutor: Универсальный базовый класс с полным жизненным циклом запуска процессов,
    контролем таймаутов через Process Tree Killer, UTF-8 декодированием и отслеживанием CWD.
  - BashExecutor: Исполнитель команд Bash (POSIX / Linux / macOS) с сохранением CWD.
  - PowerShellExecutor: Исполнитель команд PowerShell (Windows pwsh / powershell.exe) с UTF-8 консолью.
  - create_platform_executor: Фабрику выбора исполнителя по платформе ОС.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

from bridge_core.codec import WindowsOutputDecoder
from bridge_core.models import (
    ExecRequestParams,
    ExecResult,
    ExecTimeoutErrorData,
    RpcErrorCode,
)
from bridge_core.process_killer import kill_process_tree
from bridge_core.transport import RpcCallError

logger = logging.getLogger(__name__)


class BaseExecutor(abc.ABC):
    """
    Абстрактный контракт и базовый движок удалённого выполнения команд.
    Обеспечивает унифицированный жизненный цикл запуска, замера времени,
    контроля таймаутов с каскадным уничтожением дерева процессов и парсинга CWD.
    """

    CWD_MARKER_REGEX = re.compile(r"[\r\n]*__BRIDGE_CWD__:(.*?)(?:\r?\n|$)")

    def __init__(self, dev_logging: bool = True) -> None:
        self.dev_logging = dev_logging
        self.current_working_dir: str | None = None

    @abc.abstractmethod
    def _build_command_args(self, command: str) -> list[str]:
        """
        Формирует список аргументов командной строки для запуска шелла.

        Args:
            command: Исходная команда оператора.

        Returns:
            Список аргументов для передачи в asyncio.create_subprocess_exec.
        """

    def _setup_env(self, extra_env: dict[str, str] | None) -> dict[str, str]:
        """Формирует словарь переменных окружения процесса."""
        proc_env = os.environ.copy()
        proc_env["PYTHONIOENCODING"] = "utf-8"
        if extra_env:
            proc_env.update(extra_env)
        return proc_env

    def _get_subprocess_kwargs(
        self,
        effective_cwd: str | None,
        proc_env: dict[str, str],
    ) -> dict[str, Any]:
        """Формирует платформенные параметры запуска процесса."""
        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": effective_cwd,
            "env": proc_env,
        }
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return kwargs

    async def execute(self, params: ExecRequestParams) -> ExecResult:
        """
        Асинхронно выполняет команду с заданными параметрами.

        Args:
            params: Параметры выполнения (команда, таймаут, рабочий каталог, env).

        Returns:
            ExecResult с кодом возврата, stdout, stderr, замерами времени и CWD.

        Raises:
            RpcCallError: При таймауте (COMMAND_TIMEOUT) или фатальной ошибке запуска.
        """
        t0 = time.perf_counter_ns()
        started_at = datetime.now(UTC).isoformat()

        cmd_args = self._build_command_args(params.command)
        proc_env = self._setup_env(params.env)

        effective_cwd = params.working_dir or self.current_working_dir
        if effective_cwd and not os.path.exists(effective_cwd):
            effective_cwd = None

        if self.dev_logging:
            logger.info(
                "[DEV-EXEC-START] Команда: %.120s (timeout=%ds, dir=%s, effective_dir=%s)",
                params.command,
                params.timeout_sec,
                params.working_dir,
                effective_cwd,
            )

        kwargs = self._get_subprocess_kwargs(effective_cwd, proc_env)
        proc = await asyncio.create_subprocess_exec(*cmd_args, **kwargs)
        pid = proc.pid

        if self.dev_logging:
            logger.debug("[DEV-EXEC] Процесс запущен: PID=%d", pid)

        try:
            raw_stdout, raw_stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(params.timeout_sec),
            )
            timed_out = False
        except TimeoutError as err:
            timed_out = True
            logger.warning(
                "[DEV-EXEC-TIMEOUT] PID %d превысил таймаут %ds! Убиваем дерево...",
                pid,
                params.timeout_sec,
            )
            killed_pids = kill_process_tree(pid)

            # Пытаемся забрать остаточный вывод
            try:
                raw_stdout, raw_stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=0.5,
                )
            except Exception:
                raw_stdout, raw_stderr = b"", b""

            duration_ms = int((time.perf_counter_ns() - t0) // 1_000_000)
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

        # Декодируем вывод с нормализацией кодировки
        decoded_stdout_raw = WindowsOutputDecoder.decode(raw_stdout)
        decoded_stderr = WindowsOutputDecoder.decode(raw_stderr)

        # Извлекаем маркер CWD и очищаем stdout
        extracted_cwd: str | None = None
        cleaned_stdout = decoded_stdout_raw.text
        m = self.CWD_MARKER_REGEX.search(decoded_stdout_raw.text)
        if m:
            extracted_cwd = m.group(1).strip()
            cleaned_stdout = self.CWD_MARKER_REGEX.sub("", decoded_stdout_raw.text).rstrip("\r\n")
            if extracted_cwd:
                self.current_working_dir = extracted_cwd

        final_cwd = extracted_cwd or self.current_working_dir or effective_cwd
        exit_code = proc.returncode if proc.returncode is not None else -1

        if self.dev_logging:
            logger.info(
                "[DEV-EXEC-DONE] PID %d завершился (exit=%d, ms=%d, out=%d, err=%d, cwd=%s)",
                pid,
                exit_code,
                duration_ms,
                len(cleaned_stdout),
                len(decoded_stderr.text),
                final_cwd,
            )

        return ExecResult(
            exit_code=exit_code,
            stdout=cleaned_stdout,
            stderr=decoded_stderr.text,
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
            timed_out=timed_out,
            encoding_detected=decoded_stdout_raw.encoding_used,
            current_working_dir=final_cwd,
        )


class BashExecutor(BaseExecutor):
    """
    Движок удалённого выполнения команд Bash на стороне узлов POSIX / Linux / macOS.
    """

    def __init__(
        self,
        bash_bin: str | None = None,
        dev_logging: bool = True,
    ) -> None:
        super().__init__(dev_logging=dev_logging)
        self.bash_bin = bash_bin or self._detect_bash()
        if self.dev_logging:
            logger.info(
                "[BASH-EXECUTOR] Инициализирован: binary=%s (platform=%s)",
                self.bash_bin,
                sys.platform,
            )

    def _detect_bash(self) -> str:
        """Детектирует наличие bash или sh в системе."""
        candidates = ["/bin/bash", "/usr/bin/bash", "bash", "/bin/sh", "sh"]
        for cand in candidates:
            path = shutil.which(cand)
            if path:
                return path
        return "/bin/sh"

    def _setup_env(self, extra_env: dict[str, str] | None) -> dict[str, str]:
        proc_env = super()._setup_env(extra_env)
        proc_env.setdefault("LANG", "C.UTF-8")
        return proc_env

    def _build_command_args(self, command: str) -> list[str]:
        """Оборачивает команду скриптом фиксации exit-кода и маркера CWD."""
        script = (
            f"{command.strip()}\n"
            "__bridge_exit=$?\n"
            'printf "\\n__BRIDGE_CWD__:%s\\n" "$PWD"\n'
            "exit $__bridge_exit\n"
        )
        return [self.bash_bin, "-c", script]


class PowerShellExecutor(BaseExecutor):
    """
    Движок удалённого выполнения команд PowerShell (pwsh / powershell.exe).
    Обеспечивает принудительную UTF-8 кодировку консоли и отслеживание CWD.
    """

    def __init__(
        self,
        powershell_bin: str | None = None,
        allow_posix_fallback: bool = True,
        dev_logging: bool = True,
    ) -> None:
        super().__init__(dev_logging=dev_logging)
        self.allow_posix_fallback = allow_posix_fallback
        self.powershell_bin = powershell_bin or self._detect_powershell()
        if self.dev_logging:
            logger.info(
                "[POWERSHELL-EXECUTOR] Инициализирован: binary=%s (platform=%s, posix_fallback=%s)",
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
        """Формирует список аргументов запуска PowerShell с гарантией UTF-8 консоли."""
        utf8_init = (
            "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new();\n"
        )
        ps_suffix = (
            "\n$__bridge_exit = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } "
            "elseif (-not $?) { 1 } else { 0 }\n"
            "$__bridge_loc = (Get-Location)\n"
            "$__bridge_cwd = if ($__bridge_loc.Provider.Name -eq 'FileSystem') { "
            "$__bridge_loc.Path } else { $__bridge_loc.ProviderPath }\n"
            'Write-Output "`n__BRIDGE_CWD__:$__bridge_cwd"\n'
            "if ($__bridge_exit -ne 0) { exit $__bridge_exit }\n"
        )
        full_command = utf8_init + command + ps_suffix

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

        if self.allow_posix_fallback and sys.platform != "win32":
            if self.dev_logging:
                logger.debug("[EXECUTOR-MOCK] PowerShell не найден, фоллбэк на /bin/bash")
            bash_script = (
                f"{command.strip()}\n"
                "__bridge_exit=$?\n"
                'echo -e "\\n__BRIDGE_CWD__:$(pwd)"\n'
                "exit $__bridge_exit\n"
            )
            return ["/bin/bash", "-c", bash_script]

        raise FileNotFoundError("PowerShell (powershell.exe или pwsh) не найден в PATH системы")


def create_platform_executor(
    platform: str | None = None,
    dev_logging: bool = True,
) -> BaseExecutor:
    """
    Фабрика создания исполнителя команд под текущую платформу операционной системы.

    Args:
        platform: Явное имя платформы ('win32' или 'linux' / 'darwin').
                  Если None — определяется через sys.platform.
        dev_logging: Включить детальное Dev-Mode логирование.

    Returns:
        Экземпляр BaseExecutor (PowerShellExecutor на Windows, BashExecutor на POSIX).
    """
    plat = platform or sys.platform
    if plat == "win32":
        return PowerShellExecutor(dev_logging=dev_logging)

    return BashExecutor(dev_logging=dev_logging)


__all__ = [
    "BaseExecutor",
    "BashExecutor",
    "PowerShellExecutor",
    "create_platform_executor",
]
