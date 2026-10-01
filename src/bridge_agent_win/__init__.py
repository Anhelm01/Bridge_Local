"""
Bridge Agent Windows — серверный агент и служба Windows для Bridge Local.

Экспортирует:
  - WindowsBridgeService: основной сервис-демон (SCM / Standalone runner).
  - PowerShellExecutor: изолированный исполнитель команд PowerShell с UTF-8.
  - kill_process_tree: надежное завершение дерева зависших процессов по таймауту.
"""

import sys
from pathlib import Path

# Автоматическое добавление каталога src/ в sys.path для чтения зависимостей через папки
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from bridge_agent_win.executor import PowerShellExecutor  # noqa: E402
from bridge_agent_win.process_killer import kill_process_tree  # noqa: E402
from bridge_agent_win.service import WindowsBridgeService, main_standalone  # noqa: E402

__version__ = "0.1.0-dev"

__all__ = [
    "PowerShellExecutor",
    "WindowsBridgeService",
    "__version__",
    "kill_process_tree",
    "main_standalone",
]
