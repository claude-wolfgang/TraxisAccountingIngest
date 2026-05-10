@echo off
:: Auto-start label print service on the PT-P700 PC (10.1.1.242)
:: Place a shortcut to this file in: shell:startup
title Print Service - PT-P700
cd /d "%~dp0"
python print_service.py
pause
