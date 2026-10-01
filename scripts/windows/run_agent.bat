@echo off
@chcp 65001 >nul 2>&1
title Bridge Local Windows Agent
echo ========================================================
echo   Bridge Local Windows Agent (Master / Development Mode)
echo ========================================================
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

:: Check for compiled standalone binary
if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    echo [INFO] Found standalone binary dist\bridge-agent.exe
    "%REPO_ROOT%\dist\bridge-agent.exe" run
    goto :end
)
if exist "%REPO_ROOT%\bridge-agent.exe" (
    echo [INFO] Found bridge-agent.exe
    "%REPO_ROOT%\bridge-agent.exe" run
    goto :end
)

:: Run via Python / .venv
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    echo [INFO] Launching via virtual environment .venv...
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m bridge_agent_win.cli run
) else (
    echo [INFO] Launching via system python...
    python -m bridge_agent_win.cli run
)

:end
pause
