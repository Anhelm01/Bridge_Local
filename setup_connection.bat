@echo off
title Bridge Local Windows Agent - Setup Connection
cd /d "%~dp0"
echo ========================================================
echo   Bridge Local Windows Agent - Connection Setup Wizard
echo ========================================================
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

if exist "%~dp0dist\bridge-agent.exe" (
    "%~dp0dist\bridge-agent.exe" setup
) else if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" setup
) else if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli setup
) else (
    python -m bridge_agent_win.cli setup
)
pause
