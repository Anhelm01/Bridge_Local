@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Build Standalone bridge-agent.exe
echo ========================================================
echo   Bridge Local - Build Standalone Windows Agent (.exe)
echo ========================================================
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%..\..\scripts\build-windows-agent.ps1" (
    set "PS_SCRIPT=%SCRIPT_DIR%..\..\scripts\build-windows-agent.ps1"
) else if exist "%SCRIPT_DIR%..\build-windows-agent.ps1" (
    set "PS_SCRIPT=%SCRIPT_DIR%..\build-windows-agent.ps1"
) else if exist "%SCRIPT_DIR%scripts\build-windows-agent.ps1" (
    set "PS_SCRIPT=%SCRIPT_DIR%scripts\build-windows-agent.ps1"
) else (
    set "PS_SCRIPT=%SCRIPT_DIR%build-windows-agent.ps1"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
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
