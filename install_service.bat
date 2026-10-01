@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Install Windows Service
echo ========================================================
echo   Bridge Local - Install Background Windows Service (SCM)
echo   Administrator privileges required!
echo ========================================================
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

:: Check administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Administrator rights required!
    echo Right-click install_service.bat and select:
    echo "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/4] Configuring Windows Firewall (Port 9732 TCP)...
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
powershell -NoProfile -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1

if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    echo [2/4] Registering Windows SCM Service...
    "%REPO_ROOT%\dist\bridge-agent.exe" service install
    echo [3/4] Registering Explorer Context Menu...
    "%REPO_ROOT%\dist\bridge-agent.exe" install-context-menu
    echo [4/4] Starting Service...
    "%REPO_ROOT%\dist\bridge-agent.exe" service start
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    echo [2/4] Registering Windows SCM Service...
    "%REPO_ROOT%\bridge-agent.exe" service install
    echo [3/4] Registering Explorer Context Menu...
    "%REPO_ROOT%\bridge-agent.exe" install-context-menu
    echo [4/4] Starting Service...
    "%REPO_ROOT%\bridge-agent.exe" service start
) else (
    set "PY_CMD=python"
    if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PY_CMD=%REPO_ROOT%\.venv\Scripts\python.exe"
    echo [2/4] Registering Windows SCM Service...
    %PY_CMD% -m bridge_agent_win.cli service install
    echo [3/4] Registering Explorer Context Menu...
    %PY_CMD% -m bridge_agent_win.cli install-context-menu
    echo [4/4] Starting Service...
    %PY_CMD% -m bridge_agent_win.cli service start
)
echo.
echo [OK] Service BridgeLocalAgent installed and started successfully!
pause
