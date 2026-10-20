@echo off
@chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Bridge Local - Windows Control Center

:: Detect Repository / Deployment Root Directory
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%..\..\bridge.toml" (
    set "REPO_ROOT=%SCRIPT_DIR%..\..\"
) else if exist "%SCRIPT_DIR%..\..\bridge.example.toml" (
    set "REPO_ROOT=%SCRIPT_DIR%..\..\"
) else if exist "%SCRIPT_DIR%..\bridge.toml" (
    set "REPO_ROOT=%SCRIPT_DIR%..\"
) else if exist "%SCRIPT_DIR%..\bridge.example.toml" (
    set "REPO_ROOT=%SCRIPT_DIR%..\"
) else (
    set "REPO_ROOT=%SCRIPT_DIR%"
)
cd /d "%REPO_ROOT%"

:: Auto-create bridge.toml from template if missing
if not exist "%REPO_ROOT%bridge.toml" (
    if exist "%REPO_ROOT%bridge.example.toml" (
        copy /y "%REPO_ROOT%bridge.example.toml" "%REPO_ROOT%bridge.toml" >nul 2>&1
    )
)
set "PYTHONPATH=%REPO_ROOT%src;%PYTHONPATH%"

:: Check Administrator Privileges
net session >nul 2>&1
set "IS_ADMIN=0"
if %ERRORLEVEL% EQU 0 set "IS_ADMIN=1"

:: Allow direct action invocation via command line argument (e.g. start.bat 2 or start.bat 12)
if not "%~1"=="" (
    if "%~1"=="1" goto :action_quick_start
    if "%~1"=="2" goto :action_install_service
    if "%~1"=="3" goto :action_run_agent
    if "%~1"=="4" goto :action_stop_agent
    if "%~1"=="5" goto :action_setup_connection
    if "%~1"=="6" goto :action_global_setup
    if "%~1"=="7" goto :action_service_mgmt
    if "%~1"=="8" goto :action_firewall
    if "%~1"=="9" goto :action_context_menu
    if "%~1"=="10" goto :action_tray_menu
    if "%~1"=="11" goto :action_build
    if "%~1"=="12" goto :action_uninstall
    if "%~1"=="13" goto :action_drop_clip
    if /i "%~1"=="clip" goto :action_drop_clip
    if /i "%~1"=="drop" goto :action_drop_clip
)

:menu
cls
echo ==============================================================================
echo                   BRIDGE LOCAL - WINDOWS CONTROL CENTER
echo ==============================================================================
if "!IS_ADMIN!"=="1" (
    echo  Privilege Level: [ADMINISTRATOR] - Full access to SCM, registry, and firewall
) else (
    echo  Privilege Level: [STANDARD USER] - UAC prompt will be requested if needed
)
echo ------------------------------------------------------------------------------
echo  Installation Root: %REPO_ROOT%

:: Check Windows Service Status
sc query "BridgeLocalAgent" 2>nul | findstr /i "RUNNING" >nul
if not errorlevel 1 (
    echo  Service BridgeLocalAgent: [RUNNING]
) else (
    sc query "BridgeLocalAgent" 2>nul | findstr /i "STOPPED" >nul
    if not errorlevel 1 (
        echo  Service BridgeLocalAgent: [STOPPED]
    ) else (
        echo  Service BridgeLocalAgent: [NOT INSTALLED]
    )
)

:: Check Agent Port Status
netstat -ano | findstr /r ":9732 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  Agent Daemon (Port 9732): [ONLINE / LISTENING]
) else (
    echo  Agent Daemon (Port 9732): [STOPPED / OFFLINE]
)

:: Check Firewall Status
netsh advfirewall firewall show rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
if not errorlevel 1 (
    echo  Firewall Port 9732 TCP:   [ALLOWED OK]
) else (
    echo  Firewall Port 9732 TCP:   [NOT CONFIGURED]
)
netsh advfirewall firewall show rule name="Bridge Local Discovery (UDP-In)" >nul 2>&1
if not errorlevel 1 (
    echo  Firewall Port 9735 UDP:   [ALLOWED OK]
) else (
    echo  Firewall Port 9735 UDP:   [NOT CONFIGURED]
)
echo ==============================================================================
echo.
echo   [1] QUICK START (Recommended)
echo       --^> Open ports 9732 TCP and 9735 UDP in Windows Firewall (All profiles)
echo       --^> Register "Send to Pocket" in Windows Explorer context menu
echo       --^> Start Agent daemon in background (Detached, independent from console)
echo       --^> Start System Tray icon near Windows clock
echo.
echo   [2] INSTALL AS BACKGROUND WINDOWS SERVICE (SCM)
echo       --^> Full auto-setup + agent runs silently in background on boot
echo.
echo   [3] Run Agent in Console (Live Monitor and interactive prompt)
echo   [4] Stop Background Agent Daemon
echo   [5] Network and Pocket Configuration Wizard (Port, Token, Pocket path)
echo   [6] Global Windows System Setup (PATH + BRIDGE_CONFIG + C:\BridgeLocal)
echo   [7] Manage Windows Service (SCM: Start / Stop / Restart / Status)
echo   [8] Configure Windows Firewall (Open ports 9732 TCP & 9735 UDP)
echo   [9] Explorer Context Menu Integration ("Send to Pocket")
echo   [10] Windows System Tray and Autostart (shell:startup)
echo   [11] Rebuild Standalone Executable (bridge-agent.exe & bridge-tray.exe)
echo   [12] Uninstall and Clean Up (Service, Menu, Firewall, Autostart)
echo   [13] Drop Clipboard to Pocket (send copied files or text to Pocket)
echo.
echo   [0] Exit
echo.
echo ==============================================================================
set /p "CHOICE=Select an option [default: 1]: "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto :action_quick_start
if "%CHOICE%"=="2" goto :action_install_service
if "%CHOICE%"=="3" goto :action_run_agent
if "%CHOICE%"=="4" goto :action_stop_agent
if "%CHOICE%"=="5" goto :action_setup_connection
if "%CHOICE%"=="6" goto :action_global_setup
if "%CHOICE%"=="7" goto :action_service_mgmt
if "%CHOICE%"=="8" goto :action_firewall
if "%CHOICE%"=="9" goto :action_context_menu
if "%CHOICE%"=="10" goto :action_tray_menu
if "%CHOICE%"=="11" goto :action_build
if "%CHOICE%"=="12" goto :action_uninstall
if "%CHOICE%"=="13" goto :action_drop_clip
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
echo   STEP 1/4: Configuring Windows Firewall (Ports 9732 TCP & 9735 UDP)...
echo ==============================================================================
if "!IS_ADMIN!"=="1" goto :qs_fw_admin
echo [INFO] Requesting Administrator privileges to open ports 9732 TCP and 9735 UDP...
powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & netsh advfirewall firewall delete rule name=\"Bridge Local Discovery (UDP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Discovery (UDP-In)\" dir=in action=allow protocol=UDP localport=9735 profile=any & powershell -NoProfile -Command \"Set-NetConnectionProfile -InterfaceAlias ''Ethernet*'',''Wi-Fi*'' -NetworkCategory Private -ErrorAction SilentlyContinue\"' -Verb RunAs -Wait" 2>nul
echo [OK] Firewall rules applied.
goto :qs_step2

:qs_fw_admin
call :sub_apply_firewall

:qs_step2
echo.
echo ==============================================================================
echo   STEP 2/4: Registering Explorer Context Menu ("Send to Pocket")...
echo ==============================================================================
call :sub_apply_context_menu

echo.
echo ==============================================================================
echo   STEP 3/4: Starting Background Agent Daemon (Detached)...
echo ==============================================================================
call :sub_exec_agent start

echo.
echo ==============================================================================
echo   STEP 4/4: Launching System Tray Icon...
echo ==============================================================================
call :sub_exec_tray

echo.
echo ==============================================================================
echo   [OK] Bridge Local Agent and System Tray are running in background!
echo ==============================================================================
echo   - Daemon is detached: closing this window will NOT terminate the agent.
echo   - System Tray icon is running near the Windows clock.
echo   - Local network port 9732 is listening and LAN UDP 9735 is active.
echo ==============================================================================
pause
goto :menu


:: ============================================================================
:: ACTION 4: Stop Background Agent
:: ============================================================================
:action_stop_agent
echo.
echo [INFO] Stopping Background Agent Daemon...
call :sub_exec_agent stop
pause
goto :menu


:: ============================================================================
:: ACTION 2: Install Windows Service
:: ============================================================================
:action_install_service
if "!IS_ADMIN!"=="0" (
    echo [INFO] Administrator rights required to install Windows Service.
    echo Requesting UAC elevation...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\" 2' -Verb RunAs"
    exit /b 0
)
echo.
echo [1/4] Configuring Windows Firewall...
call :sub_apply_firewall

echo [2/4] Registering Explorer Context Menu...
call :sub_apply_context_menu

echo [3/4] Installing Windows SCM Service...
call :sub_exec_agent service install

echo [4/4] Starting BridgeLocalAgent service...
call :sub_exec_agent service start

echo.
echo [OK] Service BridgeLocalAgent successfully installed and started in background!
echo It will start automatically on Windows boot without any open console window.
pause
goto :menu


:: ============================================================================
:: ACTION 3: Run Agent in Console
:: ============================================================================
:action_run_agent
goto :sub_start_agent_console


:: ============================================================================
:: ACTION 4: Connection & Pocket Setup Wizard
:: ============================================================================
:action_setup_connection
echo.
call :sub_exec_agent setup
pause
goto :menu


:: ============================================================================
:: ACTION 5: Global Windows System Setup (PATH + BRIDGE_CONFIG + C:\BridgeLocal)
:: ============================================================================
:action_global_setup
cls
echo ==============================================================================
echo       GLOBAL WINDOWS SYSTEM SETUP (RUN FROM ANY DRIVE OR DIRECTORY)
echo ==============================================================================
echo.
echo   Current directory: %REPO_ROOT%
echo.
echo   [1] Add current directory to Machine PATH
echo   [2] Set BRIDGE_CONFIG environment variable to %REPO_ROOT%bridge.toml
echo   [3] Deploy standalone files to standard directory C:\BridgeLocal
echo   [4] Complete global setup (1 + 2 + 3)
echo   [0] Back to main menu
echo.
set /p "GCHOICE=Select an option [0-4]: "
if "%GCHOICE%"=="0" goto :menu
if "%GCHOICE%"=="1" goto :gs_opt1
if "%GCHOICE%"=="2" goto :gs_opt2
if "%GCHOICE%"=="3" goto :gs_opt3
if "%GCHOICE%"=="4" goto :gs_opt4
goto :action_global_setup

:gs_opt1
if "!IS_ADMIN!"=="0" goto :gs_elevate
call :sub_add_to_path "%REPO_ROOT%"
pause
goto :action_global_setup

:gs_opt2
if "!IS_ADMIN!"=="0" goto :gs_elevate
call :sub_set_bridge_config "%REPO_ROOT%bridge.toml"
pause
goto :action_global_setup

:gs_opt3
if "!IS_ADMIN!"=="0" goto :gs_elevate
call :sub_deploy_c_bridgelocal
pause
goto :action_global_setup

:gs_opt4
if "!IS_ADMIN!"=="0" goto :gs_elevate
call :sub_deploy_c_bridgelocal
call :sub_add_to_path "C:\BridgeLocal"
call :sub_set_bridge_config "C:\BridgeLocal\bridge.toml"
echo.
echo [OK] Complete global Windows setup finished!
echo The bridge-agent command is now accessible from any CMD or PowerShell prompt.
pause
goto :menu

:gs_elevate
echo.
echo [INFO] Administrator rights required to update machine environment variables.
echo Requesting UAC elevation...
powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\" 6' -Verb RunAs"
goto :menu


:: ============================================================================
:: ACTION 7: Manage Windows Service (SCM)
:: ============================================================================
:action_service_mgmt
cls
echo ==============================================================================
echo             MANAGE WINDOWS SERVICE (SCM: BridgeLocalAgent)
echo ==============================================================================
echo.
sc query "BridgeLocalAgent" 2>nul
echo.
echo   [1] Start service
echo   [2] Stop service
echo   [3] Restart service
echo   [4] Check service status
echo   [5] Remove service from system
echo   [0] Back to main menu
echo.
set /p "SMCHOICE=Select an option [0-5]: "
if "%SMCHOICE%"=="0" goto :menu
if "%SMCHOICE%"=="1" goto :sm_start
if "%SMCHOICE%"=="2" goto :sm_stop
if "%SMCHOICE%"=="3" goto :sm_restart
if "%SMCHOICE%"=="4" goto :sm_status
if "%SMCHOICE%"=="5" goto :sm_remove
goto :action_service_mgmt

:sm_start
if "!IS_ADMIN!"=="0" goto :sm_elevate
call :sub_exec_agent service start
pause
goto :action_service_mgmt

:sm_stop
if "!IS_ADMIN!"=="0" goto :sm_elevate
call :sub_exec_agent service stop
pause
goto :action_service_mgmt

:sm_restart
if "!IS_ADMIN!"=="0" goto :sm_elevate
call :sub_exec_agent service restart
pause
goto :action_service_mgmt

:sm_status
call :sub_exec_agent service status
pause
goto :action_service_mgmt

:sm_remove
if "!IS_ADMIN!"=="0" goto :sm_elevate
call :sub_exec_agent service stop 2>nul
call :sub_exec_agent service remove
pause
goto :action_service_mgmt

:sm_elevate
echo [INFO] Requesting Administrator rights to manage Windows Service...
powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\" 7' -Verb RunAs"
goto :menu


:: ============================================================================
:: ACTION 7: Firewall Configuration
:: ============================================================================
:action_firewall
if "!IS_ADMIN!"=="1" goto :fw_admin
echo [INFO] Requesting Administrator rights to configure Windows Firewall...
powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & netsh advfirewall firewall delete rule name=\"Bridge Local Discovery (UDP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Discovery (UDP-In)\" dir=in action=allow protocol=UDP localport=9735 profile=any & powershell -NoProfile -Command \"Set-NetConnectionProfile -InterfaceAlias ''Ethernet*'',''Wi-Fi*'' -NetworkCategory Private -ErrorAction SilentlyContinue\" & pause' -Verb RunAs -Wait"
goto :fw_done

:fw_admin
call :sub_apply_firewall

:fw_done
pause
goto :menu


:: ============================================================================
:: ACTION 8: Explorer Context Menu
:: ============================================================================
:action_context_menu
call :sub_apply_context_menu
pause
goto :menu


:: ============================================================================
:: ACTION 9: Windows System Tray & Autostart
:: ============================================================================
:action_tray_menu
cls
echo ==============================================================================
echo               WINDOWS SYSTEM TRAY AND AUTOSTART
echo ==============================================================================
echo.
echo   [1] Start System Tray icon now (System Tray)
echo   [2] Add Tray icon to Windows Startup (shell:startup)
echo   [3] Remove Tray icon from Windows Startup
echo   [0] Back to main menu
echo.
set /p "TRCHOICE=Select an option [0-3]: "
if "%TRCHOICE%"=="0" goto :menu
if "%TRCHOICE%"=="1" goto :tr_run_now
if "%TRCHOICE%"=="2" goto :tr_add_startup
if "%TRCHOICE%"=="3" goto :tr_del_startup
goto :action_tray_menu

:tr_run_now
echo [INFO] Starting Bridge Local System Tray...
call :sub_exec_tray
goto :menu

:tr_add_startup
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TRAY_BAT=%REPO_ROOT%scripts\windows\run_tray.bat"
if exist "%REPO_ROOT%run_tray.bat" set "TRAY_BAT=%REPO_ROOT%run_tray.bat"
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\BridgeLocalTray.lnk\"); $vbs = '%REPO_ROOT%scripts\windows\run_hidden.vbs'; $tray = '%TRAY_BAT%'; if (Test-Path $vbs) { $s.TargetPath = 'wscript.exe'; $s.Arguments = \"//nologo `\"$vbs`\" `\"$tray`\"\"; } else { $s.TargetPath = $tray; }; $s.WorkingDirectory = '%REPO_ROOT%'; $s.IconLocation = 'shell32.dll,14'; $s.Save(); Write-Host '[OK] Startup shortcut created in shell:startup'"
pause
goto :action_tray_menu

:tr_del_startup
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BridgeLocalTray.lnk" 2>nul
echo [OK] Startup shortcut removed from Windows Startup.
pause
goto :action_tray_menu


:: ============================================================================
:: ACTION 10: Rebuild Standalone Executable
:: ============================================================================
:action_build
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%scripts\build-windows-agent.ps1"
pause
goto :menu


:: ============================================================================
:: ACTION 12: Uninstall and Clean Up
:: ============================================================================
:action_uninstall
if "!IS_ADMIN!"=="0" (
    echo [INFO] Requesting Administrator rights to uninstall service and clean up...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\" 12' -Verb RunAs"
    exit /b 0
)
echo [1/4] Stopping and removing Windows Service...
call :sub_exec_agent service stop 2>nul
call :sub_exec_agent service remove 2>nul

echo [2/4] Removing Explorer Context Menu...
call :sub_exec_agent uninstall-context-menu 2>nul

echo [3/4] Removing Firewall rules for ports 9732 TCP and 9735 UDP...
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall delete rule name="Bridge Local Discovery (UDP-In)" >nul 2>&1

echo [4/4] Removing Tray icon from Startup...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BridgeLocalTray.lnk" 2>nul

echo.
echo [OK] Service, Context Menu, Firewall rules, and Startup shortcut successfully removed!
pause
goto :menu


:: ============================================================================
:: ACTION 12: Drop Clipboard to Pocket
:: ============================================================================
:action_drop_clip
echo.
echo [INFO] Dropping clipboard contents (files, images, or text) to Pocket...
call :sub_exec_agent drop --clipboard
pause
goto :menu


:: ============================================================================
:: Subroutines
:: ============================================================================

:sub_apply_firewall
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
netsh advfirewall firewall delete rule name="Bridge Local Discovery (UDP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Discovery (UDP-In)" dir=in action=allow protocol=UDP localport=9735 profile=any >nul
powershell -NoProfile -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet*','Wi-Fi*' -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1
echo [OK] Firewall rules for TCP port 9732 and UDP port 9735 created (all profiles).
goto :eof

:sub_apply_context_menu
call :sub_exec_agent install-context-menu
echo [OK] Context menu "Send to Pocket (Bridge Local)" registered in Explorer.
goto :eof

:sub_add_to_path
set "TARGET_DIR=%~1"
powershell -NoProfile -Command "$dir = '%TARGET_DIR%'.TrimEnd('\'); $path = [Environment]::GetEnvironmentVariable('Path', 'Machine'); if ($path -split ';' -notcontains $dir) { [Environment]::SetEnvironmentVariable('Path', $path + ';' + $dir, 'Machine'); Write-Host \"[OK] Directory $dir added to machine PATH\" } else { Write-Host \"[INFO] Directory $dir is already in PATH\" }"
goto :eof

:sub_set_bridge_config
set "TARGET_CFG=%~1"
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('BRIDGE_CONFIG', '%TARGET_CFG%', 'Machine'); Write-Host '[OK] Machine environment variable BRIDGE_CONFIG set to: %TARGET_CFG%'"
goto :eof

:sub_deploy_c_bridgelocal
echo [INFO] Deploying to C:\BridgeLocal...
if not exist "C:\BridgeLocal" mkdir "C:\BridgeLocal"
if not exist "C:\BridgeLocal\pocket" mkdir "C:\BridgeLocal\pocket"
if exist "%REPO_ROOT%dist\bridge-agent.exe" (
    copy /y "%REPO_ROOT%dist\bridge-agent.exe" "C:\BridgeLocal\" >nul
) else if exist "%REPO_ROOT%bridge-agent.exe" (
    copy /y "%REPO_ROOT%bridge-agent.exe" "C:\BridgeLocal\" >nul
)
if exist "%REPO_ROOT%bridge.toml" (
    if not exist "C:\BridgeLocal\bridge.toml" copy "%REPO_ROOT%bridge.toml" "C:\BridgeLocal\" >nul
)
if exist "%REPO_ROOT%start.bat" copy /y "%REPO_ROOT%start.bat" "C:\BridgeLocal\" >nul
if exist "%REPO_ROOT%run_tray.bat" (
    copy /y "%REPO_ROOT%run_tray.bat" "C:\BridgeLocal\" >nul
) else if exist "%REPO_ROOT%scripts\windows\run_tray.bat" (
    copy /y "%REPO_ROOT%scripts\windows\run_tray.bat" "C:\BridgeLocal\" >nul
)
if exist "%REPO_ROOT%scripts\windows\run_hidden.vbs" (
    copy /y "%REPO_ROOT%scripts\windows\run_hidden.vbs" "C:\BridgeLocal\" >nul
)
echo [OK] Files deployed to C:\BridgeLocal.
goto :eof

:sub_exec_agent
if /i "%~1"=="tray" goto :exec_tray
if exist "%REPO_ROOT%dist\bridge-agent.exe" (
    "%REPO_ROOT%dist\bridge-agent.exe" %*
    goto :eof
)
if exist "%REPO_ROOT%bridge-agent.exe" (
    "%REPO_ROOT%bridge-agent.exe" %*
    goto :eof
)
if exist "C:\BridgeLocal\bridge-agent.exe" (
    "C:\BridgeLocal\bridge-agent.exe" %*
    goto :eof
)
if exist "%REPO_ROOT%.venv\Scripts\python.exe" (
    "%REPO_ROOT%.venv\Scripts\python.exe" -m bridge_agent_win.cli %*
    goto :eof
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m bridge_agent_win.cli %*
    goto :eof
)
python -m bridge_agent_win.cli %*
goto :eof

:sub_exec_tray
:exec_tray
if exist "%REPO_ROOT%dist\bridge-tray.exe" (
    start "" "%REPO_ROOT%dist\bridge-tray.exe"
    goto :eof
)
if exist "%REPO_ROOT%dist\bridge-agent.exe" (
    start "" "%REPO_ROOT%dist\bridge-agent.exe" tray
    goto :eof
)
if exist "%REPO_ROOT%.venv\Scripts\pythonw.exe" (
    start "" "%REPO_ROOT%.venv\Scripts\pythonw.exe" -m bridge_agent_win.cli tray
    goto :eof
)
if exist "%REPO_ROOT%.venv\Scripts\python.exe" (
    start "" "%REPO_ROOT%.venv\Scripts\python.exe" -m bridge_agent_win.cli tray
    goto :eof
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw -m bridge_agent_win.cli tray
    goto :eof
)
start "" python -m bridge_agent_win.cli tray 2>nul
goto :eof

:sub_start_agent_console
echo.
echo [INFO] Starting Bridge Local Agent daemon with Live Console Monitor...
echo [INFO] Interactive commands available: 'help', 'status', 'notes', 'clients', 'stop'
echo [INFO] Press Ctrl+C or type 'stop' to terminate.
echo.
call :sub_exec_agent run
pause
goto :menu
