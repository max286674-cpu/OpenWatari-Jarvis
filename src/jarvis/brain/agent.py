"""JarvisAgent — Jarvis's own reasoning loop: personality + memory + tools + session.

He answers as himself first. Tools are things he reaches for (the current time; the
OpenClaw fleet for deep work) — never a change of identity. Conversation history is kept
so he remembers the flow across turns ("what did I just ask you?").
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from jarvis.brain.context import build_system_prompt
from jarvis.brain.fleet import FLEET_TOOL_SCHEMA, FleetUnavailable, delegate_to_fleet
from jarvis.brain.llm import LLMClient
from jarvis.brain.tools import tool_handlers, tool_schemas

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
    "spotify": "On Spotify…",
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


def _clean_reply(text: str) -> str:
    text = (text or "")
    # Drop whole <tool_call>…</tool_call> blocks first, then any stray tags/tokens.
    text = re.sub(r"<tool_call>.*?</tool_call>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = _ARTIFACT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
        # Built-ins + the Phase 3 knowledge/channel tools (vault, web, telegram, spotify).
        # Every Phase 3 tool self-degrades when unconfigured, so registering all is safe.
        self._tools = [GET_TIME_SCHEMA, FLEET_TOOL_SCHEMA, *tool_schemas()]
        self._registry: dict[str, Callable] = {
            "get_time": self._tool_get_time,
            "delegate_to_fleet": self._tool_delegate,
            **tool_handlers(),
        }
        logger.info(f"tools registered: {[s['function']['name'] for s in self._tools]}")

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
        self._history.append({"role": "user", "content": user_text})
        messages = [self._system, *self._history]

        for _ in range(self._max_tool_iters):
            msg = await self._llm.complete(messages, tools=self._tools)
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                reply = _clean_reply(msg.content or "")
                self._history.append({"role": "assistant", "content": reply})
                self._trim()
                return reply

            # Record the assistant's tool-call turn, then execute each call.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if on_progress and name in _TOOL_PROGRESS:
                    on_progress(_TOOL_PROGRESS[name])
                fn = self._registry.get(name)
                result = await fn(args) if fn else f"unknown tool {name}"
                logger.info(f"tool {name}({args}) -> {str(result)[:80]}")
                # Audit trail — best-effort, secrets redacted (see brain/audit.py).
                from jarvis.brain import audit

                audit.record(name, args, str(result), ok=fn is not None)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

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
        return reply

    def _trim(self) -> None:
        # Keep the last N turns (user+assistant pairs) to bound context.
        max_msgs = self._max_history_turns * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

    async def end_session(self) -> str | None:
        """Summarise this conversation to the L2 journal for continuity. Best-effort."""
        from jarvis.brain.memory import STORE

        user_turns = [m for m in self._history if m.get("role") == "user"]
        if len(user_turns) < 2:
            return None  # nothing worth journalling
        try:
            convo = "\n".join(
                f"{m['role']}: {m['content']}" for m in self._history if m.get("content")
            )
            msg = await self._llm.complete(
                [
                    {"role": "system", "content": "Summarise this conversation in ONE sentence for "
                     "Jarvis's private journal: what Vazghen wanted, what was done, and any open "
                     "thread. Third person, past tense, no preamble."},
                    {"role": "user", "content": convo[:6000]},
                ],
                temperature=0.2,
            )
            summary = _clean_reply(msg.content or "")
            if summary:
                STORE.journal_append(summary)
                return summary
        except Exception as e:  # noqa: BLE001
            logger.warning(f"end_session journal skipped: {e}")
        return None
