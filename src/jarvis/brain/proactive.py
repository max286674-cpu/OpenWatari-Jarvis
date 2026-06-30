"""Phase 10 — the proactive engine: Jarvis decides when to speak *unprompted*.

The owner's ask, verbatim: proactivity means Jarvis can remind, pause, ask for context, re-ask /
confirm, interrupt, and *start speaking on his own* when he judges it helpful. This module is the
"start speaking on his own" brain: a background **tick** that, on an interval, gathers signals,
asks "is anything worth saying right now, and how urgent?", and acts — but inside a strict
**interruption budget** and **quiet hours**, so he's a companion, not a nag.

Design goals:
  * **Decoupled + testable.** The decision core (budget, quiet hours, relevance threshold,
    repeat-suppression, day rollover) is pure and driven by an injectable clock + signal sources,
    so the whole policy is verified offline with no mic, no network, no real time passing.
  * **Fail-quiet.** A broken signal source or emit channel never throws into the tick loop; worst
    case Jarvis simply stays silent.
  * **Two channels.** If a device is listening, an interjection is *spoken* (interrupt). If not, it
    falls back to an ntfy push so it still reaches his phone. Routine-grade signals stay silent in
    quiet hours; only a near-emergency (>= quiet_override) gets through then, and only as a push.

The clarify/confirm verbs live alongside as small policy helpers (`needs_clarification`,
`confirm_required`) the agent loop and persona use before acting on ambiguous or consequential
requests.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from jarvis.config import settings

USER_TZ = ZoneInfo(settings.user_tz)


@dataclass
class Signal:
    """A candidate thing-to-say the tick may surface."""

    key: str                 # stable id for repeat-suppression (e.g. 'standup-0915')
    message: str             # what Jarvis would say, in his voice
    urgency: float           # 0..1 — clears the relevance threshold to be voiced
    kind: str = "note"       # reminder | routine | thread | calendar | health | …


@dataclass
class Interjection:
    """The outcome of one tick — what was said and how (for logging/tests)."""

    signal: Signal
    channel: str             # 'voice' | 'push' | 'suppressed'


# A signal source is a 0-arg callable returning a list of Signals (sync or async).
SignalSource = Callable[[], "list[Signal] | Awaitable[list[Signal]]"]
# An emitter takes (message, urgency, listening) and returns the channel actually used.
Emitter = Callable[[str, float, bool], Awaitable[str]]


def _parse_quiet(spec: str) -> tuple[int, int] | None:
    """'23:00-07:00' -> (start_minute, end_minute) of day. None if unparseable/blank."""
    try:
        a, b = spec.split("-")
        ah, am = (int(x) for x in a.strip().split(":"))
        bh, bm = (int(x) for x in b.strip().split(":"))
        return ah * 60 + am, bh * 60 + bm
    except Exception:  # noqa: BLE001
        return None


def in_quiet_hours(now: datetime, spec: str | None = None) -> bool:
    spec = spec if spec is not None else settings.proactive_quiet_hours
    rng = _parse_quiet(spec or "")
    if rng is None:
        return False
    start, end = rng
    minute = now.hour * 60 + now.minute
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end   # window wraps past midnight


# ---- clarify / confirm policy (the "ask for context" + "re-ask/confirm" verbs) -----------

# Tools whose effects are outward-facing, costly, or hard to undo — Jarvis confirms before these.
CONFIRM_TIER = {
    "send_telegram", "send_email", "send_push",
    "file_op", "process_op", "run_powershell", "browser",
    "run_protocol", "ha_call",
    "create_event",
    # Phase 13 — self-improvement writes are reversible via git, but still consequential.
    "write_source", "git_commit", "git_push", "git_revert",
    # Notion writes modify the owner's shared docs.
    "notion_append", "notion_comment", "notion_create_page",
    # Deleting a task is destructive (archives the row) — confirm. Creating/updating/completing a
    # task is frictionless by design (capture-by-voice), so those are intentionally NOT gated.
    "notion_delete_task",
    # Composio app actions: gated only when the slug is a WRITE (see _composio_write below).
    "composio_run_tool",
}

# Composio tool slugs encode the verb (GITHUB_CREATE_AN_ISSUE, SLACKBOT_CHAT_POST_MESSAGE). Reads run
# freely; anything that writes/sends/changes the owner's external apps is confirm-gated. Unknown = gate.
_COMPOSIO_READ = ("GET", "LIST", "FETCH", "SEARCH", "RETRIEVE", "FIND", "READ", "VIEW", "COUNT")
_COMPOSIO_WRITE = ("CREATE", "SEND", "POST", "UPDATE", "DELETE", "ADD", "REMOVE", "CHARGE", "REFUND",
                   "MERGE", "CLOSE", "SET", "EDIT", "UPLOAD", "INVITE", "ARCHIVE", "CANCEL", "ASSIGN",
                   "MOVE", "RENAME", "REPLY", "COMMENT", "WRITE", "INSERT", "APPEND", "PUT", "PATCH")


def _composio_write(slug: str) -> bool:
    """True (confirm) if a Composio tool slug writes/changes an app; False for clear reads."""
    s = (slug or "").upper()
    if any(w in s for w in _COMPOSIO_WRITE):
        return True
    if any(r in s for r in _COMPOSIO_READ):
        return False
    return True  # unknown verb -> gate (safe default)

_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they"}


def confirm_required(tool_name: str, args: dict | None = None) -> bool:
    """True if Jarvis should re-ask for confirmation before running this tool.

    file_op deletes and ha_call locks are the dangerous edges; sends spend the owner's voice to
    third parties. Reads (recall, web_search, get_time, list_*) are never gated.
    """
    name = (tool_name or "").strip()
    if name not in CONFIRM_TIER:
        return False
    if name == "file_op":
        action = (args or {}).get("action", "")
        return str(action).startswith("delete")     # create/list need no confirm
    if name == "process_op":
        return (args or {}).get("action") in {"kill", "start"}
    if name == "composio_run_tool":
        return _composio_write(str((args or {}).get("tool_slug", "")))
    return True


def needs_clarification(text: str) -> bool:
    """Heuristic: is the request too thin to act on without asking a question first?

    Empty, a bare pronoun ('do it'), or a lone vague verb gets a clarifying question rather than a
    guess. Deliberately conservative — false negatives (acting) are cheaper than nagging.
    """
    t = (text or "").strip().lower().rstrip("?.!")
    if not t:
        return True
    words = [w for w in t.split() if w]
    if len(words) == 1 and words[0] in _PRONOUN_ONLY:
        return True
    # "do it" / "handle that" / "sort this" — verb + bare pronoun, no object.
    if len(words) == 2 and words[1] in _PRONOUN_ONLY:
        return True
    return False


class ProactiveEngine:
    """The tick + interruption budget + quiet-hours gate. Pure decision core, injectable I/O."""

    def __init__(
        self,
        emit: Emitter | None = None,
        sources: list[SignalSource] | None = None,
        is_listening: Callable[[], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
        *,
        quiet_hours: str | None = None,
        daily_budget: int | None = None,
        threshold: float | None = None,
        repeat_suppress_minutes: int | None = None,
        quiet_override: float | None = None,
    ) -> None:
        self._emit = emit or self._default_emit
        self._sources = sources or []
        self._is_listening = is_listening or (lambda: False)
        self._clock = clock or (lambda: datetime.now(USER_TZ))
        self._quiet = quiet_hours if quiet_hours is not None else settings.proactive_quiet_hours
        self._budget = daily_budget if daily_budget is not None else settings.proactive_daily_budget
        self._threshold = threshold if threshold is not None else settings.proactive_relevance_threshold
        self._suppress_min = (
            repeat_suppress_minutes if repeat_suppress_minutes is not None
            else settings.proactive_repeat_suppress_minutes
        )
        self._override = (
            quiet_override if quiet_override is not None else settings.proactive_quiet_override_urgency
        )
        self._spoken_at: dict[str, datetime] = {}   # signal.key -> last emitted time
        self._day: str | None = None
        self._used_today = 0
        self._task: asyncio.Task | None = None

    # ---- budget / day rollover --------------------------------------------------------
    def _roll_day(self, now: datetime) -> None:
        today = now.strftime("%Y-%m-%d")
        if today != self._day:
            self._day = today
            self._used_today = 0

    @property
    def budget_remaining(self) -> int:
        return max(0, self._budget - self._used_today)

    # ---- selection --------------------------------------------------------------------
    def _recently_said(self, key: str, now: datetime) -> bool:
        last = self._spoken_at.get(key)
        return last is not None and (now - last) < timedelta(minutes=self._suppress_min)

    def select(self, signals: list[Signal], now: datetime) -> Signal | None:
        """Pick the most urgent signal that clears the threshold and isn't repeat-suppressed."""
        eligible = [
            s for s in signals
            if s.urgency >= self._threshold and not self._recently_said(s.key, now)
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda s: s.urgency)

    async def _gather(self) -> list[Signal]:
        out: list[Signal] = []
        for src in self._sources:
            try:
                res = src()
                if inspect.isawaitable(res):
                    res = await res
                for s in res or []:
                    if isinstance(s, Signal) and s.message.strip():
                        out.append(s)
            except Exception as e:  # noqa: BLE001 — a bad source must never break the tick
                logger.warning(f"proactive source failed: {type(e).__name__}: {e}")
        return out

    # ---- the tick ---------------------------------------------------------------------
    async def maybe_interject(self, now: datetime | None = None) -> Interjection | None:
        """One evaluation: gather → select → (quiet-hours/budget gate) → emit. Returns what it did."""
        now = now or self._clock()
        self._roll_day(now)
        if self.budget_remaining <= 0:
            return None
        # Behavioural modes (focus/lockdown) mute unprompted speech regardless of signals.
        try:
            from jarvis.brain.modes import MODES

            if MODES.proactivity_suppressed(now):
                return None
        except Exception:  # noqa: BLE001
            pass
        signal = self.select(await self._gather(), now)
        if signal is None:
            return None

        quiet = in_quiet_hours(now, self._quiet)
        if quiet and signal.urgency < self._override:
            return None  # routine-grade: hold it until quiet hours end

        listening = False
        try:
            listening = bool(self._is_listening())
        except Exception:  # noqa: BLE001
            listening = False
        # In quiet hours even an override goes by silent push, never spoken.
        speak = listening and not quiet
        try:
            channel = await self._emit(signal.message, signal.urgency, speak)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"proactive emit failed: {type(e).__name__}: {e}")
            return None
        if channel == "suppressed":
            return Interjection(signal, "suppressed")
        self._spoken_at[signal.key] = now
        self._used_today += 1
        logger.info(f"proactive [{signal.kind}] via {channel}: {signal.message[:60]!r}")
        return Interjection(signal, channel)

    async def _default_emit(self, message: str, urgency: float, listening: bool) -> str:
        """No-voice fallback emitter: push to the phone via ntfy (used when no server is wired)."""
        from jarvis.brain.tools.notify import push

        ok = await push(message, title="Watari")
        return "push" if ok else "suppressed"

    # ---- background loop --------------------------------------------------------------
    async def run(self) -> None:
        """Tick forever on the configured interval. Cancelled on shutdown."""
        interval = max(15, settings.proactive_tick_seconds)
        logger.info(
            f"proactive engine on: every {interval}s, budget {self._budget}/day, "
            f"quiet {self._quiet}, threshold {self._threshold}"
        )
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.maybe_interject()
                except Exception:  # noqa: BLE001
                    logger.exception("proactive tick error (continuing)")
        except asyncio.CancelledError:
            logger.info("proactive engine stopped")
            raise

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run())
        return self._task


def default_signal_sources() -> list[SignalSource]:
    """The signal sources the live brain ticks over. Extended as capabilities land:

    * self-health (brain/vault/ticker reachability) — Phase X cross-cutting,
    * calendar (upcoming events) — Phase 11,
    * open threads from the journal/learned memory.

    Kept deliberately small and additive so each source can fail independently.
    """
    sources: list[SignalSource] = []
    try:
        from jarvis.brain.health import health_signals

        sources.append(health_signals)
    except Exception:  # noqa: BLE001 — health module optional until Phase X
        pass
    try:
        from jarvis.brain.tools.calendar import calendar_signals

        sources.append(calendar_signals)  # imminent-event heads-up (the proactive 'backbone')
    except Exception:  # noqa: BLE001 — fail-quiet if calendar/login isn't available
        pass
    try:
        from jarvis.brain.tools.notion import task_signals

        sources.append(task_signals)      # daily nudge on overdue / due-today tasks
    except Exception:  # noqa: BLE001
        pass
    try:
        from jarvis.brain.tools.gmail import email_signals

        sources.append(email_signals)     # daily nudge on important unread mail
    except Exception:  # noqa: BLE001
        pass
    return sources
