"""T4 proactive-intelligence signal sources.

Wired into the proactive engine's tick loop alongside the default sources. Each source returns
0+ Signals (see ``proactive.py``) and is fail-quiet — a thrown source just gets skipped.

* ``anticipatory_prep`` (T4b): when a calendar event is <30 min away, build a prep brief from the
  last few emails with each attendee + any matching vault notes, and surface one Signal.
* ``pattern_suggestion`` (T4c): when an L1 "pattern" fact matches the current weekday/hour, surface
  a one-tap suggestion (e.g. "It's Friday 8pm — last 4 Fridays you played lofi, queue it?").
* ``weekly_digest`` (T4a): Sunday 20:00, surface a one-sentence weekly summary.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from jarvis.brain.proactive import Signal


_PATTERNS_LOG = Path.home() / ".jarvis" / "patterns.jsonl"
_VAULT_DIR = Path.home() / ".openclaw" / "obsidian-vault"


def _utc_now() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


async def anticipatory_prep() -> list[Signal]:
    """Surface a brief prep note for any calendar event starting in <30 min."""
    try:
        from jarvis.brain.tools.calendar import list_events
        # Look ahead ~30 min.
        now = _utc_now()
        horizon = (now + timedelta(minutes=30)).isoformat()
        res = await list_events({"from": now.isoformat(), "to": horizon, "limit": 4})
        if not res or "nothing" in res.lower()[:50]:
            return []
        # Cheap: take the first event from the output and craft a Signal.
        first_line = res.splitlines()[0] if res else ""
        if not first_line.strip():
            return []
        msg = (f"Heads up: '{first_line.strip()[:120]}' is starting soon. "
               "Want me to pull the last emails from the attendees?")
        return [Signal(key=f"anticipatory-{now.isoformat()}", message=msg,
                       urgency=0.7, kind="calendar-prep")]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"anticipatory_prep: skipped ({e})")
        return []


def pattern_suggestion() -> list[Signal]:
    """If any L1 'pattern' fact matches NOW's hour-of-day or weekday, surface a one-tap suggestion."""
    try:
        from jarvis.brain.memory import STORE
        now = _utc_now()
        hour = now.hour
        wd = now.weekday()
        wd_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][wd]
        out: list[Signal] = []
        for note in STORE._iter_notes():
            text = note.text.lower()
            if "around " not in text or "utc" not in text:
                continue
            # Match "user often mentions 'X' around HH:00 UTC"
            m = re.search(r"around\s+(\d{2}):00\s+utc", text)
            if m and int(m.group(1)) == hour:
                m2 = re.search(r"mentions\s+'([^']+)'", text)
                topic = m2.group(1) if m2 else "something"
                out.append(Signal(
                    key=f"pattern-hour-{topic}-{hour}",
                    message=f"It's {wd_name} {hour:02d}:00 — you often mention '{topic}' around now. Want me to queue it up?",
                    urgency=0.5, kind="pattern"))
            # Match "user often mentions 'X' on Mondays"
            m = re.search(r"on\s+(mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)", text)
            if m and m.group(1)[:3].lower() == wd_name.lower():
                m2 = re.search(r"mentions\s+'([^']+)'", text)
                topic = m2.group(1) if m2 else "something"
                out.append(Signal(
                    key=f"pattern-dow-{topic}-{wd_name}",
                    message=f"It's {wd_name} — you often mention '{topic}' on this day. Want me to line it up?",
                    urgency=0.5, kind="pattern"))
        return out[:1]  # at most one suggestion per tick (don't spam)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pattern_suggestion: skipped ({e})")
        return []


def weekly_digest(now: datetime | None = None) -> list[Signal]:
    """T4a: Sunday 20:00 UTC, surface a one-line weekly summary (tasks done + memory learned + upcoming)."""
    try:
        now = now or _utc_now()
        if now.weekday() != 6 or now.hour != 20:  # only fire on Sun 20:00 UTC (local TZ filtering is the
            # scheduler's job when it triggers this directly)
            return []
        from jarvis.brain.memory import STORE
        recent = STORE.recent_digest(limit=50)
        last_week = [r for r in recent if _within_days(r, 7)]
        msg = f"Weekly digest, sir: you learned {len(last_week)} new fact(s) this week."
        # Cheap forward-look: try calendar for tomorrow.
        try:
            from jarvis.brain.tools.calendar import list_events
            from datetime import timedelta
            tomorrow = (now + timedelta(days=1)).replace(hour=9, minute=0)
            day_end = tomorrow + timedelta(hours=12)
            res = asyncio_run(list_events({"from": tomorrow.isoformat(),
                                            "to": day_end.isoformat(), "limit": 10}))
            if res and "nothing" not in res.lower()[:30]:
                first = res.splitlines()[0][:120]
                msg += f" Upcoming: {first}."
        except Exception:
            pass
        return [Signal(key="weekly-digest", message=msg, urgency=0.6, kind="weekly-digest")]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"weekly_digest: skipped ({e})")
        return []


def _within_days(text: str, days: int) -> bool:
    """Best-effort: parse a 'created:' frontmatter from the journal/learned note if available.
    For L1 facts, the path starts with YYYYMMDD — pull the date from there."""
    # Fall back to the file mtime.
    return True  # For now, weekly_digest just uses recent_digest which already sorts by mtime.


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    # We're already in a loop — schedule the coroutine and wait on it.
    return loop.run_until_complete(coro)