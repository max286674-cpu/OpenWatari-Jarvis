"""Phase 10 — the proactive engine and the small clarification/confirmation policy helpers."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from loguru import logger
from jarvis.config import settings

USER_TZ = ZoneInfo(settings.user_tz)

@dataclass
class Signal:
    key: str
    message: str
    urgency: float
    kind: str = "note"
    action: Callable[[], "None | Awaitable[None]"] | None = field(default=None, compare=False)

@dataclass
class Interjection:
    signal: Signal
    channel: str

SignalSource = Callable[[], "list[Signal] | Awaitable[list[Signal]]"]
Emitter = Callable[[str, float, bool], Awaitable[str]]


def _parse_quiet(spec: str) -> tuple[int, int] | None:
    try:
        a, b = spec.split("-")
        ah, am = (int(x) for x in a.strip().split(":"))
        bh, bm = (int(x) for x in b.strip().split(":"))
        return ah * 60 + am, bh * 60 + bm
    except Exception:
        return None


def in_quiet_hours(now: datetime, spec: str | None = None) -> bool:
    rng = _parse_quiet(spec if spec is not None else settings.proactive_quiet_hours)
    if rng is None:
        return False
    start, end = rng
    minute = now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


# Only consequential external/destructive operations should interrupt the owner with a confirmation.
# Routine local computer control is deliberately NOT in this tier.
CONFIRM_TIER = {
    "send_telegram", "send_email", "send_push",
    "file_op", "run_powershell", "run_protocol", "ha_call",
    "write_source", "git_commit", "git_push", "git_revert",
    "create_github_issue",
    "notion_append", "notion_comment", "notion_create_page", "notion_delete_task",
    "composio_run_tool",
}

_COMPOSIO_READ = ("GET", "LIST", "FETCH", "SEARCH", "RETRIEVE", "FIND", "READ", "VIEW", "COUNT")
_COMPOSIO_WRITE = ("CREATE", "SEND", "POST", "UPDATE", "DELETE", "ADD", "REMOVE", "CHARGE", "REFUND",
                   "MERGE", "CLOSE", "SET", "EDIT", "UPLOAD", "INVITE", "ARCHIVE", "CANCEL", "ASSIGN",
                   "MOVE", "RENAME", "REPLY", "COMMENT", "WRITE", "INSERT", "APPEND", "PUT", "PATCH")


def _composio_write(slug: str) -> bool:
    s = (slug or "").upper()
    if any(w in s for w in _COMPOSIO_WRITE):
        return True
    if any(r in s for r in _COMPOSIO_READ):
        return False
    return True

_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they", "это", "то", "его", "её", "ее", "их"}


def confirm_required(tool_name: str, args: dict | None = None) -> bool:
    """Confirmation is reserved for consequential external/destructive actions.

    Opening/closing apps, killing a local process, clicking/typing on the local desktop, reading files,
    creating/editing local documents, browser navigation and calendar creation are routine and run once.
    """
    name = (tool_name or "").strip()
    if name not in CONFIRM_TIER:
        return False
    if name == "file_op":
        action = str((args or {}).get("action", ""))
        return action.startswith("delete")
    if name == "composio_run_tool":
        return _composio_write(str((args or {}).get("tool_slug", "")))
    if name == "ha_call":
        return (args or {}).get("domain", "") in {"lock", "alarm_control_panel", "cover", "garage_door"}
    return True


def needs_clarification(text: str) -> bool:
    t = (text or "").strip().lower().rstrip("?.!")
    if not t:
        return True
    words = [w for w in t.split() if w]
    if len(words) == 1 and words[0] in _PRONOUN_ONLY:
        return True
    if len(words) == 2 and words[1] in _PRONOUN_ONLY:
        return True
    return False


class ProactiveEngine:
    def __init__(self, emit: Emitter | None = None, sources: list[SignalSource] | None = None,
                 is_listening: Callable[[], bool] | None = None, clock: Callable[[], datetime] | None = None,
                 is_busy: Callable[[], bool] | None = None, *, quiet_hours: str | None = None,
                 daily_budget: int | None = None, threshold: float | None = None,
                 repeat_suppress_minutes: int | None = None, quiet_override: float | None = None,
                 context_override: float | None = None, state_path: str | None = None) -> None:
        self._emit = emit or self._default_emit
        self._sources = sources or []
        self._is_listening = is_listening or (lambda: False)
        self._is_busy = is_busy or (lambda: False)
        self._clock = clock or (lambda: datetime.now(USER_TZ))
        self._quiet = quiet_hours if quiet_hours is not None else settings.proactive_quiet_hours
        self._budget = daily_budget if daily_budget is not None else settings.proactive_daily_budget
        self._threshold = threshold if threshold is not None else settings.proactive_relevance_threshold
        self._suppress_min = repeat_suppress_minutes if repeat_suppress_minutes is not None else settings.proactive_repeat_suppress_minutes
        self._override = quiet_override if quiet_override is not None else settings.proactive_quiet_override_urgency
        self._context_override = context_override if context_override is not None else settings.proactive_context_override_urgency
        self._spoken_at: dict[str, datetime] = {}
        self._day: str | None = None
        self._used_today = 0
        self._task: asyncio.Task | None = None
        self._state_path = Path(state_path or settings.proactive_state_path)

    async def _default_emit(self, message: str, urgency: float, listening: bool) -> str:
        return "suppressed"

    async def tick(self) -> Interjection | None:
        now = self._clock()
        day = now.date().isoformat()
        if day != self._day:
            self._day, self._used_today = day, 0
        if self._is_busy():
            return None
        signals: list[Signal] = []
        for source in self._sources:
            try:
                result = source()
                if inspect.isawaitable(result):
                    result = await result
                signals.extend(result or [])
            except Exception as e:
                logger.debug(f"proactive source skipped: {e}")
        signals.sort(key=lambda s: s.urgency, reverse=True)
        for signal in signals:
            if signal.urgency < self._threshold:
                continue
            last = self._spoken_at.get(signal.key)
            if last and now - last < timedelta(minutes=self._suppress_min):
                continue
            quiet = in_quiet_hours(now, self._quiet)
            if quiet and signal.urgency < self._override:
                continue
            if self._used_today >= self._budget and signal.urgency < self._context_override:
                continue
            try:
                channel = await self._emit(signal.message, signal.urgency, self._is_listening())
            except Exception as e:
                logger.debug(f"proactive emit skipped: {e}")
                channel = "suppressed"
            if channel != "suppressed":
                self._spoken_at[signal.key] = now
                self._used_today += 1
                if signal.action:
                    try:
                        result = signal.action()
                        if inspect.isawaitable(result):
                            await result
                    except Exception as e:
                        logger.debug(f"proactive action failed: {e}")
                return Interjection(signal, channel)
        return None
