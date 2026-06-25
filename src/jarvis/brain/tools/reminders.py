"""Reminder tools — Jarvis's proactive memory (Phase 4).

Thin tool wrappers over ``brain/scheduler.py``. Jarvis sets one-shot or daily reminders that
later fire and get spoken (if he's running) and/or pushed to the phone via ntfy.
"""

from __future__ import annotations

from loguru import logger

from jarvis.brain.scheduler import SCHEDULER
from jarvis.brain.tools.base import tool_error
from jarvis.config import settings


async def _register_daily_with_ticker(job_id: str, message: str, daily: str) -> bool:
    """Best-effort: mirror a daily reminder to the always-on VPS ticker. Never raises."""
    if not settings.ticker_url:
        return False
    try:
        import httpx

        headers = {}
        if settings.ticker_token:
            headers["Authorization"] = f"Bearer {settings.ticker_token}"
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as c:
            r = await c.post(
                f"{settings.ticker_url.rstrip('/')}/reminders",
                json={"id": job_id, "message": message, "daily": daily},
                headers=headers,
            )
            r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"ticker register failed: {type(e).__name__}: {e}")
        return False


async def _cancel_on_ticker(job_id: str) -> None:
    """Best-effort: drop a reminder from the VPS ticker too. Never raises."""
    if not settings.ticker_url:
        return
    try:
        import httpx

        headers = {}
        if settings.ticker_token:
            headers["Authorization"] = f"Bearer {settings.ticker_token}"
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as c:
            await c.post(
                f"{settings.ticker_url.rstrip('/')}/reminders/cancel",
                json={"id": job_id}, headers=headers,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"ticker cancel failed: {type(e).__name__}: {e}")


async def set_reminder(args: dict) -> str:
    message = (args.get("message") or "").strip()
    if not message:
        return "What should I remind you about, sir?"
    in_minutes = args.get("in_minutes")
    at = (args.get("at") or "").strip() or None
    daily = (args.get("daily") or "").strip() or None
    if in_minutes is None and not at and not daily:
        return "When should I remind you, sir? Give me a delay, a time, or a daily time."
    try:
        job_id, when, ntfy_epoch = SCHEDULER.add_reminder(
            message, in_minutes=in_minutes, at=at, daily=daily
        )
        # Phase 4b — hand one-shot phone delivery to ntfy's server-side scheduler so it reaches
        # the phone even if the PC is off at fire time. If ntfy refuses, fall back to the
        # in-process push (re-enable push_phone on the job).
        suffix = ""
        if ntfy_epoch is not None:
            from jarvis.brain.tools.notify import push

            if await push(message, title="Reminder", at=ntfy_epoch):
                suffix = " I've also queued it to your phone, so it'll reach you even if this PC is off."
            else:
                SCHEDULER.set_push_phone(job_id, True)
        elif daily:
            # Recurring reminders can't be held by ntfy; register with the always-on VPS ticker
            # (if configured) so they still push with the PC off (Phase 4b).
            if await _register_daily_with_ticker(job_id, message, daily):
                suffix = " I've also registered it on the always-on host, so it'll fire even if this PC is off."
        return f"Done, sir — I'll remind you {when}: \"{message}\".{suffix} (id {job_id[:8]})"
    except Exception as e:  # noqa: BLE001
        return tool_error("reminder", e)


async def list_reminders(args: dict) -> str:
    try:
        jobs = SCHEDULER.list_reminders()
        if not jobs:
            return "You have no reminders set, sir."
        lines = [f"- {name} — next {when} (id {jid[:8]})" for jid, name, when in jobs]
        return f"You have {len(jobs)} reminder(s), sir:\n" + "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return tool_error("reminder list", e)


async def cancel_reminder(args: dict) -> str:
    job_id = (args.get("id") or "").strip()
    if not job_id:
        return "Which reminder should I cancel, sir? Tell me its id from the list."
    try:
        # Allow a short id prefix from the spoken list.
        full = next((jid for jid, _, _ in SCHEDULER.list_reminders() if jid.startswith(job_id)), job_id)
        ok = SCHEDULER.cancel(full)
        await _cancel_on_ticker(full)  # best-effort: also drop it from the always-on host
        return "Cancelled, sir." if ok else f"I couldn't find a reminder '{job_id}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("reminder cancel", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Set a reminder that will be spoken (and pushed to his phone) when it fires. "
                "Give exactly one timing: in_minutes (delay), at (ISO datetime like "
                "'2026-06-11T08:00'), or daily ('HH:MM' for a recurring daily reminder)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "What to remind him about."},
                    "in_minutes": {"type": "number", "description": "Fire after this many minutes."},
                    "at": {"type": "string", "description": "Absolute time, ISO-8601."},
                    "daily": {"type": "string", "description": "Recurring daily time 'HH:MM'."},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List the owner's pending reminders with their next fire time and id.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Cancel a reminder by its id (a short prefix from list_reminders is fine).",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Reminder id (or prefix)."}},
                "required": ["id"],
            },
        },
    },
]

HANDLERS = {
    "set_reminder": set_reminder,
    "list_reminders": list_reminders,
    "cancel_reminder": cancel_reminder,
}
