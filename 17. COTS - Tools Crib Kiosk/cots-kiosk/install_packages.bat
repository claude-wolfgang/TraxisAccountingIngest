@echo off
echo Installing Flask and requests...
echo.

:: Try pip on PATH first
pip install flask requests 2>nul && goto :done

:: If that failed, use the full path to Python 3.8
echo pip not on PATH, trying full path...
"C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\python.exe" -m pip install flask requests

:done
echo.
echo Verifying...
"C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\python.exe" -c "import flask; print('Flask OK:', flask.__version__)"
"C:\Users\Traxis-COTs\AppData\Local\Programs\Python\Python38\python.exe" -c "import requests; print('Requests OK:', requests.__version__)"
echo.
pause
