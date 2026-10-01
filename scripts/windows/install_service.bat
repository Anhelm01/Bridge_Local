@echo off
title Bridge Local - Install Windows Service
cd /d "%~dp0"
echo [1/3] Installing BridgeLocalAgent Windows Service...
if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" service install
    echo [2/3] Installing Explorer Context Menu...
    "%~dp0bridge-agent.exe" install-context-menu
    echo [3/3] Starting Service...
    "%~dp0bridge-agent.exe" service start
) else (
    python -m bridge_agent_win.cli service install
    echo [2/3] Installing Explorer Context Menu...
    python -m bridge_agent_win.cli install-context-menu
    echo [3/3] Starting Service...
    python -m bridge_agent_win.cli service start
)
echo Done!
pause
