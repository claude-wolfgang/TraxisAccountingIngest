@echo off
echo Fixing Python PATH...

set PYPATH=C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38
set PYSCRIPTS=C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\Scripts

if exist "%PYPATH%\python.exe" (
    echo Found Python at %PYPATH%
    setx PATH "%PATH%;%PYPATH%;%PYSCRIPTS%"
    echo.
    echo PATH updated. Close and reopen Command Prompt, then run:
    echo   python --version
) else (
    echo Python not found at expected path.
    echo Searching...
    dir C:\Users\Traxis-COTs\AppData\Local\Programs\Python\
    echo.
    echo Edit this bat file with the correct folder name above and run again.
)
pause
