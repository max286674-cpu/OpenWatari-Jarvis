' Watari PC-control executor — hidden launcher (no console window).
' Connects this laptop OUT to the 24/7 VPS brain's /control socket so Watari can run
' file/process/PowerShell/open-app/open-URL commands here. Started at logon by the
' WatariPcAgent scheduled task. Window style 0 = hidden, so nothing flashes on screen.
' Call the venv Python DIRECTLY (not `uv run`) — no per-launch dependency resolution, so it starts
' reliably in the elevated scheduled-task context.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Jarvis"
sh.Run "cmd /c ""C:\Jarvis\.venv\Scripts\python.exe"" -m jarvis.edge.pc_agent", 0, False
