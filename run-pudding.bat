@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

rem call keeps control when python is a .bat/.cmd shim (for example pyenv-win).
call python -c "import serial" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pyserial is not installed. Run: pip install pyserial
    pause
    exit /b 1
)

set "PORT="
if not "%~1"=="" set "PORT=%~1"
if defined PORT goto run

for /f "usebackq delims=" %%P in (`call python tools\webtest.py --find-port`) do set "PORT=%%P"
if not defined PORT goto usage
if /i "%PORT%"=="NONE" goto usage
echo   Auto-detected Bluetooth port: %PORT%

:run
call python tools\webtest.py --port %PORT%
goto end

:usage
echo Usage: run-pudding.bat [COMx]
echo.
echo Auto-detect failed. Available serial ports:
call python -c "import serial.tools.list_ports as p;[print(x.device,'|',x.description,'|',x.hwid) for x in p.comports()]"
echo.
echo Pair the PUDDING in Windows first, disconnect the phone app,
echo then run this script again. You can also pass a port manually:
echo   run-pudding.bat COM8

:end
pause
