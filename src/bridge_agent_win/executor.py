"""
bridge_agent_win.executor — Исполнитель команд PowerShell на стороне агента Windows.

Реэкспортирует PowerShellExecutor из bridge_core.executor для полной обратной
совместимости со всеми импортами в bridge_agent_win и тестах.
"""

from __future__ import annotations

from bridge_core.executor import PowerShellExecutor

__all__ = ["PowerShellExecutor"]
