' Traxis COTS Crib — Silent Kiosk Launcher
' ==========================================
' Starts the kiosk launcher silently (no console window).
' Put a shortcut to this file in:
'   shell:startup
'
' Or run manually by double-clicking.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve the directory this script lives in
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Find pythonw.exe — try common locations for the current user
userProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")
pythonw = ""

' Try Python 3.8 first (Windows 7 kiosk PC)
If fso.FileExists(userProfile & "\AppData\Local\Programs\Python\Python38\pythonw.exe") Then
    pythonw = userProfile & "\AppData\Local\Programs\Python\Python38\pythonw.exe"
' Then 3.14 (dev machine)
ElseIf fso.FileExists(userProfile & "\AppData\Local\Programs\Python\Python314\pythonw.exe") Then
    pythonw = userProfile & "\AppData\Local\Programs\Python\Python314\pythonw.exe"
' Then 3.13
ElseIf fso.FileExists(userProfile & "\AppData\Local\Programs\Python\Python313\pythonw.exe") Then
    pythonw = userProfile & "\AppData\Local\Programs\Python\Python313\pythonw.exe"
End If

If pythonw = "" Then
    MsgBox "Cannot find pythonw.exe — install Python first." & vbCrLf & vbCrLf & _
           "Looked in:" & vbCrLf & _
           userProfile & "\AppData\Local\Programs\Python\Python38\" & vbCrLf & _
           userProfile & "\AppData\Local\Programs\Python\Python314\" & vbCrLf & _
           userProfile & "\AppData\Local\Programs\Python\Python313\", _
           vbCritical, "Kiosk Launcher"
    WScript.Quit 1
End If

' Launch the kiosk (0 = hidden window, False = don't wait)
WshShell.Run """" & pythonw & """ """ & scriptDir & "\kiosk_launcher.py""", 0, False
