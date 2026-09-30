"""
Unit tests for deterministic CLI exit codes and exception mappings.
Verifies compliance with AGENTS.md Section 6 (AI Operator Protocol).
"""

from __future__ import annotations

from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeRemoteCommandError,
    BridgeTimeoutError,
)
from bridge_client_linux.exit_codes import ExitCode


def test_exit_code_values() -> None:
    """Проверяет значения детерминированных кодов завершения."""
    assert ExitCode.SUCCESS == 0
    assert ExitCode.GENERAL_ERROR == 1
    assert ExitCode.NETWORK_ERROR == 2
    assert ExitCode.AUTH_ERROR == 3
    assert ExitCode.COMMAND_FAILED == 4
    assert ExitCode.TIMEOUT == 5


def test_exception_exit_code_mappings() -> None:
    """Проверяет корректность привязки кодов возврата к классам исключений."""
    assert BridgeClientError("general").exit_code == ExitCode.GENERAL_ERROR
    assert BridgeNetworkError("network").exit_code == ExitCode.NETWORK_ERROR
    assert BridgeAuthError("auth").exit_code == ExitCode.AUTH_ERROR
    assert BridgeRemoteCommandError("fail", exit_code=127).exit_code == ExitCode.COMMAND_FAILED
    assert BridgeTimeoutError("timeout").exit_code == ExitCode.TIMEOUT


def test_remote_command_error_attributes() -> None:
    """Проверяет сохранение stdout, stderr и кода возврата удаленной команды."""
    err = BridgeRemoteCommandError(
        message="Command failed",
        exit_code=1,
        stdout="partial output",
        stderr="error trace",
    )
    assert err.cmd_exit_code == 1
    assert err.stdout == "partial output"
    assert err.stderr == "error trace"
    assert err.exit_code == ExitCode.COMMAND_FAILED
