@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Uninstall Windows Service
echo ========================================================
echo   Bridge Local - Stop and Uninstall Windows Service
echo   Administrator privileges required!
echo ========================================================
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Administrator rights required!
    echo Right-click uninstall_service.bat and select:
    echo "Run as administrator"
    echo.
    pause
    exit /b 1
)

if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    echo [1/3] Stopping service...
    "%REPO_ROOT%\dist\bridge-agent.exe" service stop
    echo [2/3] Removing service...
    "%REPO_ROOT%\dist\bridge-agent.exe" service remove
    echo [3/3] Removing context menu...
    "%REPO_ROOT%\dist\bridge-agent.exe" uninstall-context-menu
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    echo [1/3] Stopping service...
    "%REPO_ROOT%\bridge-agent.exe" service stop
    echo [2/3] Removing service...
    "%REPO_ROOT%\bridge-agent.exe" service remove
    echo [3/3] Removing context menu...
    "%REPO_ROOT%\bridge-agent.exe" uninstall-context-menu
) else (
    set "PY_CMD=python"
    if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PY_CMD=%REPO_ROOT%\.venv\Scripts\python.exe"
    echo [1/3] Stopping service...
    %PY_CMD% -m bridge_agent_win.cli service stop
    echo [2/3] Removing service...
    %PY_CMD% -m bridge_agent_win.cli service remove
    echo [3/3] Removing context menu...
    %PY_CMD% -m bridge_agent_win.cli uninstall-context-menu
)
echo.
echo [OK] Windows Service and Context Menu removed successfully!
pause
