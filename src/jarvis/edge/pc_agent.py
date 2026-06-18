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

from jarvis.brain.tools.system import LOCAL_HANDLERS
from jarvis.config import settings

# Bumped when the executor's behaviour changes, so the brain log confirms which code is live after a
# restart (e.g. the elevated-session PATH / absolute-exe fixes).
CODE_VERSION = "2026-06-14-winexe"


def _control_url() -> str:
    if settings.pc_control_url:
        return settings.pc_control_url
    u = urlparse(settings.brain_ws_url)
    return urlunparse(u._replace(path="/control"))


async def _run_op(op: str, args: dict) -> tuple[bool, str]:
    fn = LOCAL_HANDLERS.get(op)
    if fn is None:
        return False, f"unknown PC op '{op}'"
    try:
        return True, str(await fn(args or {}))
    except Exception as e:  # noqa: BLE001
        logger.exception(f"pc-agent: op {op} failed")
        return False, f"That failed on the laptop ({type(e).__name__}), sir."


async def _session(url: str, token: str | None) -> None:
    from websockets.asyncio.client import connect

    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with connect(url, additional_headers=headers, ping_interval=20,
                       ping_timeout=20, max_size=8 * 1024 * 1024) as ws:
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
