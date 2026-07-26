"""Laptop PC-control executor — gives the 24/7 VPS brain full control of THIS PC.

Run this on the laptop as a background task. It connects OUT to the brain's ``/control`` socket over
Tailscale (no inbound ports) and executes the PC ops the brain forwards: create/delete/edit files &
folders, list/kill/start processes (task-manager), run PowerShell, open the browser / a URL / an app.
So when you tell Watari from your phone "open YouTube on my laptop" or "kill Chrome" or "clean up these
processes", it runs here. The existing system-tool guards still apply (protected paths, Watari's own
secrets). When this isn't running, the brain reports the laptop offline instead of acting on the VPS.

    uv run python -m jarvis.edge.pc_agent
"""

from __future__ import annotations

import asyncio
import json
import platform
import random
from urllib.parse import urlparse, urlunparse

from loguru import logger

from jarvis.brain.tools.system import LOCAL_HANDLERS as _SYS_HANDLERS
from jarvis.brain.tools.camera import LOCAL_HANDLERS as _CAM_HANDLERS

# The laptop executor runs BOTH system ops (files/processes/screenshot) and camera ops (presence/
# enroll/capture) locally — the camera + owner face refs are on this machine, not the VPS brain.
LOCAL_HANDLERS = {**_SYS_HANDLERS, **_CAM_HANDLERS}
from jarvis.config import settings

# Bumped when the executor's behaviour changes, so the brain log confirms which code is live after a
# restart (e.g. the elevated-session PATH / absolute-exe fixes).
CODE_VERSION = "2026-06-14-winexe"


def _control_url() -> str:
    if settings.pc_control_url:
        return settings.pc_control_url
    u = urlparse(settings.brain_ws_url)
    return urlunparse(u._replace(path="/control"))


# Last-line refuse-list for an ELEVATED process. The brain's own guards (system.py path/secret
# checks + confirm tier) run first; this catches a compromised/confused brain anyway. Substring
# match on the flattened command — crude on purpose, these strings have no legitimate use here.
_REFUSED_SUBSTRINGS = (
    "format-volume", "format c:", "format d:", "clear-disk", "initialize-disk",
    "remove-item c:\\ ", "remove-item -path c:\\ ", "rd /s /q c:\\", "del /f /s /q c:\\",
    "cipher /w", "bcdedit", "vssadmin delete", "reg delete hklm", "diskpart",
)


def _refused(op: str, args: dict) -> str | None:
    blob = f"{op} {json.dumps(args, ensure_ascii=False)}".lower()
    for bad in _REFUSED_SUBSTRINGS:
        if bad in blob:
            return bad
    return None


def _proc_running(name: str) -> bool:
    """Is a process with this image name in the task list? Windows tasklist; best-effort."""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"],
                             capture_output=True, text=True, timeout=10).stdout
        return name.lower() in (out or "").lower()
    except Exception:  # noqa: BLE001 — no tasklist / timeout -> can't verify
        return False


def _verify_effect(op: str, args: dict) -> str | None:
    """C5 see→act→VERIFY: after an op runs, confirm the intended effect actually happened, so Watari
    reports "done and verified" (or flags a mismatch) instead of blindly trusting the exit. Returns a
    short note, or None when the op isn't verifiable (open_url/open_app/run_powershell are best-effort —
    there's no reliable post-state to check). ponytail: existence checks + a tasklist probe; the upgrade
    path is per-app window/clipboard assertions if a specific workflow needs them."""
    import os
    if op == "file_op":
        action, path = args.get("action"), args.get("path")
        if action in ("create_file", "create_folder") and path:
            return "verified — it exists now" if os.path.exists(path) else "WARNING: not found after create"
        if action in ("delete_file", "delete_folder") and path:
            return "verified — it's gone" if not os.path.exists(path) else "WARNING: still present after delete"
    if op == "process_op" and args.get("action") == "kill" and args.get("name"):
        return "verified — not running" if not _proc_running(args["name"]) else "WARNING: still running after kill"
    return None


async def _run_op(op: str, args: dict) -> tuple[bool, str]:
    fn = LOCAL_HANDLERS.get(op)
    if fn is None:
        return False, f"unknown PC op '{op}'"
    hit = _refused(op, args)
    if hit:
        logger.warning(f"pc-agent: REFUSED catastrophic op {op} (matched '{hit}')")
        return False, "I won't run that on the laptop — it's on the destructive-op refuse list, sir."
    try:
        out = str(await fn(args or {}))
        note = _verify_effect(op, args or {})   # C5: confirm the effect landed
        if note:
            out = f"{out} ({note})"
            if note.startswith("WARNING"):
                logger.warning(f"pc-agent: {op} verify mismatch — {note}")
        return True, out
    except Exception as e:  # noqa: BLE001
        logger.exception(f"pc-agent: op {op} failed")
        return False, f"That failed on the laptop ({type(e).__name__}), sir."


async def _session(url: str, token: str | None) -> None:
    from websockets.asyncio.client import connect

    headers = {"Authorization": f"Bearer {token}"} if token else None
    # ping_timeout 75s (not 20): a brief network blip on a 24/7 idle link shouldn't drop the
    # control channel. Matches the brain<->edge keepalive; stops the ~15-min reconnect churn.
    async with connect(url, additional_headers=headers, ping_interval=20,
                       ping_timeout=75, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "pc_hello", "host": platform.node(), "ver": CODE_VERSION}))
        logger.info(f"pc-agent: connected to {url} as '{platform.node()}' — ready for commands")
        async for raw in ws:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("type") != "pc_command":
                continue
            op, args, cid = data.get("op"), data.get("args") or {}, data.get("id")
            logger.info(f"pc-agent: exec {op}({args})")
            ok, output = await _run_op(op, args)
            await ws.send(json.dumps({"type": "pc_result", "id": cid, "ok": ok, "output": output}))


def _ensure_windows_path() -> None:
    """A process launched by an elevated Task Scheduler job can start with a minimal PATH that
    lacks System32 — so powershell/tasklist/taskkill/cmd come back FileNotFoundError. Prepend the
    standard Windows system dirs so every forwarded op resolves its executable."""
    if platform.system() != "Windows":
        return
    import os

    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    wanted = [rf"{sysroot}\System32", rf"{sysroot}\System32\WindowsPowerShell\v1.0", sysroot,
              rf"{sysroot}\System32\Wbem"]
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    for d in reversed(wanted):
        if d.lower() not in [p.lower() for p in parts]:
            parts.insert(0, d)
    os.environ["PATH"] = os.pathsep.join(parts)


async def main() -> None:
    _ensure_windows_path()
    url = _control_url()
    token = settings.api_auth_token
    logger.info(f"pc-agent starting → {url}")
    backoff = 1.0
    while True:
        try:
            await _session(url, token)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — any drop -> reconnect with backoff
            logger.warning(f"pc-agent link error ({type(e).__name__}: {e}); reconnecting")
        delay = min(backoff, 30.0) * (0.7 + 0.6 * random.random())
        await asyncio.sleep(delay)
        backoff = min(backoff * 2, 30.0)


if __name__ == "__main__":
    from jarvis.edge._supervisor import run_supervised

    run_supervised("pc_agent", main)
