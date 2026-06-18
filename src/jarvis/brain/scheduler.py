"""Proactive scheduler — the engine behind reminders and timed/recurring nudges (Phase 4).

A single process-wide ``SCHEDULER`` (APScheduler ``AsyncIOScheduler``) persisted to SQLite, so
reminders survive a restart. When a job fires it calls the module-level coroutine ``_fire`` (a
top-level function so APScheduler can serialize the reference), which delivers the message two
ways: it **speaks** it through the live edge callback if Jarvis is running, and **pushes** it
to the phone via ntfy. Either path is best-effort.

Triggers supported by ``add_reminder``: a one-shot delay (``in_minutes``), an absolute time
(``at`` ISO-8601), or a daily time (``daily`` 'HH:MM').
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from loguru import logger

from jarvis.config import settings

USER_TZ = ZoneInfo("Europe/Berlin")

# Set by SCHEDULER.start(): how to SPEAK a fired reminder on the live edge (push a TTS frame).
_LIVE_SPEAK: Callable[[str], None] | None = None

# Set by the brain server: richest proactive delivery (voice -> Telegram voice note -> ntfy push).
# Signature mirrors BrainServer.proactive_emit(message, urgency, speak) -> awaitable[str].
_BRIEFING_EMIT: Callable | None = None


async def _fire_briefing() -> None:
    """Top-level job target (importable for the SQLite jobstore): the daily task briefing.

    Builds today's overdue+due summary from the Notion tasks DB at fire time, then delivers it the
    proactive way — spoken to a listening device, else a Telegram voice note, else an ntfy push.
    """
    try:
        from jarvis.brain.tools.notion import notion_tasks

        # 'open' = overdue + due-today + this-week deadlines + recurring, so the morning briefing
        # covers what's due today AND upcoming deadlines AND standing recurring tasks (not today only).
        body = await notion_tasks({"scope": "open"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"task briefing build failed: {e}")
        return
    if not body or "Nothing due" in body or "not configured" in body:
        msg = "Good morning, sir. Nothing's due today — you're clear."
    else:
        msg = "Good morning, sir. Here's your day. " + body
    logger.info("firing daily task briefing")
    if _BRIEFING_EMIT is not None:
        try:
            res = _BRIEFING_EMIT(msg, 0.6, True)
            if hasattr(res, "__await__"):
                await res
            return
        except Exception as e:  # noqa: BLE001
            logger.warning(f"briefing proactive-emit failed ({e}); falling back to speak+push")
    # Fallback (no proactive emitter wired): speak on the live edge + push to phone.
    if _LIVE_SPEAK is not None:
        try:
            _LIVE_SPEAK(msg)
        except Exception:  # noqa: BLE001
            pass
    try:
        from jarvis.brain.tools.notify import push

        await push(msg, title="Watari — today")
    except Exception:  # noqa: BLE001
        pass


async def _fire(message: str, push_phone: bool = True) -> None:
    """Top-level job target (must be importable for the SQLite jobstore). Delivers a reminder.

    ``push_phone`` is False when the phone delivery was already handed to ntfy's server-side
    scheduler at set-time (Phase 4b): in that case this in-process firing only *speaks* it (when
    the edge is live), and ntfy independently delivers the push — avoiding a double-push. If the
    edge is off, ntfy still delivers; if ntfy couldn't take it, push_phone stays True as a fallback.
    """
    logger.info(f"reminder fired: {message!r} (push_phone={push_phone})")
    spoke = False
    if _LIVE_SPEAK is not None:
        try:
            _LIVE_SPEAK(message)
            spoke = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"reminder speak failed: {e}")
    if push_phone:
        try:
            from jarvis.brain.tools.notify import push

            await push(message, title="Reminder" if spoke else "Watari reminder")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"reminder push failed: {e}")


def _db_url() -> str:
    from pathlib import Path

    path = settings.scheduler_db_path or str(
        Path(__file__).resolve().parents[3] / "jarvis_jobs.sqlite"
    )
    return f"sqlite:///{path}"


class Scheduler:
    def __init__(self) -> None:
        self._sched = None

    def _ensure(self):
        if self._sched is not None:
            return self._sched
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._sched = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=_db_url())},
            timezone=USER_TZ,
        )
        return self._sched

    def start(self, on_speak: Callable[[str], None] | None = None) -> None:
        """Start the scheduler (idempotent) and register how to speak fired reminders."""
        global _LIVE_SPEAK
        if on_speak is not None:
            _LIVE_SPEAK = on_speak
        sched = self._ensure()
        if not sched.running:
            sched.start()
            logger.info("scheduler started")

    def set_briefing_emit(self, emit: Callable | None) -> None:
        """Register the proactive delivery used by the daily briefing (server.proactive_emit)."""
        global _BRIEFING_EMIT
        _BRIEFING_EMIT = emit

    def schedule_daily_briefing(self, hhmm: str) -> str | None:
        """(Re)register the daily task briefing at HH:MM. Fixed id so restarts refresh, not duplicate.
        Returns the job id, or None if disabled/invalid."""
        if not (hhmm or "").strip():
            return None
        from apscheduler.triggers.cron import CronTrigger

        hh, mm = _parse_hhmm(hhmm)
        sched = self._ensure()
        sched.add_job(_fire_briefing, trigger=CronTrigger(hour=hh, minute=mm, timezone=USER_TZ),
                      id="daily-task-briefing", name="daily task briefing",
                      misfire_grace_time=3600, coalesce=True, replace_existing=True)
        logger.info(f"daily task briefing scheduled for {hh:02d}:{mm:02d}")
        return "daily-task-briefing"

    def run_briefing_now(self) -> None:
        """Fire the briefing immediately (for a 'brief me now' voice command or a test)."""
        import asyncio as _a

        try:
            _a.get_running_loop().create_task(_fire_briefing())
        except RuntimeError:
            _a.run(_fire_briefing())

    def add_reminder(
        self,
        message: str,
        in_minutes: float | None = None,
        at: str | None = None,
        daily: str | None = None,
    ) -> tuple[str, str, float | None]:
        """Schedule a reminder. Returns (job_id, human-readable when, ntfy_epoch_or_None).

        ``ntfy_epoch_or_None`` is the absolute fire time (Unix seconds) when this is a one-shot
        reminder that ntfy can deliver server-side (true PC-off 24/7 — Phase 4b); the caller
        should then hand that push to ntfy. It's None for recurring (daily) reminders or one-shots
        outside ntfy's window — those rely on the live edge / an always-on host. Raises ValueError
        on bad input.
        """
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger

        from jarvis.brain.tools.notify import ntfy_can_schedule

        sched = self._ensure()
        fire_dt: datetime | None = None  # absolute fire time for one-shots (for ntfy scheduling)
        if daily:
            hh, mm = _parse_hhmm(daily)
            trigger = CronTrigger(hour=hh, minute=mm, timezone=USER_TZ)
            when = f"every day at {hh:02d}:{mm:02d}"
        elif at:
            dt = datetime.fromisoformat(at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=USER_TZ)
            trigger = DateTrigger(run_date=dt)
            when = dt.strftime("%A %d %B at %H:%M")
            fire_dt = dt
        elif in_minutes is not None:
            dt = datetime.now(USER_TZ) + timedelta(minutes=float(in_minutes))
            trigger = DateTrigger(run_date=dt)
            when = f"in {_fmt_minutes(float(in_minutes))} (at {dt.strftime('%H:%M')})"
            fire_dt = dt
        else:
            raise ValueError("need one of in_minutes / at / daily")

        # Phase 4b: if ntfy can hold this one-shot server-side, let IT own the phone push (fires
        # even with the PC off). The in-process job then only SPEAKS (push_phone=False) to avoid a
        # double-push. Recurring/out-of-window jobs keep push_phone=True (live edge / VPS ticker).
        ntfy_epoch = fire_dt.timestamp() if (fire_dt and ntfy_can_schedule(fire_dt.timestamp())) else None
        push_phone = ntfy_epoch is None

        # misfire_grace_time large + coalesce: if the PC was off/asleep when a reminder was due,
        # still fire it (once) the moment the edge comes back, instead of silently dropping it.
        job = sched.add_job(_fire, trigger=trigger, args=[message, push_phone], name=message,
                            misfire_grace_time=86400, coalesce=True, replace_existing=False)
        return job.id, when, ntfy_epoch

    def set_push_phone(self, job_id: str, value: bool) -> None:
        """Flip a job's push_phone flag — used to re-enable the in-process push if ntfy refused."""
        sched = self._ensure()
        try:
            job = sched.get_job(job_id)
            if job is not None:
                sched.modify_job(job_id, args=[job.args[0], value])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"set_push_phone failed: {e}")

    def list_reminders(self) -> list[tuple[str, str, str]]:
        sched = self._ensure()
        out = []
        for job in sched.get_jobs():
            nxt = job.next_run_time.strftime("%a %d %b %H:%M") if job.next_run_time else "—"
            out.append((job.id, job.name or "", nxt))
        return out

    def cancel(self, job_id: str) -> bool:
        sched = self._ensure()
        try:
            sched.remove_job(job_id)
            return True
        except Exception:  # noqa: BLE001
            return False


def _parse_hhmm(s: str) -> tuple[int, int]:
    parts = s.strip().split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _fmt_minutes(m: float) -> str:
    if m < 60:
        return f"{int(m)} minute(s)"
    h, mm = divmod(int(m), 60)
    return f"{h}h{mm:02d}m"


SCHEDULER = Scheduler()
