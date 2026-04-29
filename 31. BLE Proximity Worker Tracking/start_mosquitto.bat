@echo off
:: Start Mosquitto + configure for P31 BLE Proximity Test
:: Run as Administrator

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

set CONF=C:\Program Files\mosquitto\mosquitto.conf

:: Add listener config if not present
findstr /x "listener 1883" "%CONF%" >nul 2>&1
if %errorlevel% neq 0 (
    echo.>> "%CONF%"
    echo listener 1883>> "%CONF%"
    echo allow_anonymous true>> "%CONF%"
    echo Added listener 1883 + allow_anonymous to mosquitto.conf
) else (
    echo Config already present.
)

:: Stop and restart
net stop mosquitto >nul 2>&1
net start mosquitto
if %errorlevel% equ 0 (
    echo.
    echo Mosquitto running on port 1883.
    echo Test with: mosquitto_sub -h localhost -t "espresense/#" -v
) else (
    echo.
    echo Service failed. Trying to run directly...
    start "" "C:\Program Files\mosquitto\mosquitto.exe" -c "%CONF%" -v
    echo Mosquitto started in a new window.
)
pause
