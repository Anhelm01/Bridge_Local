"""
bridge_client_linux.exceptions — Иерархия исключений клиента Linux.

Все исключения ассоциированы с детерминированными кодами завершения (ExitCode)
для консистентной обработки в CLI и агентах agy_cli.
"""

from __future__ import annotations

from typing import Any

from bridge_client_linux.exit_codes import ExitCode


class BridgeClientError(Exception):
    """Базовое исключение клиента Bridge Local."""

    exit_code: ExitCode = ExitCode.GENERAL_ERROR

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BridgeNetworkError(BridgeClientError):
    """Ошибка сети (хост недоступен, соединение разорвано, connection refused)."""

    exit_code: ExitCode = ExitCode.NETWORK_ERROR


class BridgeAuthError(BridgeClientError):
    """Ошибка аутентификации (неверный PSK токен, сбой HMAC подписи)."""

    exit_code: ExitCode = ExitCode.AUTH_ERROR


class BridgeRemoteCommandError(BridgeClientError):
    """Ошибка выполнения удалённой команды PowerShell (ненулевой код возврата)."""

    exit_code: ExitCode = ExitCode.COMMAND_FAILED

    def __init__(
        self,
        message: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.cmd_exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class BridgeTimeoutError(BridgeClientError):
    """Превышение допустимого времени ожидания (RPC или команды)."""

    exit_code: ExitCode = ExitCode.TIMEOUT
