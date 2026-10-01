"""Точка входа для запуска через python -m bridge_agent_win."""

from __future__ import annotations

import contextlib
import sys

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from bridge_agent_win.cli import main

if __name__ == "__main__":
    main()

