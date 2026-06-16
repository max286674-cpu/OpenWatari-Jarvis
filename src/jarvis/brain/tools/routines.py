"""Routines & modes — the cheap, non-privileged 'protocols' from the Phase-X expansion.

Two tools:

* ``routine(name, minutes)`` — runs a named behavioural routine: **briefing** (a spoken morning
  brief), **focus**/**lockdown**/**guest**/**commute** (flip a runtime mode), **panic** (go quiet +
  alert the phone), **backup** (archive his memory), **normal** (clear all modes). These are NOT the
  password-gated protocols (goodnight/phoenix/ragnarok) — they change behaviour, not the system, so
  they need no password.
* ``self_health`` — Jarvis reports on his own organs (vault, cache, reminder host).

All degrade gracefully and compose from existing tools, so the briefing simply skips any capability
that isn't configured.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jarvis.brain.modes import MODES
from jarvis.brain.tools.base import tool_error
from jarvis.config import settings

USER_TZ = ZoneInfo("Europe/Berlin")
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _degraded(text: str) -> bool:
    return "isn't configured" in text or "not configured" in text or "couldn't" in text


async def _daily_briefing() -> str:
    """Compose a short spoken brief from time + weather + calendar + headlines (skip what's off)."""
    from jarvis.brain.tools.calendar import list_events
    from jarvis.brain.tools.utility import news_brief, weather

    from jarvis.brain import prefs

    now = datetime.now(USER_TZ)
    parts = [f"Good {('morning' if now.hour < 12 else 'afternoon' if now.hour < 18 else 'evening')}, "
             f"sir. It's {now:%A %H:%M}."]
    home = prefs.home_location()
    if home:
        w = await weather({"location": home})
        if not _degraded(w):
            parts.append(w)
    events = await list_events({"days": 1})
    if not _degraded(events):
        parts.append(events)
    news = await news_brief({})
    if not _degraded(news):
        parts.append(news)
    return " ".join(parts)


async def _backup_memory() -> str:
    """Zip the memory/ dir to backups/ with a timestamp. Returns a spoken confirmation."""
    mem = _REPO_ROOT / "memory"
    if not mem.is_dir():
        return "There's no memory folder to back up yet, sir."
    backups = _REPO_ROOT / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(USER_TZ).strftime("%Y%m%d-%H%M%S")
    base = backups / f"jarvis-memory-{stamp}"
    archive = shutil.make_archive(str(base), "zip", root_dir=str(mem))
    size_kb = Path(archive).stat().st_size // 1024
    return f"Backed up your memory, sir — {Path(archive).name}, about {size_kb} kilobytes."


async def routine(args: dict) -> str:
    name = (args.get("name") or "").strip().lower()
    try:
        minutes = int(args.get("minutes") or 60)
    except (TypeError, ValueError):
        minutes = 60
    try:
        if name in ("briefing", "morning", "brief"):
            return await _daily_briefing()
        if name in ("focus", "deepwork", "deep-work"):
            MODES.set_focus(minutes)
            return f"Focus mode on for {minutes} minutes, sir — I'll hold anything non-urgent."
        if name in ("lockdown", "privacy", "quiet"):
            MODES.lockdown = True
            return "Lockdown engaged, sir — I'll stay quiet and stop volunteering things until you lift it."
        if name == "guest":
            MODES.guest = True
            return "Guest mode on, sir — I'll respond to others too until you switch it off."
        if name == "commute":
            MODES.commute = True
            return "Commute mode on, sir — I'll keep it brief."
        if name in ("panic", "safe"):
            MODES.lockdown = True
            from jarvis.brain.tools.notify import push

            await push("Panic routine triggered.", title="Watari")
            return "Panic routine, sir — I've gone quiet and pinged your phone."
        if name == "backup":
            return await _backup_memory()
        if name in ("normal", "resume", "end", "off", "clear"):
            MODES.clear()
            return "Back to normal, sir — all modes cleared."
        return (f"I don't have a '{name}' routine, sir. I can do: briefing, focus, lockdown, guest, "
                "commute, panic, backup, or normal.")
    except Exception as e:  # noqa: BLE001
        return tool_error("routine", e)


async def set_home_location(args: dict) -> str:
    """Change (or report) Vazghen's current home location — a runtime variable, not a constant."""
    from jarvis.brain import prefs

    loc = (args.get("location") or "").strip()
    if not loc:
        cur = prefs.home_location()
        return (f"Home is currently set to {cur}, sir." if cur
                else "No home location is set yet, sir — where are you based?")
    prefs.set("home_location", loc)
    return f"Done, sir — home is now {loc}. I'll use it for weather and your daily briefing."


async def self_health(args: dict) -> str:
    try:
        from jarvis.brain.health import check, summarize

        snap = await check()
        modes = MODES.status()
        tail = "" if modes == "normal" else f" Current mode: {modes}."
        return summarize(snap) + tail
    except Exception as e:  # noqa: BLE001
        return tool_error("self health", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "routine",
            "description": (
                "Run a named behavioural routine (not a password protocol). Names: 'briefing' (a "
                "short spoken morning brief), 'focus' (hold non-urgent interjections for N minutes), "
                "'lockdown' (go quiet/private), 'guest' (respond to others too), 'commute' (keep it "
                "brief), 'panic' (go quiet and alert his phone), 'backup' (archive your memory), "
                "'normal' (clear all modes)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Routine name."},
                    "minutes": {"type": "integer", "description": "Duration for focus mode (default 60)."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_home_location",
            "description": (
                "Set or report Vazghen's CURRENT home location (a changeable variable — e.g. Cologne "
                "normally, but Armenia or France for a summer). With no location, reports the current "
                "one. This is what 'what's the weather' and the daily briefing default to. Use when he "
                "says 'I'm in X now' / 'set home to X' / 'I'm spending the summer in X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City/place, e.g. 'Yerevan, Armenia'. Omit to report current."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "self_health",
            "description": (
                "Report on your own health — vault readability, cache backend, reminder host — and "
                "your current mode. Use for 'are you all right / status / are you healthy'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

HANDLERS = {"routine": routine, "set_home_location": set_home_location, "self_health": self_health}
