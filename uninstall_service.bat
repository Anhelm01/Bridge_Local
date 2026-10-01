@echo off
title Bridge Local - Uninstall Windows Service
echo ========================================================
echo   Остановка и удаление системной службы Bridge Local
echo   Требуются права Администратора!
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Требуются права Администратора!
    echo Кликните правой кнопкой мыши по uninstall_service.bat и выберите:
    echo "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

if exist "%~dp0dist\bridge-agent.exe" (
    echo [1/3] Остановка службы...
    "%~dp0dist\bridge-agent.exe" service stop
    echo [2/3] Удаление службы...
    "%~dp0dist\bridge-agent.exe" service remove
    echo [3/3] Удаление контекстного меню...
    "%~dp0dist\bridge-agent.exe" uninstall-context-menu
) else if exist "%~dp0bridge-agent.exe" (
    echo [1/3] Остановка службы...
    "%~dp0bridge-agent.exe" service stop
    echo [2/3] Удаление службы...
    "%~dp0bridge-agent.exe" service remove
    echo [3/3] Удаление контекстного меню...
    "%~dp0bridge-agent.exe" uninstall-context-menu
) else (
    set "PY_CMD=python"
    if exist "%~dp0.venv\Scripts\python.exe" set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    echo [1/3] Остановка службы...
    %PY_CMD% -m bridge_agent_win.cli service stop
    echo [2/3] Удаление службы...
    %PY_CMD% -m bridge_agent_win.cli service remove
    echo [3/3] Удаление контекстного меню...
    %PY_CMD% -m bridge_agent_win.cli uninstall-context-menu
)
echo.
echo [OK] Служба и контекстное меню удалены!
pause
