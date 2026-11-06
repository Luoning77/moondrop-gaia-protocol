@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" goto usage
python tools\webtest.py --port %~1
goto end

:usage
echo Usage: run-pudding.bat COM4
echo.
echo Available serial ports:
python -c "import serial.tools.list_ports as p;[print(x.device,'|',x.description,'|',x.hwid) for x in p.comports()]"
echo.
echo Pair the PUDDING in Windows first, then use the COM port named
echo "Standard Serial over Bluetooth link". Disconnect the phone app.

:end
pause
