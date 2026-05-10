@echo off
echo =====================================================
echo FOCAS Connection Test - Traxis Manufacturing
echo =====================================================
echo.

if "%1"=="" (
    echo Usage: test.bat [IP_ADDRESS]
    echo.
    echo Example: test.bat 192.168.1.100
    echo.
    echo Or edit Program.cs line 15 to set default IP
    echo then run: test.bat
    echo.
    pause
    exit /b
)

echo Testing connection to %1...
echo.
dotnet run %1

pause
