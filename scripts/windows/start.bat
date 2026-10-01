@echo off
@chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Bridge Local - Windows Control Center
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    if exist "%~dp0..\..\bridge.toml" set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

:: Check Administrator Privileges
net session >nul 2>&1
set "IS_ADMIN=0"
if %ERRORLEVEL% EQU 0 set "IS_ADMIN=1"

:menu
cls
echo ==============================================================================
echo                   BRIDGE LOCAL - WINDOWS CONTROL CENTER
echo ==============================================================================
if "!IS_ADMIN!"=="1" (
    echo  Privilege Level: [ADMINISTRATOR] - Full access to SCM and Firewall
) else (
    echo  Privilege Level: [STANDARD USER] - UAC prompt will be requested if needed
)
echo ==============================================================================
echo.
echo   [1] QUICK START (Recommended)
echo       --^> Open port 9732 in Windows Firewall (All profiles)
echo       --^> Register "Send to Pocket" in Windows Explorer context menu
echo       --^> Launch Bridge Local Agent in interactive console
echo.
echo   [2] INSTALL AS BACKGROUND WINDOWS SERVICE (SCM)
echo       --^> Full auto-setup + agent runs silently in background on boot
echo.
echo   [3] Run Agent in Console only (without changing system settings)
echo   [4] Open Firewall Port 9732 TCP (Standalone Firewall Rule)
echo   [5] Install / Update Explorer Context Menu ("Send to Pocket")
echo   [6] Rebuild Executable (dist\bridge-agent.exe via PyInstaller)
echo   [7] Uninstall Windows Service and Context Menu (Full Cleanup)
echo.
echo   [0] Exit
echo.
echo ==============================================================================
set /p "CHOICE=Select an option [default: 1]: "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto :action_quick_start
if "%CHOICE%"=="2" goto :action_install_service
if "%CHOICE%"=="3" goto :action_run_agent
if "%CHOICE%"=="4" goto :action_firewall
if "%CHOICE%"=="5" goto :action_context_menu
if "%CHOICE%"=="6" goto :action_build
if "%CHOICE%"=="7" goto :action_uninstall
if "%CHOICE%"=="0" exit /b 0

echo [WARN] Invalid input, please try again.
timeout /t 2 >nul
goto :menu


:: ============================================================================
:: ACTION 1: Quick Start
:: ============================================================================
:action_quick_start
echo.
echo ==============================================================================
echo   STEP 1/3: Configuring Windows Firewall (Port 9732 TCP)...
echo ==============================================================================
if "!IS_ADMIN!"=="1" (
    call :sub_apply_firewall
) else (
    echo [INFO] Requesting Administrator privileges to open port 9732...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & powershell -NoProfile -Command \"Set-NetConnectionProfile -InterfaceAlias ''Ethernet'' -NetworkCategory Private -ErrorAction SilentlyContinue\"' -Verb RunAs -Wait" 2>nul
    echo [OK] Firewall rule applied.
)

echo.
echo ==============================================================================
echo   STEP 2/3: Registering Explorer Context Menu ("Send to Pocket")...
echo ==============================================================================
call :sub_apply_context_menu

echo.
echo ==============================================================================
echo   STEP 3/3: Launching Bridge Local Agent...
echo ==============================================================================
goto :sub_start_agent_console


:: ============================================================================
:: ACTION 2: Install Windows Service
:: ============================================================================
:action_install_service
if "!IS_ADMIN!"=="0" (
    echo [INFO] Administrator rights required to install Windows Service.
    echo Launching installer with UAC prompt...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%REPO_ROOT%\install_service.bat\"\"' -Verb RunAs"
    exit /b 0
)
call :sub_apply_firewall
call :sub_apply_context_menu
call :sub_exec_agent service install
call :sub_exec_agent service start
echo.
echo [OK] Service BridgeLocalAgent successfully installed and started in background!
pause
goto :menu


:: ============================================================================
:: ACTION 3: Run Agent in Console
:: ============================================================================
:action_run_agent
goto :sub_start_agent_console


:: ============================================================================
:: ACTION 4: Firewall Only
:: ============================================================================
:action_firewall
if "!IS_ADMIN!"=="1" (
    call :sub_apply_firewall
) else (
    echo [INFO] Requesting Administrator rights...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & pause' -Verb RunAs -Wait"
)
pause
goto :menu


:: ============================================================================
:: ACTION 5: Context Menu
:: ============================================================================
:action_context_menu
call :sub_apply_context_menu
pause
goto :menu


:: ============================================================================
:: ACTION 6: Rebuild EXE
:: ============================================================================
:action_build
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\build-windows-agent.ps1"
pause
goto :menu


:: ============================================================================
:: ACTION 7: Uninstall and Clean Up
:: ============================================================================
:action_uninstall
if "!IS_ADMIN!"=="0" (
    echo [INFO] Requesting Administrator rights to uninstall service...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%REPO_ROOT%\uninstall_service.bat\"\"' -Verb RunAs"
    exit /b 0
)
call :sub_exec_agent service stop
call :sub_exec_agent service remove
call :sub_exec_agent uninstall-context-menu
echo.
echo [OK] Service and Context Menu successfully removed.
pause
goto :menu


:: ============================================================================
:: Subroutines
:: ============================================================================

:sub_apply_firewall
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
powershell -NoProfile -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1
echo [OK] Firewall rule for TCP port 9732 created (all profiles).
goto :eof

:sub_apply_context_menu
call :sub_exec_agent install-context-menu
echo [OK] Context menu "Send to Pocket (Bridge Local)" registered in Explorer.
goto :eof

:sub_exec_agent
if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    "%REPO_ROOT%\dist\bridge-agent.exe" %*
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    "%REPO_ROOT%\bridge-agent.exe" %*
) else if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m bridge_agent_win.cli %*
) else (
    python -m bridge_agent_win.cli %*
)
goto :eof

:sub_start_agent_console
echo.
echo [INFO] Starting Bridge Local Agent daemon...
echo [INFO] Press Ctrl+C to stop.
echo.
call :sub_exec_agent run
pause
goto :menu
