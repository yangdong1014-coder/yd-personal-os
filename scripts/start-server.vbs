' Desktop launcher: start server in background (no console), open browser, then exit.
' Closing this script does NOT stop the server. Use stop-server.bat to stop.

Option Explicit

Dim fso, shell, scriptDir, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\start-server.bat"

If Not fso.FileExists(batPath) Then
    MsgBox "找不到启动脚本: " & batPath, vbCritical, "个人能力操作系统"
    WScript.Quit 1
End If

' WindowStyle 0 = hidden; WaitOnReturn False = do not block on bat exit
shell.Run """" & batPath & """ launch", 0, False