@echo off
setlocal
set "REPO_ROOT=%~dp0"
if not exist "%REPO_ROOT%\bridge.toml" (
    set "REPO_ROOT=%~dp0..\.."
)
cd /d "%REPO_ROOT%"
set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"

if "%~1"=="" (
    echo [ERROR] Укажите путь к файлу для отправки в Карман.
    pause
    exit /b 1
)

if exist "%REPO_ROOT%\dist\bridge-agent.exe" (
    "%REPO_ROOT%\dist\bridge-agent.exe" drop "%~1"
) else if exist "%REPO_ROOT%\bridge-agent.exe" (
    "%REPO_ROOT%\bridge-agent.exe" drop "%~1"
) else if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m bridge_agent_win.cli drop "%~1"
) else (
    python -m bridge_agent_win.cli drop "%~1"
)
