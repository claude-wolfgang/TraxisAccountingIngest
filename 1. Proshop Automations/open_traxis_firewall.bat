@echo off
:: Opens Windows Firewall ports for Traxis services
:: Must be run as Administrator

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click and select "Run as administrator".
    pause
    exit /b 1
)

echo Opening firewall ports for Traxis services...

netsh advfirewall firewall add rule name="Traxis Time Tracker (8050)" dir=in action=allow protocol=TCP localport=8050
netsh advfirewall firewall add rule name="Traxis Overseer (8060)" dir=in action=allow protocol=TCP localport=8060
netsh advfirewall firewall add rule name="Traxis FASData Dashboard (8070)" dir=in action=allow protocol=TCP localport=8070

echo.
echo Done. Firewall rules added for ports 8050, 8060, and 8070.
pause
