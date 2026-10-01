@echo off
setlocal EnableDelayedExpansion
title Bridge Local — Единый мастер запуска и управления Windows
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

:: Определение прав Администратора
net session >nul 2>&1
set "IS_ADMIN=0"
if %ERRORLEVEL% EQU 0 set "IS_ADMIN=1"

:menu
cls
echo ==============================================================================
echo              BRIDGE LOCAL — ЕДИНЫЙ ЦЕНТР УПРАВЛЕНИЯ (WINDOWS)
echo ==============================================================================
echo  Статус прав: !IS_ADMIN!
if "!IS_ADMIN!"=="1" (
    echo  Режим: [АДМИНИСТРАТОР] — полный доступ к службам и брандмауэру
) else (
    echo  Режим: [ПОЛЬЗОВАТЕЛЬ] — для настройки брандмауэра и службы потребуется UAC
)
echo ==============================================================================
echo.
echo   [1] БЫСТРЫЙ СТАРТ ПОД КЛЮЧ (Рекомендуется)
echo       --^> Открывает порт 9732 в Брандмауэре (все профили)
echo       --^> Регистрирует пункт «Отправить в Карман» в Проводнике Windows
echo       --^> Запускает агент Bridge Local в интерактивной консоли
echo.
echo   [2] УСТАНОВКА ПОСТОЯННОЙ ФОНОВОЙ СЛУЖБЫ WINDOWS (SCM)
echo       --^> Полная автонастройка + служба работает в фоне без открытых окон
echo.
echo   [3] Только запустить агент в консоли (без изменения настроек)
echo   [4] Открыть порт 9732 в Брандмауэре Windows (Firewall Rule)
echo   [5] Установить / Обновить меню «Отправить в Карман» в Проводнике
echo   [6] Пересобрать автономный исполняемый файл (bridge-agent.exe)
echo   [7] Удалить службу Windows и пункт из Проводника (Очистка)
echo.
echo   [0] Выход
echo.
echo ==============================================================================
set /p "CHOICE=Выберите действие [по умолчанию: 1]: "
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto :action_quick_start
if "%CHOICE%"=="2" goto :action_install_service
if "%CHOICE%"=="3" goto :action_run_agent
if "%CHOICE%"=="4" goto :action_firewall
if "%CHOICE%"=="5" goto :action_context_menu
if "%CHOICE%"=="6" goto :action_build
if "%CHOICE%"=="7" goto :action_uninstall
if "%CHOICE%"=="0" exit /b 0

echo [WARN] Неверный ввод, повторите попытку.
timeout /t 2 >nul
goto :menu


:: ============================================================================
:: ДЕЙСТВИЕ 1: Быстрый старт под ключ
:: ============================================================================
:action_quick_start
echo.
echo ==============================================================================
echo   ШАГ 1/3: Настройка Брандмауэра Windows (порт 9732 TCP)...
echo ==============================================================================
if "!IS_ADMIN!"=="1" (
    call :sub_apply_firewall
) else (
    echo [INFO] Запрос прав администратора для открытия порта 9732...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & powershell -NoProfile -Command \"Set-NetConnectionProfile -InterfaceAlias ''Ethernet'' -NetworkCategory Private -ErrorAction SilentlyContinue\"' -Verb RunAs -Wait" 2>nul
    echo [OK] Брандмауэр настроен.
)

echo.
echo ==============================================================================
echo   ШАГ 2/3: Регистрация контекстного меню «Отправить в Карман»...
echo ==============================================================================
call :sub_apply_context_menu

echo.
echo ==============================================================================
echo   ШАГ 3/3: Запуск агента Bridge Local...
echo ==============================================================================
goto :sub_start_agent_console


:: ============================================================================
:: ДЕЙСТВИЕ 2: Установка постоянной службы Windows SCM
:: ============================================================================
:action_install_service
if "!IS_ADMIN!"=="0" (
    echo [INFO] Для установки системной службы требуются права Администратора.
    echo Запускаем установщик с запросом UAC...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~dp0install_service.bat\"\"' -Verb RunAs"
    exit /b 0
)
call :sub_apply_firewall
call :sub_apply_context_menu
call :sub_exec_agent service install
call :sub_exec_agent service start
echo.
echo [OK] Системная служба BridgeLocalAgent успешно зарегистрирована и запущена в фоне!
pause
goto :menu


:: ============================================================================
:: ДЕЙСТВИЕ 3: Запуск агента в консоли
:: ============================================================================
:action_run_agent
goto :sub_start_agent_console


:: ============================================================================
:: ДЕЙСТВИЕ 4: Только Брандмауэр
:: ============================================================================
:action_firewall
if "!IS_ADMIN!"=="1" (
    call :sub_apply_firewall
) else (
    echo [INFO] Запрос прав администратора...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall delete rule name=\"Bridge Local Daemon (TCP-In)\" >nul 2>&1 & netsh advfirewall firewall add rule name=\"Bridge Local Daemon (TCP-In)\" dir=in action=allow protocol=TCP localport=9732 profile=any & pause' -Verb RunAs -Wait"
)
pause
goto :menu


:: ============================================================================
:: ДЕЙСТВИЕ 5: Контекстное меню
:: ============================================================================
:action_context_menu
call :sub_apply_context_menu
pause
goto :menu


:: ============================================================================
:: ДЕЙСТВИЕ 6: Пересборка EXE
:: ============================================================================
:action_build
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-windows-agent.ps1"
pause
goto :menu


:: ============================================================================
:: ДЕЙСТВИЕ 7: Удаление службы и очистка
:: ============================================================================
:action_uninstall
if "!IS_ADMIN!"=="0" (
    echo [INFO] Запрос прав администратора для удаления службы...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~dp0uninstall_service.bat\"\"' -Verb RunAs"
    exit /b 0
)
call :sub_exec_agent service stop
call :sub_exec_agent service remove
call :sub_exec_agent uninstall-context-menu
echo.
echo [OK] Служба и контекстное меню успешно удалены.
pause
goto :menu


:: ============================================================================
:: Вспомогательные подпрограммы
:: ============================================================================

:sub_apply_firewall
netsh advfirewall firewall delete rule name="Bridge Local Daemon (TCP-In)" >nul 2>&1
netsh advfirewall firewall add rule name="Bridge Local Daemon (TCP-In)" dir=in action=allow protocol=TCP localport=9732 profile=any >nul
powershell -NoProfile -Command "Set-NetConnectionProfile -InterfaceAlias 'Ethernet' -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1
echo [OK] Правило Брандмауэра для TCP порта 9732 создано (все профили).
goto :eof

:sub_apply_context_menu
call :sub_exec_agent install-context-menu
echo [OK] Пункт меню Проводника «Отправить в Карман (Bridge Local)» зарегистрирован.
goto :eof

:sub_exec_agent
if exist "%~dp0dist\bridge-agent.exe" (
    "%~dp0dist\bridge-agent.exe" %*
) else if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" %*
) else if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m bridge_agent_win.cli %*
) else (
    python -m bridge_agent_win.cli %*
)
goto :eof

:sub_start_agent_console
echo.
echo [INFO] Запуск демона Bridge Local...
echo [INFO] Для остановки нажмите Ctrl+C.
echo.
call :sub_exec_agent run
pause
goto :menu
