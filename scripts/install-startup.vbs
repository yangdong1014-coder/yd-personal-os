' Add startup shortcut via Python (Unicode-safe).
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyScript = scriptDir & "\install_startup.py"

Set shell = CreateObject("WScript.Shell")
cmd = "python """ & pyScript & """"
exitCode = shell.Run(cmd, 1, True)
If exitCode <> 0 Then
    cmd = "py -3 """ & pyScript & """"
    exitCode = shell.Run(cmd, 1, True)
End If
WScript.Quit exitCode