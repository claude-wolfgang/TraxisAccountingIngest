@echo off
REM ============================================================================
REM  Install waitress on the .71 Python interpreters
REM  ============================================================================
REM  Required after the Werkzeug -> waitress refactor (Overseer + 9 services).
REM  Without this, services fail with ModuleNotFoundError: waitress on next start.
REM
REM  Double-click on .71 (collector PC) BEFORE restarting Overseer.
REM
REM  .71 has two Python interpreters:
REM    - Main: ...\Programs\Python\Python314\ (used by Overseer + most services)
REM    - Alt:  ...\Local\Python\bin\          (used by AirCompressor)
REM  Both get waitress so any service can call _serve_with_shutdown().
REM ============================================================================

echo.
echo  ============================================
echo   Install waitress on .71 Python interpreters
echo  ============================================
echo.

set "MAIN_PY=C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe"
set "ALT_PY=C:\Users\TRAXIS\AppData\Local\Python\bin\python.exe"

REM --- Main interpreter ---
if exist "%MAIN_PY%" (
    echo  --- Main interpreter
    echo      %MAIN_PY%
    "%MAIN_PY%" -m pip install --upgrade waitress
) else (
    echo  [SKIP] Main Python not found at:
    echo         %MAIN_PY%
)
echo.

REM --- AirCompressor interpreter ---
if exist "%ALT_PY%" (
    echo  --- AirCompressor interpreter
    echo      %ALT_PY%
    "%ALT_PY%" -m pip install --upgrade waitress
) else (
    echo  [SKIP] AirCompressor Python not found at:
    echo         %ALT_PY%
    echo         Likely safe to ignore -- AirCompressor may use the main Python.
)

echo.
echo  ============================================
echo   Done. Next steps:
echo     1. Restart Overseer so services pick up the new code
echo        (e.g. nssm restart TraxisAgent, or kill+respawn manually)
echo     2. Watch http://localhost:8060 -- all services should go green
echo  ============================================
echo.
pause
