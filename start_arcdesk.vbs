' Arc Desk - SILENT, SHADOW launch (no console, no window, no tray icon).
' Point your Windows Startup shortcut here. Press Ctrl+Alt+J to open the palette.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pyw  = base & "\.venv\Scripts\pythonw.exe"
runpy = base & "\run.py"

If fso.FileExists(pyw) Then
    sh.Run """" & pyw & """ """ & runpy & """ --shadow", 0, False
Else
    ' fall back to system pythonw if the venv is missing
    sh.Run "pythonw """ & runpy & """ --shadow", 0, False
End If
