"""
bridge_client_linux.client — Высокоуровневый клиент Bridge Local для Linux.

Реэкспортирует универсальный BridgeClient из bridge_core.client для обратной совместимости.
"""

from __future__ import annotations

from bridge_core.client import BridgeClient

__all__ = ["BridgeClient"]
