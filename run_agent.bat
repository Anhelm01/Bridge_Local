@echo off
@chcp 65001 >nul 2>&1
title Bridge Local Windows Agent
echo ========================================================
echo   Bridge Local Windows Agent (Master / Development Mode)
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

:: Check for compiled standalone binary
if exist "%~dp0dist\bridge-agent.exe" (
    echo [INFO] Found standalone binary dist\bridge-agent.exe
    "%~dp0dist\bridge-agent.exe" run
    goto :end
)
if exist "%~dp0bridge-agent.exe" (
    echo [INFO] Found bridge-agent.exe
    "%~dp0bridge-agent.exe" run
    goto :end
)

:: Run via Python / .venv
if exist "%~dp0.venv\Scripts\python.exe" (
    echo [INFO] Launching via virtual environment .venv...
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli run
) else (
    echo [INFO] Launching via system python...
    python -m bridge_agent_win.cli run
)

:end
pause
