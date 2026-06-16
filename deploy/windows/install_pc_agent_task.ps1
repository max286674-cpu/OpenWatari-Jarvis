# Install the WatariPcAgent scheduled task so the laptop PC-control executor auto-starts at logon
# WITH HIGHEST PRIVILEGES (elevated). This is what gives Watari TRUE full control of this PC from the
# 24/7 VPS brain: an elevated executor can kill any process (incl. system), run administrator
# PowerShell with no per-command UAC prompt, and write protected locations.
#
# Run this ONCE, elevated. It self-elevates: if not already admin it relaunches via UAC.

$ErrorActionPreference = 'Stop'

# Self-elevate if needed.
$me = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $me.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host "Re-launching elevated (accept the UAC prompt)..."
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`""
    return
}

$user = "$env:USERDOMAIN\$env:USERNAME"

# Launch the venv pythonw.exe DIRECTLY (no VBS/cmd shim). Task Scheduler then creates the process
# with the task's FULL elevated token — the old wscript->ShellExecute chain handed back a filtered,
# non-elevated token (executor reported NORMAL). pythonw = no console window, so nothing flashes.
$pyw = "C:\Jarvis\.venv\Scripts\pythonw.exe"
$action    = New-ScheduledTaskAction -Execute $pyw -Argument "-m jarvis.edge.pc_agent" -WorkingDirectory "C:\Jarvis"
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
                -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "WatariPcAgent" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

# Remove the old non-elevated Startup launcher so we don't run two executors.
$startupVbs = Join-Path ([Environment]::GetFolderPath('Startup')) "WatariPcAgent.vbs"
if (Test-Path $startupVbs) { Remove-Item $startupVbs -Force }

Write-Host "WatariPcAgent installed (elevated, at logon). (Re)starting it now..."
# Stop any running instance and any stale executor procs, so we relaunch with the latest code.
Stop-ScheduledTask -TaskName "WatariPcAgent" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match 'pc_agent' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName "WatariPcAgent"
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName "WatariPcAgent" | Format-List TaskName,State
Write-Host "Done. Watari now has elevated control of this PC."
