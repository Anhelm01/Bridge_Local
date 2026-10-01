@echo off
title Bridge Local Windows Agent
echo ========================================================
echo   Bridge Local Windows Agent (Master / Development Mode)
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

:: Проверка наличия скомпилированного бинарника
if exist "%~dp0dist\bridge-agent.exe" (
    echo [INFO] Найден скомпилированный бинарник dist\bridge-agent.exe
    "%~dp0dist\bridge-agent.exe" run
    goto :end
)
if exist "%~dp0bridge-agent.exe" (
    echo [INFO] Найден bridge-agent.exe
    "%~dp0bridge-agent.exe" run
    goto :end
)

:: Запуск через виртуальное окружение .venv (если есть) или глобальный python
if exist "%~dp0.venv\Scripts\python.exe" (
    echo [INFO] Запуск через виртуальное окружение .venv...
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli run
) else (
    echo [INFO] Запуск через системный python...
    python -m bridge_agent_win.cli run
)

:end
pause
