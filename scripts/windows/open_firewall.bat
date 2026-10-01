@echo off
title Bridge Local - Открытие порта 9732 в Брандмауэре Windows
echo ========================================================
echo   Bridge Local - Разрешение порта 9732 в Брандмауэре
echo ========================================================
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Требуются права Администратора!
    echo.
    echo Пожалуйста, кликните правой кнопкой мыши по этому файлу
    echo и выберите: "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

echo [1/2] Добавление входящего правила для порта 9732 TCP...
netsh advfirewall firewall delete rule name="Bridge Local (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Порт 9732 успешно открыт для всех профилей (Public, Private).
) else (
    echo   [FAIL] Не удалось добавить правило через netsh.
)

echo [2/2] Переключение профиля сети Ethernet в Private (Частная)...
powershell -NoProfile -Command "try { Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private -ErrorAction SilentlyContinue; Write-Host '  [OK] Сеть Ethernet переведена в доверенный режим Private.' } catch { Write-Host '  [SKIP] Не удалось сменить профиль сети.' }"

echo.
echo ========================================================
echo   [ГОТОВО] Порт 9732 открыт! Теперь Linux сможет подключиться.
echo ========================================================
echo.
pause
