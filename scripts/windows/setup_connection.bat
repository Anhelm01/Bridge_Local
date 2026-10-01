@echo off
title Bridge Local Windows Agent - Setup Connection
cd /d "%~dp0"
echo ========================================================
echo   Bridge Local Windows Agent - Connection Setup Wizard
echo ========================================================
if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" setup
) else (
    python -m bridge_agent_win.cli setup
)
pause
