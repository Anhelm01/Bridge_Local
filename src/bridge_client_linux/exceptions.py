"""
bridge_client_linux.exceptions — Иерархия исключений клиента Linux.

Реэкспортирует исключения из bridge_core.exceptions для обратной совместимости.
"""

from __future__ import annotations

from bridge_core.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeRemoteCommandError,
    BridgeTimeoutError,
    format_error_payload,
)

__all__ = [
    "BridgeAuthError",
    "BridgeClientError",
    "BridgeNetworkError",
    "BridgeRemoteCommandError",
    "BridgeTimeoutError",
    "format_error_payload",
]
