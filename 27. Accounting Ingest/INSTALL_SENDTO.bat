@echo off
REM Install "Send To" right-click menu entries for ProShop and QBO queuing
REM Creates .bat shortcuts in %APPDATA%\Microsoft\Windows\SendTo\

set SCRIPT_DIR=%~dp0
set SENDTO=%APPDATA%\Microsoft\Windows\SendTo
set PYTHON=C:\Users\Superuser\AppData\Local\Programs\Python\Python314\python.exe

echo Creating Send To shortcuts...

(
echo @echo off
echo "%PYTHON%" "%SCRIPT_DIR%sendto_proshop.py" %%*
echo pause
) > "%SENDTO%\ProShop Queue.bat"

(
echo @echo off
echo "%PYTHON%" "%SCRIPT_DIR%sendto_qbo.py" %%*
echo pause
) > "%SENDTO%\QBO Queue.bat"

echo.
echo Done! Right-click any PDF and look under "Send To" for:
echo   - ProShop Queue
echo   - QBO Queue
echo.
pause
