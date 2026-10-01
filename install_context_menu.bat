@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Install Context Menu
echo ========================================================
echo   Bridge Local - Register "Send to Pocket" Context Menu
echo ========================================================
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    "%REPO_ROOT%\dist\bridge-agent.exe" install-context-menu
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    "%REPO_ROOT%\bridge-agent.exe" install-context-menu
) else if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m bridge_agent_win.cli install-context-menu
) else (
    python -m bridge_agent_win.cli install-context-menu
)
echo.
pause
