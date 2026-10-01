@echo off
@chcp 65001 >nul 2>&1
title Bridge Local Windows Agent - Setup Connection
echo ========================================================
echo   Bridge Local Windows Agent - Connection Setup Wizard
echo ========================================================
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    "%REPO_ROOT%\dist\bridge-agent.exe" setup
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    "%REPO_ROOT%\bridge-agent.exe" setup
) else if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m bridge_agent_win.cli setup
) else (
    python -m bridge_agent_win.cli setup
)
pause
