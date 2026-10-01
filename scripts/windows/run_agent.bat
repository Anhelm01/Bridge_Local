@echo off
title Bridge Local Windows Agent
echo ========================================================
echo   Bridge Local Windows Agent (Standalone Console Mode)
echo ========================================================
cd /d "%~dp0"
if exist "%~dp0bridge-agent.exe" (
    "%~dp0bridge-agent.exe" run
) else (
    python -m bridge_agent_win.cli run
)
pause
