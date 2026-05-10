@echo off
echo Stopping FocasMonitor...
sc stop FocasMonitor
timeout /t 3 /nobreak >nul
echo Copying files...
xcopy /Y /E "D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\focasmonitor\bin\Release\net10.0\win-x86\publish\*" "C:\FocasMonitor\"
del "C:\FASData\diag_tool.log" 2>nul
echo Starting FocasMonitor...
sc start FocasMonitor
echo Done.
pause
