"""JarvisAgent — Jarvis's own reasoning loop: personality + memory + tools + session.

He answers as himself first. Tools are things he reaches for (the current time; the
OpenClaw fleet for deep work) — never a change of identity. Conversation history is kept
so he remembers the flow across turns ("what did I just ask you?").
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from jarvis.brain.context import build_system_prompt
from jarvis.brain.fleet import FLEET_TOOL_SCHEMA, FleetUnavailable, delegate_to_fleet
from jarvis.brain.llm import LLMClient

# Vazghen is in Germany (UTC+1). Used for time/greeting/scheduling.
USER_TZ = ZoneInfo("Europe/Berlin")

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
        # The fleet touches shared infra, so it stays off until the user authorizes it
        # for the session (set_fleet_authorized(True)).
        self.fleet_authorized = False
        self._tools = [GET_TIME_SCHEMA, FLEET_TOOL_SCHEMA]
        self._registry: dict[str, Callable] = {
            "get_time": self._tool_get_time,
            "delegate_to_fleet": self._tool_delegate,
        }

    def set_fleet_authorized(self, ok: bool) -> None:
        self.fleet_authorized = ok
        logger.info(f"fleet delegation {'authorized' if ok else 'disabled'} for session")

    async def warmup(self) -> None:
        """Prime the primary model so the first real turn isn't a cold ~3s TTFT."""
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
        task = args.get("task", "")
        agent = args.get("agent") or None
        try:
            return await delegate_to_fleet(task, agent=agent, on_progress=lambda n: logger.info(f"[fleet] {n}"))
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
                reply = (msg.content or "").strip()
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
                if on_progress and name == "delegate_to_fleet":
                    on_progress("Let me consult the specialists on that…")
                fn = self._registry.get(name)
                result = await fn(args) if fn else f"unknown tool {name}"
                logger.info(f"tool {name}({args}) -> {str(result)[:80]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

        # Tool-iteration budget exhausted — make a final no-tools pass so he still speaks.
        msg = await self._llm.complete(messages)
        reply = (msg.content or "I'm not sure how to answer that, sir.").strip()
        self._history.append({"role": "assistant", "content": reply})
        self._trim()
        return reply

    def _trim(self) -> None:
        # Keep the last N turns (user+assistant pairs) to bound context.
        max_msgs = self._max_history_turns * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]
