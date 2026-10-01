# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for building standalone Linux CLI & TUI client (bridge-cli).
"""

from pathlib import Path

spec_root = Path(__file__).resolve().parent if "__file__" in locals() else Path.cwd()
src_dir = spec_root / "src"

datas = [
    (str(spec_root / "bridge.toml"), "."),
] if (spec_root / "bridge.toml").exists() else []

a = Analysis(
    [str(src_dir / "bridge_local" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "bridge_core",
        "bridge_core.codec",
        "bridge_core.config",
        "bridge_core.heartbeat",
        "bridge_core.logger",
        "bridge_core.models",
        "bridge_core.notes",
        "bridge_core.pocket",
        "bridge_core.protocol",
        "bridge_core.retry",
        "bridge_core.security",
        "bridge_core.transport",
        "bridge_client_linux",
        "bridge_client_linux.cli",
        "bridge_client_linux.client",
        "bridge_client_linux.exceptions",
        "bridge_client_linux.exit_codes",
        "bridge_client_linux.tui",
        "bridge_client_linux.tui.app",
        "bridge_client_linux.tui.screens",
        "bridge_client_linux.tui.theme",
        "pydantic",
        "watchdog",
        "watchdog.observers",
        "watchdog.observers.polling",
        "watchdog.observers.inotify",
        "typer",
        "rich",
    ],
    excludes=[
        "bridge_agent_win",
        "tkinter",
        "matplotlib",
        "pytest",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="bridge-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
)
