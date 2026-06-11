"""System-control tools — files, folders, processes, and PowerShell.

Jarvis manages Vazghen's own machine: create/delete files & folders, list/kill/start
processes, and run PowerShell (optionally **elevated**, which raises a Windows UAC prompt
Vazghen accepts). These are powerful and partly irreversible, so:

* destructive deletes refuse anything under ``settings.system_protected_paths`` or a drive root;
* the persona rule is to **confirm before anything destructive or outward-facing**;
* elevated PowerShell runs in its own UAC-approved window (its stdout isn't captured back).

All handlers return a short speakable string and never raise.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from jarvis.brain.tools.base import clip, tool_error
from jarvis.config import settings


def _enabled() -> bool:
    return settings.system_tools_enabled


def _protected(p: Path) -> bool:
    rp = p.resolve()
    # A drive root (C:\) or anything under a protected system path is off-limits.
    if rp.parent == rp:
        return True
    roots = [r.strip() for r in settings.system_protected_paths.split(",") if r.strip()]
    for root in roots:
        try:
            rootp = Path(root).resolve()
            if rp == rootp or rootp in rp.parents:
                return True
        except OSError:
            continue
    return False


async def file_op(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir (JARVIS_SYSTEM_TOOLS_ENABLED)."
    action = (args.get("action") or "").strip().lower()
    raw = (args.get("path") or "").strip()
    if not raw:
        return "Which path, sir?"
    p = Path(raw).expanduser()
    try:
        if action == "create_folder":
            p.mkdir(parents=True, exist_ok=True)
            return f"Created the folder {p}, sir."
        if action == "create_file":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args.get("content") or "", encoding="utf-8")
            return f"Created the file {p}, sir."
        if action == "delete_file":
            if not p.exists():
                return f"There's no file at {p}, sir."
            if _protected(p):
                return f"I won't delete {p}, sir — it's a protected system path."
            p.unlink()
            return f"Deleted the file {p}, sir."
        if action == "delete_folder":
            if not p.exists():
                return f"There's no folder at {p}, sir."
            if _protected(p):
                return f"I won't delete {p}, sir — it's a protected system path."
            shutil.rmtree(p)
            return f"Deleted the folder {p} and its contents, sir."
        if action == "list":
            if not p.is_dir():
                return f"{p} isn't a folder, sir."
            entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
            return clip(f"{p} contains: " + ", ".join(entries) if entries else f"{p} is empty, sir.", 1500)
        return f"I don't know the file action '{action}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("file operation", e)


async def process_op(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    action = (args.get("action") or "").strip().lower()
    name = (args.get("name") or "").strip()
    pid = args.get("pid")
    command = (args.get("command") or "").strip()
    try:
        if action == "list":
            r = await asyncio.to_thread(
                subprocess.run,
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=20,
            )
            lines = [ln for ln in r.stdout.splitlines() if (not name or name.lower() in ln.lower())]
            return clip(f"{len(lines)} process(es)" + (f" matching '{name}'" if name else "")
                        + ":\n" + "\n".join(lines[:25]), 1800)
        if action == "kill":
            if pid:
                cmd = ["taskkill", "/PID", str(pid), "/T", "/F"]
            elif name:
                cmd = ["taskkill", "/IM", name, "/T", "/F"]
            else:
                return "Tell me the process name or pid to kill, sir."
            r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=20)
            ok = r.returncode == 0
            return (f"Killed {name or pid}, sir." if ok
                    else f"Couldn't kill {name or pid}: {clip(r.stderr or r.stdout, 160)}")
        if action == "start":
            if not command:
                return "What should I start, sir? Give me a command or executable."
            # Detached so it outlives this turn.
            flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0  # DETACHED|NEW_GROUP
            await asyncio.to_thread(
                lambda: subprocess.Popen(command, shell=True, creationflags=flags))
            return f"Started: {clip(command, 120)}, sir."
        return f"I don't know the process action '{action}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("process operation", e)


async def run_powershell(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    command = (args.get("command") or "").strip()
    as_admin = bool(args.get("as_admin"))
    if not command:
        return "What PowerShell command, sir?"
    try:
        if as_admin:
            # Relaunch elevated via UAC. Output goes to its own window (not captured here).
            launcher = (
                f"Start-Process powershell -Verb RunAs -ArgumentList "
                f"'-NoProfile','-Command',{_ps_quote(command)}"
            )
            await asyncio.to_thread(
                subprocess.run,
                ["powershell", "-NoProfile", "-Command", launcher],
                capture_output=True, text=True, timeout=30,
            )
            return ("I launched that as administrator, sir — accept the Windows prompt to let it run. "
                    "(Elevated output runs in its own window.)")
        r = await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, timeout=60,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        return clip(out or "Done, sir — no output.", 1800)
    except Exception as e:  # noqa: BLE001
        return tool_error("PowerShell", e)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "file_op",
            "description": (
                "Create or delete files and folders on Vazghen's PC, or list a folder. "
                "Deleting is irreversible — confirm with him first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create_file", "create_folder", "delete_file", "delete_folder", "list"],
                    },
                    "path": {"type": "string", "description": "Absolute or ~ path."},
                    "content": {"type": "string", "description": "Text for create_file."},
                },
                "required": ["action", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "process_op",
            "description": (
                "Manage processes: list running processes (optionally filtered by name), kill a "
                "process by name or pid, or start a new process/app. Killing apps is disruptive — "
                "confirm first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "kill", "start"]},
                    "name": {"type": "string", "description": "Process image name, e.g. 'chrome.exe'."},
                    "pid": {"type": "integer", "description": "Process id (for kill)."},
                    "command": {"type": "string", "description": "Command/executable to start."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": (
                "Run a PowerShell command on Vazghen's PC and get the output. Set as_admin=true to "
                "run elevated (raises a Windows UAC prompt he must accept). Use for system tasks, "
                "settings, installs. Confirm anything destructive first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The PowerShell command."},
                    "as_admin": {"type": "boolean", "description": "Run elevated (UAC). Default false."},
                },
                "required": ["command"],
            },
        },
    },
]

HANDLERS = {"file_op": file_op, "process_op": process_op, "run_powershell": run_powershell}
