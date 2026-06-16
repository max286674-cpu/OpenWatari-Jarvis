# PC control — files, processes, PowerShell, the task manager

How to act as a full task-manager / shell on Vazghen's laptop from the 24/7 VPS brain. The commands
forward over the tailnet to the laptop executor (`edge/pc_agent.py`); when it isn't connected the
ops run wherever the brain runs. The executor runs **elevated**, so you have administrator rights.

## Tools and when to use them
- `process_op` — `list` (task manager: see what's running, optionally filter by name), `kill` (by
  `name` like `chrome.exe` or by `pid`; uses `taskkill /T /F` so it takes child processes too),
  `start` (launch a command/exe detached so it outlives the turn).
- `run_powershell` — arbitrary PowerShell with captured output. `as_admin=true` only matters when the
  executor is NOT already elevated (it normally is). Use for: services, scheduled tasks, installs
  (`winget`/`choco`), registry, network, disk, settings.
- `file_op` — `create_file`/`create_folder`/`delete_file`/`delete_folder`/`list`. Paths may use
  forward slashes (`C:/Users/...`) — cleaner than escaped backslashes.
- `open_url` — open a site/YouTube/search in the default browser. `open_app` — launch an app by name
  (`notepad`, `code`, `explorer`, `spotify`).

## Discipline
- **Confirm before destructive or disruptive acts**: killing a foreground app he's using, deleting
  files/folders, mass-killing, registry/service edits, anything that could lose work. State exactly
  what you'll do, then do it.
- Protected paths and your own secrets (`.env`, `*.session`, `voiceprint.json`, the repo's
  `.git`/`audit`/`backups`) are refused by the delete guard — don't try to route around it.
- "Clean up tasks" = `process_op list`, name the heavy/duplicate user processes, propose which to
  kill, then kill on his OK. Never kill system-critical processes (csrss, wininit, services, lsass).
- Prefer `winget install <id> -e --silent` for installs; report the exit/result succinctly out loud.
- For multi-step shell work, do it in one `run_powershell` script rather than many round-trips.
