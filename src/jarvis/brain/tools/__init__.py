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
    channels,
    coding,
    composio,
    contacts,
    documents,
    gmail,
    localplay,
    macros,
    memory,
    multimodal,
    music,
    notify,
    notion,
    protocols,
    reminders,
    routines,
    skills,
    smarthome,
    system,
    tasks,
    telegram,
    undo,
    utility,
    vault,
    voicechat,
    web,
)

_MODULES = [vault, memory, web, telegram, voicechat, music, localplay, system, browser,
            protocols, reminders, notify, gmail, calendar, smarthome, utility, routines,
            coding, skills, notion, tasks, contacts, documents, composio, channels,
            macros, multimodal, undo]  # noqa: E501

Handler = Callable[[dict], Awaitable[str]]

# --- Lazy tool groups (fine-tuning.md Item 2) ---------------------------------------------
# Every handler is ALWAYS in the registry below (so tests, the proactive engine, and direct
# handler calls keep working). These groups are about what the AGENT *advertises to the model on a
# given turn*: low-frequency modules are held back until the turn actually needs them, keeping the
# per-turn schema surface lean. No capability is removed — a group simply lights up when relevant.
_LAZY_GROUPS: dict[str, list] = {
    "coding": [coding],                  # read/write source, tests, lint, git — only for dev work
    "office": [notion, gmail, calendar],  # email, calendar, Notion — when he asks about them
    "home": [smarthome, voicechat],      # smart-home control + Telegram music-room streaming
    "docs": [documents],                 # read a local document + answer questions grounded in it
    "apps": [composio],                  # 250+ external apps via Composio (GitHub/Slack/Drive/...)
    "channels": [channels],              # YouTube channel ops (list / random / latest) — T1
    "macros": [macros],                  # User-defined macro sequences + if_then — T2
}
# Substring triggers (lowercased) that activate a group for a turn. Broad on purpose — a miss just
# means a one-turn delay (the follow-up usually contains the word, and groups stay warm one turn).
LAZY_GROUP_TRIGGERS: dict[str, tuple[str, ...]] = {
    "coding": ("code", "coding", "source", "function", "bug", "refactor", "commit", "git ",
               "lint", "unit test", "run the test", "run tests", "repo", "push", "branch",
               "revert", "your code", "self-improve", "self improve", "improve yourself",
               "pull request", "diff", "the suite"),
    "office": ("email", "e-mail", "mail", "inbox", "gmail", "draft", "calendar", "schedule",
               "event", "meeting", "appointment", "agenda", "notion", "document", "page",
               "task list", "my tasks", "task", "tasks", "deadline", "due", "to-do", "todo",
               "to do", "on my plate", "what's due", "whats due", "what do i need to do",
               "what needs", "dashboard", "overdue"),
    "home": ("smart home", "home assistant", "light", "lamp", "thermostat", "heating", "lock",
             "unlock", "music room", "voice chat", "stream music", "play in the room"),
    "docs": ("document", "this file", "read this", "the pdf", "a pdf", "the doc", "this doc",
             "in the file", "ask the document", "close the document", "read the file",
             "this report", "the attachment"),
    "apps": ("github", "gitlab", "slack", "discord", "google drive", "gdrive", "google doc",
             "google sheet", "spreadsheet", "stripe", "linear", "jira", "trello", "asana",
             "airtable", "reddit", "youtube", "linkedin", "instagram", "coinbase", "supabase",
             "hubspot", "salesforce", "calendly", "an issue", "a pr", "pull request",
             "post a message", "send a message to", "add a row", "create a channel", "in slack",
             "on github", "to slack", "a repo", "my repos"),
    "channels": ("youtube channel", "channel ", "from channel", "random video", "random from",
                 "latest from", "latest video", "what's new on", "new from", "upload from",
                 "of videos", "lofi girl", "veritasium", "mrbeast"),
    "macros": ("macro", "macros", "routine", "morning routine", "evening routine", "shortcut",
               "if then", "if ", "branching", "every morning", "every day at", "recurring",
               "set up a"),
}


def _schemas_of(mods: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mod in mods:
        out.extend(mod.SCHEMAS)
    return out


def tool_schemas() -> list[dict[str, Any]]:
    """The FULL registry of schemas (every group). Used by tests + the report's registry view."""
    return _schemas_of(_MODULES)


def core_tool_schemas() -> list[dict[str, Any]]:
    """Schemas advertised on every turn (core groups only) — the lean per-turn surface."""
    return _schemas_of(CORE_MODULES)


def group_tool_schemas(group: str) -> list[dict[str, Any]]:
    """Schemas for one lazy group, added to a turn when that group activates."""
    return _schemas_of(_LAZY_GROUPS.get(group, []))


def groups_for_text(text: str) -> set[str]:
    """Which lazy groups a user utterance should activate (substring trigger match)."""
    t = (text or "").lower()
    return {g for g, kws in LAZY_GROUP_TRIGGERS.items() if any(k in t for k in kws)}


def tool_handlers() -> dict[str, Handler]:
    handlers: dict[str, Handler] = {}
    for mod in _MODULES:
        handlers.update(mod.HANDLERS)
    return handlers


def tool_names() -> list[str]:
    return [s["function"]["name"] for s in tool_schemas()]


_LAZY_MODULES = {m for mods in _LAZY_GROUPS.values() for m in mods}
# Core modules are advertised on every turn; lazy ones only when their group is active.
CORE_MODULES = [m for m in _MODULES if m not in _LAZY_MODULES]
