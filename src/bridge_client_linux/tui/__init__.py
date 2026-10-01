"""
bridge_client_linux.tui — Терминальный интерфейс (TUI) Bridge Local.

Экспортирует:
  - OFFICIAL_THEME, PaletteTheme
  - BRIDGES_MASTER, DRAWBRIDGE_INDUSTRIAL, DRAWBRIDGE_HEADER
  - render_welcome_screen, render_operational_header, render_current_mode
  - run_interactive_tui, handle_key_action
  - demo_process_animations
"""

from __future__ import annotations

from bridge_client_linux.tui.animations import demo_process_animations
from bridge_client_linux.tui.app import (
    F_KEY_MAP,
    MODES_ORDER,
    PAGE_SIZES,
    handle_key_action,
    handle_scroll_action,
    read_terminal_key,
    run_interactive_tui,
)
from bridge_client_linux.tui.logos import (
    BRIDGES_MASTER,
    DRAWBRIDGE_HEADER,
    DRAWBRIDGE_INDUSTRIAL,
)
from bridge_client_linux.tui.screens import (
    render_config_mode,
    render_current_mode,
    render_dashboard_mode,
    render_dev_mode,
    render_exec_mode,
    render_mode_tabs,
    render_notes_mode,
    render_operational_header,
    render_pocket_mode,
    render_theme_spec,
    render_welcome_screen,
)
from bridge_client_linux.tui.theme import OFFICIAL_THEME, PaletteTheme

__all__ = [
    "BRIDGES_MASTER",
    "DRAWBRIDGE_HEADER",
    "DRAWBRIDGE_INDUSTRIAL",
    "F_KEY_MAP",
    "MODES_ORDER",
    "OFFICIAL_THEME",
    "PAGE_SIZES",
    "PaletteTheme",
    "demo_process_animations",
    "handle_key_action",
    "handle_scroll_action",
    "read_terminal_key",
    "render_config_mode",
    "render_current_mode",
    "render_dashboard_mode",
    "render_dev_mode",
    "render_exec_mode",
    "render_mode_tabs",
    "render_notes_mode",
    "render_operational_header",
    "render_pocket_mode",
    "render_theme_spec",
    "render_welcome_screen",
    "run_interactive_tui",
]
