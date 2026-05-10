@echo off
echo =====================================================
echo  FOCAS Machine Monitor - Console Mode
echo  Traxis Manufacturing
echo =====================================================
echo.
echo Running in console mode for testing...
echo Press Ctrl+C to stop
echo.

cd /d "%~dp0"
dotnet run

pause
