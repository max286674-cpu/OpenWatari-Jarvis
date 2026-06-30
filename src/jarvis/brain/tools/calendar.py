"""Google Calendar tools — list and create events (Phase 11).

Same Google OAuth app as Gmail (``brain/google.py``). ``list_events`` is the backbone of the
proactive engine ("you have a standup in 10 minutes"); ``create_event`` is confirm-gated. Times are
ISO-8601; the brain's timezone is the owner's configured timezone. Degrades to a spoken note until login.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jarvis.brain.google import api_get, api_post, configured
from jarvis.brain.tools.base import not_configured, tool_error
from jarvis.config import settings

_CAL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_NEEDS = "your Google login — run bench/google_login.py once (JARVIS_GOOGLE_* keys)"


def _fmt_when(ev: dict) -> str:
    start = ev.get("start", {})
    when = start.get("dateTime") or start.get("date") or ""
    return when.replace("T", " at ")[:16] if when else "sometime"


async def list_events(args: dict) -> str:
    if not configured():
        return not_configured("Google Calendar", _NEEDS)
    try:
        days = int(args.get("days") or 1)
    except (TypeError, ValueError):
        days = 1
    try:
        max_n = int(args.get("max") or 10)
    except (TypeError, ValueError):
        max_n = 10
    now = datetime.now(timezone.utc)
    try:
        data = await api_get(
            _CAL,
            params={
                "timeMin": now.isoformat(),
                "timeMax": (now + timedelta(days=days)).isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max_n,
            },
        )
        events = data.get("items") or []
        if not events:
            window = "today" if days <= 1 else f"the next {days} days"
            return f"Nothing on your calendar for {window}, sir."
        parts = [f"{ev.get('summary', '(busy)')} {_fmt_when(ev)}" for ev in events[:max_n]]
        return f"You have {len(parts)} event(s), sir: " + "; ".join(parts)
    except Exception as e:  # noqa: BLE001
        return tool_error("calendar read", e)


async def create_event(args: dict) -> str:
    if not configured():
        return not_configured("Google Calendar", _NEEDS)
    summary = (args.get("summary") or "").strip()
    start = (args.get("start") or "").strip()
    end = (args.get("end") or "").strip()
    if not (summary and start):
        return "I need at least a title and a start time to add that, sir."
    if not end:
        # Default to a one-hour block when no end is given.
        try:
            end = (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat()
        except ValueError:
            end = start
    try:
        body = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": settings.user_tz},
            "end": {"dateTime": end, "timeZone": settings.user_tz},
        }
        await api_post(_CAL, body)
        return f"Added '{summary}' to your calendar, sir, starting {start.replace('T', ' at ')}."
    except Exception as e:  # noqa: BLE001
        return tool_error("calendar create", e)


async def calendar_signals():
    """Proactive signal source: a heads-up for each timed event starting in the next ~15 min.

    This is the calendar 'backbone' the proactive engine was always meant to tick over (it had only
    health signals wired, so it stayed silent whenever the system was healthy). Fail-quiet: not
    logged in, no events, or any API error -> no signals. Repeat-suppression (by event id, in the
    engine) keeps it to one nudge per event even though the 5-min tick re-sees the 15-min window."""
    from jarvis.brain.proactive import Signal  # lazy: avoid a calendar<->proactive import cycle

    if not configured():
        return []
    now = datetime.now(timezone.utc)
    try:
        data = await api_get(_CAL, params={
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(minutes=15)).isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 5,
        })
    except Exception:  # noqa: BLE001 — a broken source must never throw into the tick loop
        return []
    out = []
    for ev in data.get("items") or []:
        start = (ev.get("start") or {}).get("dateTime")  # timed events only; skip all-day
        if not start:
            continue
        try:
            when = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        mins = max(0, round((when - now).total_seconds() / 60))
        title = ev.get("summary", "an event")
        msg = f"Sir, {title} is starting now." if mins == 0 else f"Sir, {title} starts in {mins} minute(s)."
        out.append(Signal(key=f"cal-{ev.get('id', start)}", kind="calendar", urgency=0.75, message=msg))
    return out


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": (
                "List upcoming Google Calendar events. Use for 'what's on today / this week / "
                "what's my next meeting'. days=1 is today; max caps the count."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Look-ahead window in days (default 1)."},
                    "max": {"type": "integer", "description": "Max events to read (default 10)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": (
                "Create a Google Calendar event. Confirm the title and time with the owner first. "
                "start/end are ISO-8601 local times (e.g. '2026-06-12T15:00'); end defaults to +1h."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start": {"type": "string", "description": "ISO-8601 start, e.g. 2026-06-12T15:00."},
                    "end": {"type": "string", "description": "ISO-8601 end (optional; defaults +1h)."},
                },
                "required": ["summary", "start"],
            },
        },
    },
]

HANDLERS = {"list_events": list_events, "create_event": create_event}
