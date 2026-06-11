"""Jarvis's Phase 3 tool registry — knowledge & channels.

Each tool module exposes ``SCHEMAS`` (OpenAI function schemas the LLM sees) and ``HANDLERS``
(name -> async ``handler(args: dict) -> str``). The agent merges these with its built-ins
(get_time, delegate_to_fleet). Every handler degrades gracefully when its integration isn't
configured, so the full set can always be registered safely (see ``tools/base.py``).

Adding a capability = drop a module here and list it in ``_MODULES``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from jarvis.brain.tools import (
    browser,
    calendar,
    coding,
    gmail,
    localplay,
    memory,
    music,
    notify,
    protocols,
    reminders,
    routines,
    skills,
    smarthome,
    spotify,
    system,
    telegram,
    utility,
    vault,
    voicechat,
    web,
)

_MODULES = [vault, memory, web, telegram, voicechat, spotify, music, localplay, system, browser,
            protocols, reminders, notify, gmail, calendar, smarthome, utility, routines,
            coding, skills]

Handler = Callable[[dict], Awaitable[str]]


def tool_schemas() -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for mod in _MODULES:
        schemas.extend(mod.SCHEMAS)
    return schemas


def tool_handlers() -> dict[str, Handler]:
    handlers: dict[str, Handler] = {}
    for mod in _MODULES:
        handlers.update(mod.HANDLERS)
    return handlers


def tool_names() -> list[str]:
    return [s["function"]["name"] for s in tool_schemas()]
