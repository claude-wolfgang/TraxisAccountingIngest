Get-CimInstance Win32_Process -Filter "CommandLine like '%print_service%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
Start-Process python -ArgumentList "print_service.py" -WorkingDirectory $PSScriptRoot
