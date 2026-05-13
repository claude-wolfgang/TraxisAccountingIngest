@echo off
:: Install Python dependencies for print_service.py
:: Run once on the PT-P700 PC (10.1.1.242) after pulling Phase A refactor.
:: Adds waitress (production WSGI server) plus flask and requests.
title Install Print Service Deps
cd /d "%~dp0"
echo Installing from requirements.txt ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Done. Now run start_print_service.bat to launch the service.
pause
