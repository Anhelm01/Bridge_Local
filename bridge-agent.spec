# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for building standalone Windows Agent (bridge-agent.exe).

Generates a standalone single-file binary with all dependencies bundled:
  - bridge_core (protocol, framing, transport, storage, notes, logger, security)
  - bridge_agent_win (service, executor, process killer, context menu)
  - pydantic, watchdog, psutil, pywin32
"""

from pathlib import Path
import sys

block_cipher = None

# Base path relative to spec location
spec_root = Path(__file__).resolve().parent if "__file__" in locals() else Path.cwd()
src_dir = spec_root / "src"

datas = [
    (str(spec_root / "bridge.toml"), "."),
] if (spec_root / "bridge.toml").exists() else []

binaries = []
if sys.platform == "win32":
    try:
        from PyInstaller.utils.hooks import collect_dynamic_libs

        binaries.extend(collect_dynamic_libs("win32"))
    except Exception:
        pass

a = Analysis(
    [str(src_dir / "bridge_agent_win" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=binaries,
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
        "bridge_agent_win",
        "bridge_agent_win.cli",
        "bridge_agent_win.context_menu",
        "bridge_agent_win.executor",
        "bridge_agent_win.process_killer",
        "bridge_agent_win.service",
        "bridge_agent_win.tray",
        "bridge_agent_win.monitor",
        "pydantic",
        "psutil",
        "watchdog",
        "watchdog.observers",
        "watchdog.observers.polling",
        "watchdog.observers.read_directory_changes",
        "win32timezone",
        "win32service",
        "win32serviceutil",
        "win32event",
        "servicemanager",
        "win32gui",
        "win32con",
        "win32clipboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "bridge_client_linux",
        "tkinter",
        "matplotlib",
        "pytest",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="bridge-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
