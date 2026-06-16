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


_REPO_ROOT = Path(__file__).resolve().parents[4]
# Jarvis's OWN secrets/runtime state — a system delete must never touch these (parity with the
# coding tool's _safe_path). Without this, "delete the .env file" or removing the voiceprint/session
# would be allowed because they're not under a Windows system path.
_SENSITIVE_NAMES = {"voiceprint.json", "jarvis_jobs.sqlite"}
_SENSITIVE_SUFFIX = {".session", ".session-journal"}
_SENSITIVE_TOPDIRS = {".git", "audit", "backups", ".jarvis-browser"}


def _enabled() -> bool:
    return settings.system_tools_enabled


def _win_exe(name: str) -> str:
    """Absolute path to a Windows system executable, so it resolves even when the process was
    launched (e.g. by an elevated Task Scheduler job) with a minimal PATH that lacks System32."""
    if sys.platform != "win32":
        return name
    import os

    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    candidates = {
        "powershell": rf"{sysroot}\System32\WindowsPowerShell\v1.0\powershell.exe",
        "tasklist": rf"{sysroot}\System32\tasklist.exe",
        "taskkill": rf"{sysroot}\System32\taskkill.exe",
        "cmd": rf"{sysroot}\System32\cmd.exe",
    }
    p = candidates.get(name)
    return p if (p and os.path.isfile(p)) else name


async def _dispatch(op: str, args: dict, local) -> str:
    """Run a PC op on the laptop executor if one is connected to THIS brain (the VPS case); else run
    it locally (correct when the brain itself runs on the laptop). This is what gives the 24/7 VPS
    brain full control of the laptop's files/processes."""
    from jarvis.brain.pc_link import PC_LINK

    if PC_LINK.active:
        try:
            return await PC_LINK.forward(op, args)
        except Exception as e:  # noqa: BLE001
            return (f"Your laptop didn't respond, sir ({type(e).__name__}) — it may be offline or the "
                    "executor isn't running.")
    return await local(args)


def _sensitive(p: Path) -> bool:
    """True for Jarvis's own credentials/state files (refused by destructive file ops)."""
    name = p.name
    if (name == ".env" or name.startswith(".env")
            or name in _SENSITIVE_NAMES or p.suffix in _SENSITIVE_SUFFIX):
        return True
    try:
        rp = p.resolve()
        if rp == _REPO_ROOT or _REPO_ROOT in rp.parents:
            parts = rp.relative_to(_REPO_ROOT).parts
            if parts and parts[0] in _SENSITIVE_TOPDIRS:
                return True
    except (OSError, ValueError):
        pass
    return False


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


async def _file_op_local(args: dict) -> str:
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
            if _sensitive(p):
                return f"I won't overwrite {p}, sir — that's one of my own credential/state files."
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args.get("content") or "", encoding="utf-8")
            return f"Created the file {p}, sir."
        if action == "delete_file":
            if not p.exists():
                return f"There's no file at {p}, sir."
            if _protected(p):
                return f"I won't delete {p}, sir — it's a protected system path."
            if _sensitive(p):
                return f"I won't delete {p}, sir — that's one of my own credential/state files."
            p.unlink()
            return f"Deleted the file {p}, sir."
        if action == "delete_folder":
            if not p.exists():
                return f"There's no folder at {p}, sir."
            if _protected(p) or _sensitive(p):
                return f"I won't delete {p}, sir — it's protected (system or my own state)."
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


async def _process_op_local(args: dict) -> str:
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
                [_win_exe("tasklist"), "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=20,
            )
            lines = [ln for ln in r.stdout.splitlines() if (not name or name.lower() in ln.lower())]
            return clip(f"{len(lines)} process(es)" + (f" matching '{name}'" if name else "")
                        + ":\n" + "\n".join(lines[:25]), 1800)
        if action == "kill":
            if pid:
                cmd = [_win_exe("taskkill"), "/PID", str(pid), "/T", "/F"]
            elif name:
                cmd = [_win_exe("taskkill"), "/IM", name, "/T", "/F"]
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


async def _run_powershell_local(args: dict) -> str:
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
                [_win_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command", launcher],
                capture_output=True, text=True, timeout=30,
            )
            return ("I launched that as administrator, sir — accept the Windows prompt to let it run. "
                    "(Elevated output runs in its own window.)")
        r = await asyncio.to_thread(
            subprocess.run,
            [_win_exe("powershell"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", command],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        return clip(out or "Done, sir — no output.", 1800)
    except Exception as e:  # noqa: BLE001
        return tool_error("PowerShell", e)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


async def _open_url_local(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    url = (args.get("url") or "").strip()
    if not url:
        return "Which URL, sir?"
    if "://" not in url:
        url = "https://" + url
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
            await asyncio.to_thread(
                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", url], creationflags=flags))
        else:
            await asyncio.to_thread(lambda: subprocess.Popen(["xdg-open", url]))
        return f"Opened {clip(url, 100)} in your browser, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("open url", e)


async def _open_app_local(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    app = (args.get("app") or "").strip()
    if not app:
        return "Which app should I open, sir?"
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200
            await asyncio.to_thread(
                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))
        else:
            await asyncio.to_thread(lambda: subprocess.Popen([app]))
        return f"Launched {clip(app, 80)}, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("open app", e)


# ---- Public handlers: forward to the laptop executor if connected, else run locally -------------
async def file_op(args: dict) -> str:
    return await _dispatch("file_op", args, _file_op_local)


async def process_op(args: dict) -> str:
    return await _dispatch("process_op", args, _process_op_local)


async def run_powershell(args: dict) -> str:
    return await _dispatch("run_powershell", args, _run_powershell_local)


async def open_url(args: dict) -> str:
    return await _dispatch("open_url", args, _open_url_local)


async def open_app(args: dict) -> str:
    return await _dispatch("open_app", args, _open_app_local)


# What the laptop executor (edge/pc_agent.py) runs LOCALLY for each forwarded op (no re-dispatch).
LOCAL_HANDLERS = {
    "file_op": _file_op_local,
    "process_op": _process_op_local,
    "run_powershell": _run_powershell_local,
    "open_url": _open_url_local,
    "open_app": _open_app_local,
}


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
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a URL in Vazghen's default browser on his PC (e.g. open YouTube, a "
                           "website, a search). Use this to 'open the browser' / 'open YouTube'.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The URL or site, e.g. youtube.com"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launch an application or executable on Vazghen's PC by name or path "
                           "(e.g. 'notepad', 'spotify', 'code', 'explorer').",
            "parameters": {
                "type": "object",
                "properties": {"app": {"type": "string", "description": "App name or path to launch."}},
                "required": ["app"],
            },
        },
    },
]

HANDLERS = {
    "file_op": file_op, "process_op": process_op, "run_powershell": run_powershell,
    "open_url": open_url, "open_app": open_app,
}
