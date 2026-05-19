@echo off
rem Silent kiosk launcher used by the scheduled-task autostart.
rem Uses pythonw so no console window appears at logon.
cd /d "%~dp0"

set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=C:\Program Files\Python314\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=C:\Program Files\Python313\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"

"%PYTHONW%" kiosk_launcher.py
