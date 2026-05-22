@echo off
rem Silent kiosk launcher used by the scheduled-task autostart.
rem Uses pythonw so no console window appears at logon.
cd /d "%~dp0"

set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=C:\Program Files\Python314\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=C:\Program Files\Python313\pythonw.exe"
rem Kiosk PC (.141) has Python installed at %LOCALAPPDATA%\Python\bin (not the
rem default Programs\Python\ location) — check that before falling back to PATH.
if not exist "%PYTHONW%" set "PYTHONW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"

"%PYTHONW%" kiosk_launcher.py
