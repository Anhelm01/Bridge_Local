@echo off
title Bridge Local - Install Context Menu
echo ========================================================
echo   Установка пункта «Отправить в Карман» в Проводник
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

if exist "%~dp0dist\bridge-agent.exe" (
    "%~dp0dist\bridge-agent.exe" install-context-menu
) else if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" install-context-menu
) else if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli install-context-menu
) else (
    python -m bridge_agent_win.cli install-context-menu
)
echo.
pause
