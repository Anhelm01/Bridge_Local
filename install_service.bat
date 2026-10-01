@echo off
title Bridge Local - Install Windows Service
echo ========================================================
echo   Установка системной службы Bridge Local (SCM)
echo   Требуются права Администратора!
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

:: Проверка прав администратора
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Скрипт должен быть запущен от имени Администратора!
    echo Кликните правой кнопкой мыши по install_service.bat и выберите:
    echo "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

if exist "%~dp0dist\bridge-agent.exe" (
    echo [1/3] Регистрация службы Windows SCM...
    "%~dp0dist\bridge-agent.exe" service install
    echo [2/3] Установка контекстного меню Проводника...
    "%~dp0dist\bridge-agent.exe" install-context-menu
    echo [3/3] Запуск службы...
    "%~dp0dist\bridge-agent.exe" service start
) else if exist "%~dp0bridge-agent.exe" (
    echo [1/3] Регистрация службы Windows SCM...
    "%~dp0bridge-agent.exe" service install
    echo [2/3] Установка контекстного меню Проводника...
    "%~dp0bridge-agent.exe" install-context-menu
    echo [3/3] Запуск службы...
    "%~dp0bridge-agent.exe" service start
) else (
    set "PY_CMD=python"
    if exist "%~dp0.venv\Scripts\python.exe" set "PY_CMD=%~dp0.venv\Scripts\python.exe"
    echo [1/3] Регистрация службы Windows SCM...
    %PY_CMD% -m bridge_agent_win.cli service install
    echo [2/3] Установка контекстного меню Проводника...
    %PY_CMD% -m bridge_agent_win.cli install-context-menu
    echo [3/3] Запуск службы...
    %PY_CMD% -m bridge_agent_win.cli service start
)
echo.
echo [OK] Служба BridgeLocalAgent успешно установлена и запущена!
pause
