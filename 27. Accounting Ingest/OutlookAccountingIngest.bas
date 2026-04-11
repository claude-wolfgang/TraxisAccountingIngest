Attribute VB_Name = "AccountingIngest"
'--------------------------------------------------------------------
' Outlook VBA — Accounting Ingest Queue Buttons
'
' Adds two macros that appear as toolbar buttons:
'   SendToProShop  — saves PDF attachments from selected email,
'                    queues them for ProShop review
'   SendToQBO      — saves PDF attachments from selected email,
'                    queues them as vendor invoices for QBO
'
' Install: Alt+F11 → File → Import File → select this .bas file
' Then: File → Options → Quick Access Toolbar →
'        "Choose commands from: Macros" → add both macros
'--------------------------------------------------------------------

Private Const PYTHON_EXE As String = _
    "C:\Users\Superuser\AppData\Local\Programs\Python\Python314\python.exe"

Private Const SCRIPT_DIR As String = _
    "C:\Users\Superuser\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\27. Accounting Ingest\"

Private Const TEMP_DIR As String = "AccountingIngest"

'====================================================================
' Public macros — these show up in the macro list / QAT picker
'====================================================================

Public Sub SendToProShop()
    QueueAttachments "proshop"
End Sub

Public Sub SendToQBO()
    QueueAttachments "qbo"
End Sub

'====================================================================
' Core logic
'====================================================================

Private Sub QueueAttachments(target As String)
    On Error GoTo ErrHandler

    ' Get selected email
    Dim sel As Selection
    Set sel = Application.ActiveExplorer.Selection

    If sel.Count = 0 Then
        MsgBox "Select an email first.", vbExclamation, "Accounting Ingest"
        Exit Sub
    End If

    ' Only handle mail items
    If sel.Item(1).Class <> olMail Then
        MsgBox "Select an email message (not a meeting or contact).", _
               vbExclamation, "Accounting Ingest"
        Exit Sub
    End If

    Dim mail As MailItem
    Set mail = sel.Item(1)

    If mail.Attachments.Count = 0 Then
        MsgBox "This email has no attachments.", vbExclamation, "Accounting Ingest"
        Exit Sub
    End If

    ' Create temp folder
    Dim tmpPath As String
    tmpPath = Environ("TEMP") & "\" & TEMP_DIR
    If Dir(tmpPath, vbDirectory) = "" Then MkDir tmpPath

    ' Pick the right script
    Dim scriptPath As String
    If target = "proshop" Then
        scriptPath = SCRIPT_DIR & "sendto_proshop.py"
    Else
        scriptPath = SCRIPT_DIR & "sendto_qbo.py"
    End If

    ' Save and queue each PDF attachment
    Dim att As Attachment
    Dim savedFile As String
    Dim queued As Integer
    Dim skipped As Integer
    queued = 0
    skipped = 0

    Dim wsh As Object
    Set wsh = CreateObject("WScript.Shell")

    For Each att In mail.Attachments
        Dim ext As String
        ext = LCase(Right(att.FileName, 4))

        If ext = ".pdf" Or ext = ".PDF" Then
            ' Timestamp prefix to avoid collisions
            savedFile = tmpPath & "\" & Format(Now, "yyyymmdd_hhnnss") & "_" & att.FileName
            att.SaveAsFile savedFile

            ' Run Python script (hidden window)
            Dim cmd As String
            cmd = """" & PYTHON_EXE & """ """ & scriptPath & """ """ & savedFile & """"
            wsh.Run cmd, 0, True  ' 0=hidden, True=wait for completion

            queued = queued + 1
        Else
            skipped = skipped + 1
        End If
    Next att

    Set wsh = Nothing

    ' Report
    Dim targetLabel As String
    If target = "proshop" Then
        targetLabel = "ProShop"
    Else
        targetLabel = "QBO"
    End If

    If queued = 0 Then
        MsgBox "No PDF attachments found in this email." & vbCrLf & _
               skipped & " non-PDF attachment(s) skipped.", _
               vbExclamation, "Accounting Ingest"
    ElseIf queued = 1 Then
        MsgBox "1 PDF queued for " & targetLabel & "." & vbCrLf & _
               "Open the Accounting Ingest app to review.", _
               vbInformation, "Accounting Ingest"
    Else
        MsgBox queued & " PDFs queued for " & targetLabel & "." & vbCrLf & _
               "Open the Accounting Ingest app to review.", _
               vbInformation, "Accounting Ingest"
    End If

    Exit Sub

ErrHandler:
    MsgBox "Error: " & Err.Description, vbCritical, "Accounting Ingest"
End Sub
