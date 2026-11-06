@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting DEMO mode (no real device)...
echo.
python tools\webtest.py --demo --web-port 8080
pause
