@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

python -c "import serial" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pyserial is not installed. Run: pip install pyserial
    pause
    exit /b 1
)

rem Open the browser after the server has had time to bind the port.
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8080'"
python tools\webtest.py
pause
