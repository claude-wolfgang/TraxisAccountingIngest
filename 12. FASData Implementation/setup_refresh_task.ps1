$action = New-ScheduledTaskAction `
    -Execute 'C:\Users\TRAXIS\AppData\Local\Programs\Python\Python314\python.exe' `
    -Argument '"D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\12. FASData Implementation\generate_report.py"'

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName 'FASData Report Refresh' `
    -Action $action `
    -Trigger $trigger `
    -Description 'Regenerate FASData utilization report and HTML dashboard every 5 minutes' `
    -Force

Write-Host "Scheduled task 'FASData Report Refresh' created successfully."
