@echo off
@chcp 65001 >nul 2>&1
title Bridge Local - Open Port 9732 in Windows Firewall
echo ========================================================
echo   Bridge Local - Allow Port 9732 in Windows Firewall
echo ========================================================
echo.

:: Check Administrator Privileges
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Administrator rights required!
    echo.
    echo Please right-click this file and select:
    echo "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/2] Adding inbound rule for TCP port 9732...
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Port 9732 successfully opened for all profiles (Domain, Private, Public).
) else (
    echo   [FAIL] Failed to add firewall rule via netsh.
)

echo [2/2] Setting Ethernet network profile to Private...
powershell -NoProfile -Command "try { Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private -ErrorAction SilentlyContinue; Write-Host '  [OK] Network profile set to Private.' } catch { Write-Host '  [SKIP] Could not change network profile.' }"

echo.
echo ========================================================
echo   [DONE] Port 9732 is open. Linux can now connect.
echo ========================================================
echo.
pause
