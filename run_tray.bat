@echo off
title Bridge Local System Tray
echo ========================================================
echo   Bridge Local System Tray Launcher
echo ========================================================

:: Opredelenie kornya repozitoriya
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%src\bridge_agent_win" (
    set "REPO_ROOT=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%..\src\bridge_agent_win" (
    set "REPO_ROOT=%SCRIPT_DIR%..\"
) else if exist "%SCRIPT_DIR%..\..\src\bridge_agent_win" (
    set "REPO_ROOT=%SCRIPT_DIR%..\..\"
) else (
    set "REPO_ROOT=%SCRIPT_DIR%"
)

cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%src;%PYTHONPATH%"

:: 1. Zapusk cherez .venv v korne repozitoriya
if exist "%REPO_ROOT%.venv\Scripts\pythonw.exe" (
    echo [INFO] Zapusk treya cherez .venv\Scripts\pythonw.exe...
    start "" "%REPO_ROOT%.venv\Scripts\pythonw.exe" -m bridge_agent_win.cli tray
    exit /b 0
)

if exist "%REPO_ROOT%.venv\Scripts\python.exe" (
    echo [INFO] Zapusk treya cherez .venv\Scripts\python.exe...
    start "" "%REPO_ROOT%.venv\Scripts\python.exe" -m bridge_agent_win.cli tray
    exit /b 0
)

:: 2. Proverka dist\bridge-agent.exe
if exist "%REPO_ROOT%dist\bridge-agent.exe" (
    "%REPO_ROOT%dist\bridge-agent.exe" --help 2>&1 | findstr /i "tray" >nul
    if not errorlevel 1 (
        echo [INFO] Zapusk treya cherez dist\bridge-agent.exe...
        start "" "%REPO_ROOT%dist\bridge-agent.exe" tray
        exit /b 0
    )
)

:: 3. Proverka Python v LocalAppData polzovatelya
set "USER_PY=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if exist "%USER_PY%" (
    echo [INFO] Zapusk treya cherez %USER_PY%...
    start "" "%USER_PY%" -m bridge_agent_win.cli tray
    exit /b 0
)
set "USER_PY_C=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%USER_PY_C%" (
    echo [INFO] Zapusk treya cherez %USER_PY_C%...
    start "" "%USER_PY_C%" -m bridge_agent_win.cli tray
    exit /b 0
)

:: 4. Fallback na sistemnyj python v PATH
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw -m bridge_agent_win.cli tray
    exit /b 0
)

start "" python -m bridge_agent_win.cli tray 2>nul
