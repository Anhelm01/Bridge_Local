@echo off
title Bridge Local - Uninstall Context Menu
echo ========================================================
echo   Удаление пункта «Отправить в Карман» из Проводника
echo ========================================================
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

if exist "%~dp0dist\bridge-agent.exe" (
    "%~dp0dist\bridge-agent.exe" uninstall-context-menu
) else if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" uninstall-context-menu
) else if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli uninstall-context-menu
) else (
    python -m bridge_agent_win.cli uninstall-context-menu
)
echo.
pause
