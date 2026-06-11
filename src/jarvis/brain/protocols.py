"""Protocols — named, password-gated executable routines (FRIDAY/JARVIS style).

A protocol is a small standalone script Jarvis runs ONLY when given the matching password.
This is the identity gate: Jarvis asks for the password first (persona rule), and the runner
verifies it in constant time before launching anything. The scripts live in
``src/jarvis/protocols/`` and are launched **detached** so they survive Jarvis being killed
(needed for the stop/restart protocols).

The three shipped protocols:
  * ``goodnight`` — stops Jarvis (terminates the running edge process).
  * ``phoenix``   — restarts Jarvis (kills the old process, starts a fresh one).
  * ``ragnarok``  — restarts the laptop.

Passwords come from settings (``JARVIS_PROTOCOL_*_PASSWORD``) — CHANGE the defaults in .env.
"""

from __future__ import annotations

import hmac
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

from jarvis.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_DIR = _REPO_ROOT / "src" / "jarvis" / "protocols"


def _registry() -> dict[str, dict]:
    return {
        "goodnight": {
            "script": "goodnight.py",
            "password": settings.protocol_goodnight_password,
            "spoken": "Goodnight, sir. Powering down.",
            "description": "stops Jarvis",
        },
        "phoenix": {
            "script": "phoenix.py",
            "password": settings.protocol_phoenix_password,
            "spoken": "Rebooting myself, sir. Back in a moment.",
            "description": "restarts Jarvis",
        },
        "ragnarok": {
            "script": "ragnarok.py",
            "password": settings.protocol_ragnarok_password,
            "spoken": "Restarting the machine, sir. Save your work.",
            "description": "restarts the laptop",
        },
    }


def protocol_names() -> list[str]:
    return list(_registry().keys())


def describe_protocols() -> str:
    return "; ".join(f"{n} ({p['description']})" for n, p in _registry().items())


class ProtocolResult:
    def __init__(self, ok: bool, message: str, spoken: str | None = None) -> None:
        self.ok = ok
        self.message = message
        self.spoken = spoken


def run_protocol(name: str, password: str) -> ProtocolResult:
    """Verify the password and, if correct, launch the protocol's detached script."""
    if not settings.protocols_enabled:
        return ProtocolResult(False, "Protocols are disabled, sir.")
    name = (name or "").strip().lower()
    reg = _registry()
    if name not in reg:
        return ProtocolResult(False, f"There's no protocol '{name}', sir. I have: {describe_protocols()}.")
    proto = reg[name]
    if not password:
        return ProtocolResult(False, f"Protocol {name} needs the password, sir.")
    # Constant-time compare so a wrong guess leaks no timing.
    if not hmac.compare_digest(str(password).strip(), str(proto["password"])):
        logger.warning(f"protocol '{name}' refused: bad password")
        return ProtocolResult(False, f"That password is incorrect, sir. Protocol {name} was not run.")

    script = _SCRIPT_DIR / proto["script"]
    if not script.is_file():
        return ProtocolResult(False, f"Protocol script {proto['script']} is missing, sir.")
    try:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        subprocess.Popen(
            [sys.executable, str(script), str(os.getpid()), str(_REPO_ROOT), sys.executable],
            cwd=str(_REPO_ROOT),
            creationflags=flags,
            close_fds=True,
        )
        logger.info(f"protocol '{name}' authorized and launched")
        return ProtocolResult(True, f"Protocol {name} authorized. {proto['description'].capitalize()}.",
                              spoken=proto["spoken"])
    except Exception as e:  # noqa: BLE001
        logger.exception("protocol launch failed")
        return ProtocolResult(False, f"I couldn't launch protocol {name}, sir: {type(e).__name__}.")
