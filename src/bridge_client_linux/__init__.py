"""
bridge_client_linux — Клиентский пакет Bridge Local для Linux.

Включает:
  - BridgeClient: высокоуровневый асинхронный клиент RPC, кармана, заметок и PowerShell.
  - ExitCode: детерминированные коды завершения CLI (0, 1, 2, 3, 4, 5).
  - TUI: терминальный интерфейс и Neofetch-сплэш.
  - CLI: Typer-приложение bridge-cli.
"""

from __future__ import annotations

from bridge_client_linux.cli import run as main
from bridge_client_linux.client import BridgeClient
from bridge_client_linux.exceptions import (
    BridgeAuthError,
    BridgeClientError,
    BridgeNetworkError,
    BridgeRemoteCommandError,
    BridgeTimeoutError,
)
from bridge_client_linux.exit_codes import ExitCode

__version__ = "0.1.0-dev"

__all__ = [
    "BridgeAuthError",
    "BridgeClient",
    "BridgeClientError",
    "BridgeNetworkError",
    "BridgeRemoteCommandError",
    "BridgeTimeoutError",
    "ExitCode",
    "__version__",
    "main",
]
