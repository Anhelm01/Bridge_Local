"""
bridge_client_linux.tui — Micro/Mini HUD Bridge Local v0.3.0.

Единственный интерфейс: Micro/Mini HUD (4-5 строк).
"""

from __future__ import annotations

from bridge_client_linux.tui.app import (
    dispatch_omnibar_action,
    dispatch_tui_action,
    probe_target_socket,
    read_terminal_key,
    run_interactive_tui,
)
from bridge_client_linux.tui.screens import (
    format_bytes,
    get_live_context,
    render_current_mode,
    render_mini_hud,
)
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

__all__ = [
    "OFFICIAL_THEME",
    "PaletteTheme",
    "dispatch_omnibar_action",
    "dispatch_tui_action",
    "format_bytes",
    "get_live_context",
    "probe_target_socket",
    "read_terminal_key",
    "render_current_mode",
    "render_mini_hud",
    "run_interactive_tui",
]
