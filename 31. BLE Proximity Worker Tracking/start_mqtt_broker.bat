@echo off
:: Start Mosquitto with clean minimal config — no admin needed
:: Runs in foreground so you can see ESP32 connections

echo ============================================================
echo   P31 — Starting MQTT Broker (Mosquitto)
echo   Port 1883 — press Ctrl+C to stop
echo ============================================================
echo.

"C:\Program Files\mosquitto\mosquitto.exe" -c "%~dp0mosquitto_clean.conf" -v
pause
