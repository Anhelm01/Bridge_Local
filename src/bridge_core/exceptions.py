"""
bridge_core.exceptions — Иерархия исключений клиента и сервиса Bridge Local.

Все клиентские исключения ассоциированы с детерминированными кодами завершения (ExitCode)
для консистентной обработки в CLI и агентах agy_cli.
"""

from __future__ import annotations

from typing import Any

from bridge_core.exit_codes import ExitCode


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
    """Ошибка выполнения удалённой команды (процесс завершился с ненулевым кодом)."""

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


def format_error_payload(e: Exception) -> tuple[int, dict[str, Any]]:
    """
    Преобразует любое исключение в пару (exit_code, payload_dict)
    для машиночитаемого ответа в режиме --json оператора agy_cli.
    """
    code = int(e.exit_code) if isinstance(e, BridgeClientError) else int(ExitCode.GENERAL_ERROR)

    payload: dict[str, Any] = {
        "status": "error",
        "error_code": code,
        "error_type": type(e).__name__,
        "message": str(e),
    }
    if isinstance(e, BridgeRemoteCommandError):
        payload["cmd_exit_code"] = e.cmd_exit_code
        payload["stdout"] = e.stdout
        payload["stderr"] = e.stderr
    elif isinstance(e, BridgeClientError) and e.details:
        payload["details"] = e.details

    return code, payload

