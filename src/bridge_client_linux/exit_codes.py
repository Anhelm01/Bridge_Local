"""
bridge_client_linux.exit_codes — Детерминированные коды завершения CLI для ИИ-агентов (agy_cli).

Реэкспортирует ExitCode из bridge_core.exit_codes для обратной совместимости.
"""

from __future__ import annotations

from bridge_core.exit_codes import ExitCode

__all__ = ["ExitCode"]
