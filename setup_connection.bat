@echo off
title Bridge Local Windows Agent - Setup Connection
cd /d "%~dp0"
echo ========================================================
echo   Bridge Local Windows Agent - Connection Setup Wizard
echo ========================================================
python -m bridge_agent_win.cli setup
pause
