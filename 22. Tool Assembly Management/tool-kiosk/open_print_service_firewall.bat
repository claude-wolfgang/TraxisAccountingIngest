@echo off
:: Run as Administrator to open firewall for the label print service (port 5002)
netsh advfirewall firewall add rule name="Tool Kiosk Print Service" dir=in action=allow protocol=TCP localport=5002
echo.
echo Firewall rule added for port 5002.
pause
