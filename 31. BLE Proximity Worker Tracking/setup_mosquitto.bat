@echo off
:: ESP32 Proximity Test — Mosquitto Setup
:: Run as Administrator (right-click → Run as administrator)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click the .bat file and select "Run as administrator"
    pause
    exit /b 1
)

echo ============================================================
echo   P31 BLE Proximity — Mosquitto + Driver Setup
echo ============================================================
echo.

:: Step 1: Check for CP2102 driver
echo [1/4] Checking CP2102 USB driver...
pnputil /enum-devices /problem | findstr /i "CP210" >nul 2>&1
if %errorlevel% equ 0 (
    echo   WARNING: CP2102 device found but driver not working.
    echo   Opening Device Manager — find the CP2102 under "Other devices",
    echo   right-click → Update driver → Search automatically.
    echo.
    devmgmt.msc
    echo   Press any key after you've updated the driver...
    pause >nul
) else (
    echo   CP2102 driver looks OK.
)
echo.

:: Step 2: Install Mosquitto
echo [2/4] Installing Mosquitto MQTT broker...
set INSTALLER=%USERPROFILE%\Downloads\mosquitto-2.1.2-install-windows-x64.exe
if exist "%INSTALLER%" (
    echo   Running installer — use defaults, click through...
    start /wait "" "%INSTALLER%"
    echo   Installer finished.
) else (
    echo   Installer not found at %INSTALLER%
    echo   Checking if Mosquitto is already installed...
    if exist "C:\Program Files\mosquitto\mosquitto.exe" (
        echo   Mosquitto already installed.
    ) else (
        echo   ERROR: Download Mosquitto first from https://mosquitto.org/download/
        pause
        exit /b 1
    )
)
echo.

:: Step 3: Configure Mosquitto for local connections
echo [3/4] Configuring Mosquitto...
set CONF=C:\Program Files\mosquitto\mosquitto.conf
if exist "%CONF%" (
    findstr /c:"listener 1883" "%CONF%" >nul 2>&1
    if %errorlevel% neq 0 (
        echo. >> "%CONF%"
        echo # P31 BLE Proximity — allow local connections >> "%CONF%"
        echo listener 1883 >> "%CONF%"
        echo allow_anonymous true >> "%CONF%"
        echo   Added listener config to mosquitto.conf
    ) else (
        echo   Config already has listener 1883 — skipping.
    )
) else (
    echo   ERROR: mosquitto.conf not found. Is Mosquitto installed?
    pause
    exit /b 1
)
echo.

:: Step 4: Restart Mosquitto service
echo [4/4] Restarting Mosquitto service...
net stop mosquitto >nul 2>&1
net start mosquitto
if %errorlevel% equ 0 (
    echo   Mosquitto running on port 1883.
) else (
    echo   WARNING: Could not start Mosquitto service.
    echo   Try starting it manually: net start mosquitto
)
echo.

:: Summary
echo ============================================================
echo   Setup complete. Next steps:
echo.
echo   1. Check Device Manager for the ESP32 COM port number
echo   2. Open Chrome → https://espresense.com/firmware
echo      Select "esp32", connect to the COM port, flash
echo   3. Connect to ESPresense Wi-Fi hotspot, configure:
echo      - Your shop Wi-Fi SSID/password
echo      - MQTT broker: this PC's IP address, port 1883
echo      - Room name: test-bench
echo   4. Run:  python esp32_proximity_test.py
echo ============================================================
pause
