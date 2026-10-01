@echo off
title Bridge Local - Сборка автономного bridge-agent.exe
echo ========================================================
echo   Bridge Local - Сборка автономного агента Windows (.exe)
echo ========================================================
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-windows-agent.ps1"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [OK] Сборка успешно завершена!
    echo   Бинарник находится в: dist\bridge-agent.exe
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   [FAIL] Сборка завершилась с ошибкой.
    echo ========================================================
)
pause
