"""
Bridge Agent Windows — серверный агент и служба Windows для Bridge Local.

Экспортирует:
  - WindowsBridgeService: основной сервис-демон (SCM / Standalone runner).
  - PowerShellExecutor: изолированный исполнитель команд PowerShell с UTF-8.
  - kill_process_tree: надежное завершение дерева зависших процессов по таймауту.
"""

from bridge_agent_win.executor import PowerShellExecutor
from bridge_agent_win.process_killer import kill_process_tree
from bridge_agent_win.service import WindowsBridgeService, main_standalone

__version__ = "0.1.0-dev"

__all__ = [
    "PowerShellExecutor",
    "WindowsBridgeService",
    "__version__",
    "kill_process_tree",
    "main_standalone",
]
