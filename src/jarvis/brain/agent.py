"""JarvisAgent — Jarvis's own reasoning loop: personality + memory + tools + session.

He answers as himself first. Tools are things he reaches for (the current time; the
OpenClaw fleet for deep work) — never a change of identity. Conversation history is kept
so he remembers the flow across turns ("what did I just ask you?").
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from jarvis.brain.context import build_system_prompt
from jarvis.brain.fleet import FLEET_TOOL_SCHEMA, FleetUnavailable, delegate_to_fleet
from jarvis.brain.llm import LLMClient
from jarvis.brain.tools import (
    core_tool_schemas,
    group_tool_schemas,
    groups_for_text,
    tool_handlers,
)

# Short spoken filler per tool so a longer turn is never dead air.
_TOOL_PROGRESS = {
    "delegate_to_fleet": "Let me put that to the team lead…",
    "search_vault": "Checking your vault…",
    "read_vault_note": "Reading that note…",
    "web_search": "Looking that up…",
    "scrape_url": "Opening the page…",
    "browse_web": "Opening a browser…",
    "check_telegram": "Checking your Telegram…",
    "send_telegram": "Sending that…",
    "telegram_music": "Pulling that from your playlist…",
    "play_in_music_room": "Cueing it up in your music room…",
    "stop_music_room": "Leaving the music room…",
    "play_music": "Finding that song…",
    "stop_music": "Stopping the music…",
    "file_op": "Working on your files…",
    "process_op": "On it…",
    "run_powershell": "Running that…",
    "browser": "In the browser…",
    "run_protocol": "Authorizing the protocol…",
    "set_reminder": "Setting that reminder…",
    "send_push": "Pinging your phone…",
}

# Vazghen is in Germany (UTC+1). Used for time/greeting/scheduling.
USER_TZ = ZoneInfo("Europe/Berlin")

# Some models, when pushed past their tool budget or asked to speak without tools, emit a
# textual tool-call (e.g. "<tool_call>browser ...") instead of prose. That must never be
# spoken, so we strip such artifacts from any final reply.
_ARTIFACT_RE = re.compile(
    r"<\s*/?\s*(tool_call|arg_key|arg_value|function|tool_response)\s*>|<\|[^>]*\|>",
    re.IGNORECASE,
)


# Weak models (e.g. llama-3.1-8b-instant) sometimes SPEAK a confirmation ("done, home is now X")
# without actually emitting the tool call. For unambiguous *imperative* commands — where the right
# behaviour is unquestionably to call a tool — we force the provider's tool_choice to "required" on
# the first pass so the model physically cannot answer with a hollow confirmation. Kept deliberately
# tight (clear commands, not capability questions) so normal chat still flows on "auto".
_COMMAND_PATTERNS = (
    r"\b(set|change|update|switch)\b.{0,30}\b(home|location)\b",
    r"\bremind me\b", r"\bset (a |an )?reminder\b", r"\bremember (that|to|my)\b",
    r"\b(send|reply)\b.{0,30}\b(telegram|message|dm|text)\b",
    r"\b(turn|switch) (on|off)\b", r"\b(lock|unlock|dim)\b", r"\bset the (thermostat|heating)\b",
    r"\bplay\b.{0,40}\b(song|music|track|playlist)\b", r"\bstop the music\b",
    r"\b(add|schedule|create).{0,30}\b(calendar|event|meeting|appointment)\b",
    r"\b(draft|send).{0,20}\bemail\b", r"\bback ?up (my )?(memory|vault)\b",
    r"\brun (the )?protocol\b", r"\bsearch (my )?vault\b",
)
_COMMAND_RE = re.compile("|".join(_COMMAND_PATTERNS), re.IGNORECASE)

# Anaphoric / terse follow-up commands ("set it back to X", "make it Paris", "turn it off") carry
# no object noun, so the patterns above miss them and a weak model fakes the confirmation. Catch a
# leading imperative verb (optionally after "now/actually/no/please/ok") as a command too. Scoped to
# action verbs so ordinary replies — which rarely START with these — aren't forced into a tool call.
_IMPERATIVE_RE = re.compile(
    r"^\s*(now|actually|no,?|please|ok|okay|and|then)?\s*"
    r"(set|change|update|switch|make|turn|play|send|remind|add|schedule|remember|"
    r"lock|unlock|dim|put|cancel|delete|remove|stop|start|run|back ?up|draft|reply)\b",
    re.IGNORECASE,
)


def _wants_forced_tool(user_text: str) -> bool:
    """True for clear imperative commands that must result in a tool call, not a spoken claim."""
    t = user_text or ""
    return bool(_COMMAND_RE.search(t) or _IMPERATIVE_RE.search(t))


# A short affirmation that grants a pending confirmation ("yes", "go ahead", "do it", "send it").
# Used by the confirm-tier gate: a held-back outward/destructive tool runs only after one of these.
_AFFIRM_RE = re.compile(
    r"^\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"
    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"
    r"correct|fine|absolutely|yes please|go|right)\b",
    re.IGNORECASE,
)


def _is_affirmation(text: str) -> bool:
    return bool(_AFFIRM_RE.match(text or ""))


def _clean_reply(text: str) -> str:
    text = (text or "")
    # Drop whole <tool_call>…</tool_call> blocks first, then any stray tags/tokens.
    text = re.sub(r"<tool_call>.*?</tool_call>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = _ARTIFACT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Sentence boundary for streaming: a .!?… followed by whitespace ends a speakable chunk. We feed
# whole sentences to TTS so Watari starts talking on sentence 1 while the rest still generates.
_SENT_BOUNDARY = re.compile(r"[.!?…](?=\s)")


def _pop_sentences(buf: str) -> tuple[list[str], str]:
    """Split off any COMPLETE sentences from a running buffer; return (sentences, remainder)."""
    out: list[str] = []
    while True:
        m = _SENT_BOUNDARY.search(buf)
        if not m:
            break
        idx = m.end()
        seg = buf[:idx].strip()
        if seg:
            out.append(seg)
        buf = buf[idx:].lstrip()
    return out, buf


GET_TIME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Get Vazghen's current local date and time (Germany, Europe/Berlin).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


class JarvisAgent:
    def __init__(self, max_history_turns: int = 12, max_tool_iters: int = 4) -> None:
        self._llm = LLMClient()
        self._system = {"role": "system", "content": build_system_prompt()}
        self._history: list[dict[str, Any]] = []
        self._max_history_turns = max_history_turns
        self._max_tool_iters = max_tool_iters
        # The fleet touches shared infra, so it stays off unless armed — either per-session via
        # set_fleet_authorized(True), or for a 24/7 deployment via JARVIS_FLEET_AUTHORIZED=true.
        from jarvis.config import settings as _s

        self.fleet_authorized = _s.fleet_authorized
        # Self-improvement loop (background_review): count turns; every N, spawn a background pass
        # that learns durable facts into L1 memory. Off the hot path, so it never slows a reply.
        self._turns_since_review = 0
        self._review_every = max(2, _s.self_improve_every_turns)
        self._self_improve = _s.self_improve_enabled
        # Confirmation tier ENFORCEMENT (not just a prompt rule): an outward-facing / destructive
        # tool (send_email, file_op delete, run_powershell, …) is BLOCKED on first attempt and run
        # only after Vazghen affirms. _pending_confirm holds the held-back call; _confirm_granted is
        # set for a turn whose utterance affirms a pending one. So a weak model physically cannot
        # fire a consequential tool without a yes.
        self._pending_confirm: dict | None = None
        self._confirm_granted = False
        # Smart session reset: clear stale WORKING memory after a long idle gap (durable memory kept).
        self._last_turn_at: datetime | None = None
        self._idle_reset_min = max(0, _s.session_idle_reset_minutes)
        # The handler REGISTRY is always complete — every tool can execute. What varies per turn is
        # what we ADVERTISE to the model: a lean CORE surface every turn, plus any lazy group the
        # turn needs (fine-tuning.md Item 2). _core_tools = built-ins + core schemas (the typical
        # per-turn surface). Lazy groups light up via _active_groups (with a one-turn warm decay so
        # an immediate follow-up like "reply to it" still has the tools).
        self._core_tools = [GET_TIME_SCHEMA, FLEET_TOOL_SCHEMA, *core_tool_schemas()]
        self._group_ttl: dict[str, int] = {}     # group -> turns it stays advertised
        self._tools = list(self._core_tools)     # current advertised set (core until a turn needs more)
        self._registry: dict[str, Callable] = {
            "get_time": self._tool_get_time,
            "delegate_to_fleet": self._tool_delegate,
            **tool_handlers(),
        }
        logger.info(f"tools: {len(self._core_tools)} core advertised; "
                    f"{len(self._registry)} total in registry")

    def _tools_for_turn(self, user_text: str) -> list[dict[str, Any]]:
        """Core surface + any lazy group this turn activates (or is still warm from last turn)."""
        for g in self._group_ttl:                # decay previous activations by one turn
            self._group_ttl[g] -= 1
        for g in groups_for_text(user_text):     # (re)arm groups the utterance calls for
            self._group_ttl[g] = 2               # this turn + one follow-up
        active = [g for g, ttl in self._group_ttl.items() if ttl > 0]
        self._group_ttl = {g: ttl for g, ttl in self._group_ttl.items() if ttl > 0}
        tools = list(self._core_tools)
        for g in active:
            tools.extend(group_tool_schemas(g))
        if active:
            logger.info(f"lazy tool groups active this turn: {active} (+{len(tools) - len(self._core_tools)} tools)")
        self._tools = tools
        return tools

    def _begin_turn(self, user_text: str) -> None:
        """Per-turn bookkeeping before the model runs: smart idle-reset + confirmation-grant state."""
        now = datetime.now(USER_TZ)
        self._maybe_idle_reset(now)                       # uses the PREVIOUS _last_turn_at
        # A pending confirm is granted only if THIS utterance affirms it; any other new request
        # supersedes (drops) the pending one — a "yes" must immediately follow the ask.
        self._confirm_granted = bool(self._pending_confirm) and _is_affirmation(user_text)
        if self._pending_confirm and not self._confirm_granted:
            self._pending_confirm = None
        self._last_turn_at = now

    def _maybe_idle_reset(self, now: datetime) -> None:
        if not self._idle_reset_min or not self._history or self._last_turn_at is None:
            return
        if (now - self._last_turn_at) >= timedelta(minutes=self._idle_reset_min):
            self.reset_session(reason=f"idle {int((now - self._last_turn_at).total_seconds()//60)}m")

    def reset_session(self, reason: str = "manual") -> None:
        """Smart reset: journal the prior conversation (in the background) and clear WORKING memory.
        Durable memory (L1 learned, L2 journal, L3 vault) is untouched, so he forgets the *thread*,
        not the *person*. Safe to call from voice ("start a new conversation") or on idle."""
        history = list(self._history)
        self._history = []
        self._pending_confirm = None
        self._confirm_granted = False
        if history:
            async def _run() -> None:
                try:
                    await self._journal_history(history)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"reset journal skipped: {e}")
            try:
                asyncio.get_running_loop().create_task(_run())
            except RuntimeError:
                pass  # no loop (sync context) — skip the journal, still reset
        logger.info(f"session reset ({reason}); cleared {len(history)} working messages")

    def note_proactive(self, message: str) -> None:
        """Record something Watari said UNPROMPTED (a proactive nudge or a fired reminder). It goes
        into BOTH the working history (so an immediate reply — "yes do it", "what did you mean?" —
        has context) AND the L2 journal (so Vazghen can refer back DAYS later — "that thing you
        suggested last week" — long after the 12-turn working window has rolled over)."""
        message = (message or "").strip()
        if not message:
            return
        self._history.append({"role": "assistant", "content": message})
        self._trim()
        try:
            from jarvis.brain.memory import STORE

            STORE.journal_append(f"[proactive] Watari said unprompted: {message}")
        except Exception:  # noqa: BLE001 — journalling is best-effort, never block the nudge
            pass

    def set_fleet_authorized(self, ok: bool) -> None:
        self.fleet_authorized = ok
        logger.info(f"fleet delegation {'authorized' if ok else 'disabled'} for session")

    async def warmup(self) -> None:
        """Prime the primary model so the first real turn isn't a cold ~3s TTFT."""
        # L3 vault must always be readable; L1 learned-memory readiness logged for visibility.
        try:
            from jarvis.brain.context import validate_vault
            from jarvis.brain.memory import STORE

            validate_vault()
            logger.info(f"learned memory (L1): {STORE.count()} facts")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory/vault startup check skipped: {e}")
        try:
            await self._llm.complete(
                [{"role": "system", "content": "reply with: ready"},
                 {"role": "user", "content": "ready?"}],
                temperature=0.0,
            )
            logger.info("brain warmup complete")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"brain warmup skipped: {e}")

    # ---- tools ------------------------------------------------------------------------
    async def _tool_get_time(self, _args: dict) -> str:
        now = datetime.now(USER_TZ)
        return now.strftime("%A, %d %B %Y, %H:%M") + " (Europe/Berlin)"

    async def _tool_delegate(self, args: dict) -> str:
        if not self.fleet_authorized:
            return (
                "FLEET_NOT_AUTHORIZED: tell Vazghen you can consult the OpenClaw fleet for this, "
                "but it isn't authorized this session yet — ask if he wants you to."
            )
        # Jarvis briefs the team lead (ispir) only — no per-call agent target by design.
        task = args.get("task", "")
        try:
            return await delegate_to_fleet(task, on_progress=lambda n: logger.info(f"[fleet] {n}"))
        except FleetUnavailable as e:
            return f"FLEET_UNAVAILABLE: {e}"

    # ---- main loop --------------------------------------------------------------------
    async def respond(self, user_text: str, on_progress: Callable | None = None) -> str:
        """Run one full turn (with tool calls) and return Jarvis's spoken reply text."""
        self._begin_turn(user_text)
        self._history.append({"role": "user", "content": user_text})
        messages = [self._system, *self._history]
        turn_tools = self._tools_for_turn(user_text)
        # Force a tool call on the first pass for clear commands, so a weak model can't fake it.
        force_first = _wants_forced_tool(user_text) and bool(turn_tools)

        for i in range(self._max_tool_iters):
            choice = "required" if (i == 0 and force_first) else "auto"
            try:
                msg = await self._llm.complete(messages, tools=turn_tools, tool_choice=choice)
            except RuntimeError:
                # A model in the chain may reject forced tool_choice — retry this pass on "auto".
                if choice == "auto":
                    raise
                msg = await self._llm.complete(messages, tools=turn_tools, tool_choice="auto")
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                reply = _clean_reply(msg.content or "")
                # Never persist an empty assistant turn: with no content AND no tool_calls it's an
                # invalid message that some upstream models reject (400) when the history is replayed
                # next turn. Fall back to a spoken acknowledgement instead.
                stored = reply or "Sorry sir, I didn't catch that — could you say it again?"
                self._history.append({"role": "assistant", "content": stored})
                self._trim()
                self._spawn_review()
                return reply or stored

            # Record the assistant's tool-call turn, then execute each call (shared with the
            # streaming path) — normalise the OpenAI objects to plain dicts first.
            calls = [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                for tc in tool_calls
            ]
            await self._execute_calls(messages, calls, msg.content or "", on_progress)

        # Tool-iteration budget exhausted — final no-tools pass so he speaks a summary, not
        # another tool call. The nudge steers models that would otherwise emit a raw tool-call.
        messages.append({
            "role": "system",
            "content": "Now reply to Vazghen in one or two spoken sentences, summarising what you "
                       "did and what you found. Do NOT call or write any tool calls.",
        })
        msg = await self._llm.complete(messages)
        reply = _clean_reply(msg.content or "") or "I've done what I can on that, sir."
        self._history.append({"role": "assistant", "content": reply})
        self._trim()
        self._spawn_review()
        return reply

    async def _execute_calls(
        self,
        messages: list[dict[str, Any]],
        calls: list[dict[str, Any]],
        assistant_content: str = "",
        on_progress: Callable | None = None,
    ) -> None:
        """Append the assistant's tool-call turn, run each tool, append the results. Mutates
        ``messages``. Shared by both the blocking (``respond``) and streaming (``respond_stream``)
        paths so tool behaviour, error recovery, and the audit trail stay identical."""
        messages.append({
            "role": "assistant",
            "content": assistant_content or "",
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls
            ],
        })
        from jarvis.brain import audit
        from jarvis.brain.proactive import confirm_required
        for c in calls:
            name = c["name"]
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            # Confirmation tier: an outward-facing / destructive tool is BLOCKED until Vazghen has
            # affirmed it. We don't execute — we hand the model a sentinel so it reads the action
            # back and asks; the held call runs next turn once _confirm_granted (set by an
            # affirmation). One "yes" authorises ONE action (grant consumed below).
            if confirm_required(name, args) and not self._confirm_granted:
                self._pending_confirm = {"name": name, "args": args}
                blocked = (
                    "CONFIRM_REQUIRED — do NOT say this is done. In one sentence tell Vazghen "
                    "exactly what you're about to do (the action and its target or recipient) and "
                    "ask him to confirm. It will run only after he says yes."
                )
                logger.info(f"confirm-gate: held {name}({args}) pending Vazghen's yes")
                audit.record(name, args, "blocked: confirmation required", ok=False)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": blocked})
                continue
            if on_progress and name in _TOOL_PROGRESS:
                on_progress(_TOOL_PROGRESS[name])
            fn = self._registry.get(name)
            # A tool that raises must NOT crash the turn: turn it into a recoverable result the
            # model can apologise for and work around, and record the failure in the audit log.
            if fn is None:
                result, ok = f"unknown tool {name}", False
            else:
                try:
                    result, ok = await fn(args), True
                except Exception as e:  # noqa: BLE001 — degrade, don't die
                    logger.exception(f"tool {name} raised")
                    result = (f"That tool ({name}) hit an error: {type(e).__name__}. "
                              "Tell Vazghen briefly that it failed and carry on.")
                    ok = False
            logger.info(f"tool {name}({args}) -> {str(result)[:80]}")
            audit.record(name, args, str(result), ok=ok)
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": str(result)})
            # A confirmed consequential action consumes the grant: one "yes" authorises one action,
            # never a chain of them.
            if confirm_required(name, args):
                self._confirm_granted = False
                self._pending_confirm = None

    async def respond_stream(self, user_text: str, on_progress: Callable | None = None):
        """Streaming twin of ``respond``: yields spoken sentences AS they generate, so TTS can
        start on sentence 1 while the model is still writing. Resolves tool calls between passes
        exactly like ``respond``. Yields ``str`` chunks; persists the full reply to history."""
        self._begin_turn(user_text)
        self._history.append({"role": "user", "content": user_text})
        messages = [self._system, *self._history]
        turn_tools = self._tools_for_turn(user_text)
        force_first = _wants_forced_tool(user_text) and bool(turn_tools)
        spoken: list[str] = []

        def _finish(default: str) -> None:
            final = " ".join(spoken).strip() or default
            self._history.append({"role": "assistant", "content": final})
            self._trim()
            self._spawn_review()

        for i in range(self._max_tool_iters):
            choice = "required" if (i == 0 and force_first) else "auto"
            attempts = [choice] if choice == "auto" else [choice, "auto"]
            buf, calls, preamble = "", None, []
            for attempt in attempts:
                buf, calls, preamble = "", None, []
                try:
                    async for kind, payload in self._llm.stream_with_tools(
                        messages, tools=turn_tools, tool_choice=attempt
                    ):
                        if kind == "text":
                            buf += payload
                            sents, buf = _pop_sentences(buf)
                            for s in sents:
                                cs = _clean_reply(s)
                                if cs:
                                    preamble.append(cs)
                                    spoken.append(cs)
                                    yield cs
                        else:  # ("tools", calls)
                            calls = payload
                    break  # this attempt succeeded
                except RuntimeError:
                    if attempt == "auto":
                        raise
                    continue  # forced tool_choice rejected by every model — retry on auto

            if not calls:
                tail = _clean_reply(buf)
                if tail:
                    spoken.append(tail)
                    yield tail
                _finish("Sorry sir, I didn't catch that — could you say it again?")
                return

            await self._execute_calls(messages, calls, " ".join(preamble), on_progress)

        # Budget exhausted — one final no-tools summary pass, also streamed.
        messages.append({
            "role": "system",
            "content": "Now reply to Vazghen in one or two spoken sentences, summarising what you "
                       "did and what you found. Do NOT call or write any tool calls.",
        })
        buf = ""
        async for kind, payload in self._llm.stream_with_tools(messages):
            if kind == "text":
                buf += payload
                sents, buf = _pop_sentences(buf)
                for s in sents:
                    cs = _clean_reply(s)
                    if cs:
                        spoken.append(cs)
                        yield cs
        tail = _clean_reply(buf)
        if tail:
            spoken.append(tail)
            yield tail
        _finish("I've done what I can on that, sir.")

    def _trim(self) -> None:
        # Keep the last N turns (user+assistant pairs) to bound context.
        max_msgs = self._max_history_turns * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

    def _spawn_review(self) -> None:
        """Self-improvement: every N turns, kick off a background pass that learns durable facts into
        L1 memory. Fire-and-forget so the reply is never delayed; a snapshot of history is passed so
        the review is stable even as the conversation moves on."""
        if not self._self_improve:
            return
        self._turns_since_review += 1
        if self._turns_since_review < self._review_every:
            return
        self._turns_since_review = 0
        history = list(self._history)

        async def _run() -> None:
            from jarvis.brain.background_review import review_and_learn
            await review_and_learn(history, self._llm)

        try:
            asyncio.get_running_loop().create_task(_run())
        except RuntimeError:
            pass  # no running loop (sync context) — skip; end_session still reviews

    async def _journal_history(self, history: list[dict[str, Any]]) -> str | None:
        """Summarise a conversation to the L2 journal (+ distil L1 facts). Shared by end_session and
        the smart reset, so both paths preserve continuity the same way. Best-effort."""
        from jarvis.brain.memory import STORE

        user_turns = [m for m in history if m.get("role") == "user"]
        if len(user_turns) < 2:
            return None  # nothing worth journalling
        try:
            convo = "\n".join(f"{m['role']}: {m['content']}" for m in history if m.get("content"))
            msg = await self._llm.complete(
                [
                    {"role": "system", "content": "Summarise this conversation in ONE sentence for "
                     "the assistant's private journal: what Vazghen wanted, what was done, and any "
                     "open thread. Third person, past tense, no preamble."},
                    {"role": "user", "content": convo[:6000]},
                ],
                temperature=0.2,
            )
            summary = _clean_reply(msg.content or "")
            if summary:
                STORE.journal_append(summary)
            if self._self_improve:
                try:
                    from jarvis.brain.background_review import review_and_learn
                    await review_and_learn(list(history), self._llm)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"journal self-improve skipped: {e}")
            return summary or None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"journal skipped: {e}")
        return None

    async def end_session(self) -> str | None:
        """Summarise this conversation to the L2 journal for continuity. Best-effort."""
        return await self._journal_history(self._history)
