@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Build Standalone bridge-agent.exe
echo ========================================================
echo   Bridge Local - Build Standalone Windows Agent (.exe)
echo ========================================================
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-windows-agent.ps1"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [OK] Build completed successfully!
    echo   Binary location: dist\bridge-agent.exe
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   [FAIL] Build finished with errors.
    echo ========================================================
)
pause
