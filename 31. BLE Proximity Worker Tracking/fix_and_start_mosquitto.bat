@echo off
:: Fix duplicate config and start Mosquitto
:: Run as Administrator

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Run as Administrator.
    pause
    exit /b 1
)

set CONF=C:\Program Files\mosquitto\mosquitto.conf
set TEMP_CONF=%TEMP%\mosquitto_fixed.conf

echo Fixing duplicate listener entries...
powershell -Command "(Get-Content '%CONF%') -replace '(?s)listener 1883\r?\nallow_anonymous true\r?\n\r?\nlistener 1883\r?\nallow_anonymous true', 'listener 1883`nallow_anonymous true' | Set-Content '%TEMP_CONF%' -Encoding ASCII"
copy /Y "%TEMP_CONF%" "%CONF%" >nul
echo Fixed.

echo Starting Mosquitto...
net stop mosquitto >nul 2>&1
net start mosquitto
if %errorlevel% equ 0 (
    echo.
    echo Mosquitto running on port 1883.
) else (
    echo Service failed — running directly...
    start "Mosquitto" "C:\Program Files\mosquitto\mosquitto.exe" -c "%CONF%" -v
    timeout /t 2 >nul
)

echo.
echo Testing broker...
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h localhost -t "test" -m "hello" 2>nul
if %errorlevel% equ 0 (
    echo Broker is accepting connections.
) else (
    echo WARNING: Could not publish test message.
)

echo.
echo This PC's IP:
ipconfig | findstr /C:"IPv4"
echo.
echo Configure ESP32 MQTT broker to this IP, port 1883.
pause
