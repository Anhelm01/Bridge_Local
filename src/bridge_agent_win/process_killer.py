"""
bridge_agent_win.process_killer — Надежное уничтожение дерева процессов (Process Tree Killer).

Реэкспортирует кроссплатформенный kill_process_tree из bridge_core.process_killer
для обратной совместимости.
"""

from __future__ import annotations

from bridge_core.process_killer import kill_process_tree

__all__ = ["kill_process_tree"]
