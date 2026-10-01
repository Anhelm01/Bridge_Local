"""Точка входа для запуска через python -m bridge_agent_win."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Автоматическое добавление каталога src/ в sys.path для чтения зависимостей через папки
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from bridge_agent_win.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
