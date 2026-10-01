@echo off
title Bridge Local - Uninstall Windows Service
cd /d "%~dp0"
echo [1/3] Stopping Service...
if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" service stop
    echo [2/3] Removing Service...
    "%~dp0bridge-agent.exe" service remove
    echo [3/3] Removing Context Menu...
    "%~dp0bridge-agent.exe" uninstall-context-menu
) else (
    python -m bridge_agent_win.cli service stop
    echo [2/3] Removing Service...
    python -m bridge_agent_win.cli service remove
    echo [3/3] Removing Context Menu...
    python -m bridge_agent_win.cli uninstall-context-menu
)
echo Done!
pause
