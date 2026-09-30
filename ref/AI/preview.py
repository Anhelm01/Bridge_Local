"""
ref/AI/preview.py — Удобный алиас для ref/AI/ascii_preview.py.
Позволяет вызывать:
  uv run python ref/AI/preview.py all 1
  uv run python ref/AI/preview.py all 2
  uv run python ref/AI/preview.py welcome 1
"""

from __future__ import annotations

import runpy
from pathlib import Path

target = Path(__file__).parent / "ascii_preview.py"
runpy.run_path(str(target), run_name="__main__")
