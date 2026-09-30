"""
Тесты для bridge_agent_win.executor — выполнение команд, таймауты, UTF-8 и кодеки.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bridge_agent_win.executor import PowerShellExecutor
from bridge_core.models import ExecRequestParams, RpcErrorCode
from bridge_core.transport import RpcCallError


class TestPowerShellExecutor:
    """Тесты PowerShellExecutor."""

    @pytest.mark.asyncio
    async def test_execute_simple_echo(self) -> None:
        executor = PowerShellExecutor(allow_posix_fallback=True)
        params = ExecRequestParams(command='echo "Hello Bridge"', timeout_sec=5)

        result = await executor.execute(params)
        assert result.exit_code == 0
        assert "Hello Bridge" in result.stdout
        assert result.duration_ms >= 0
        assert not result.timed_out

    @pytest.mark.asyncio
    async def test_execute_cyrillic_utf8(self) -> None:
        executor = PowerShellExecutor(allow_posix_fallback=True)
        params = ExecRequestParams(command='echo "Привет мир 123"', timeout_sec=5)

        result = await executor.execute(params)
        assert result.exit_code == 0
        assert "Привет мир 123" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_exit_code_propagation(self) -> None:
        executor = PowerShellExecutor(allow_posix_fallback=True)
        params = ExecRequestParams(command="exit 7", timeout_sec=5)

        result = await executor.execute(params)
        assert result.exit_code == 7

    @pytest.mark.asyncio
    async def test_execute_timeout_kills_process(self) -> None:
        """Команда сна на 10 секунд при таймауте 1 сек должна прерываться с ошибкой таймаута."""
        executor = PowerShellExecutor(allow_posix_fallback=True)
        params = ExecRequestParams(command="sleep 10", timeout_sec=1)

        with pytest.raises(RpcCallError) as exc_info:
            await executor.execute(params)

        assert exc_info.value.code == RpcErrorCode.COMMAND_TIMEOUT
        assert "лимит времени" in exc_info.value.message
        assert exc_info.value.data is not None
        assert exc_info.value.data["timeout_sec"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_working_dir(self, tmp_path: Path) -> None:
        executor = PowerShellExecutor(allow_posix_fallback=True)
        params = ExecRequestParams(
            command="pwd",
            working_dir=str(tmp_path),
            timeout_sec=5,
        )

        result = await executor.execute(params)
        assert result.exit_code == 0
        assert str(tmp_path.resolve()) in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_env_variables(self) -> None:
        executor = PowerShellExecutor(allow_posix_fallback=True)
        is_pwsh = bool(shutil.which("powershell") or shutil.which("pwsh"))
        cmd = "Write-Output $env:CUSTOM_VAR" if is_pwsh else "echo $CUSTOM_VAR"
        params = ExecRequestParams(
            command=cmd,
            env={"CUSTOM_VAR": "SUPER_VAL_99"},
            timeout_sec=5,
        )

        result = await executor.execute(params)
        assert result.exit_code == 0
        assert "SUPER_VAL_99" in result.stdout
