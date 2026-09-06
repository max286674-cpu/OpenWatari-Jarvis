"""Jarvis tool registry."""
from __future__ import annotations
from typing import Any, Awaitable, Callable
from jarvis.brain.tools import activity, approvals, browser, calendar, camera, channels, coaching, coding, composio, contacts, desktop, documents, gmail, graphmem, localplay, macros, memory, multimodal, music, notify, notion, objectives, protocols, reminders, relationship, routines, skills, smarthome, system, tasks, telegram, undo, utility, vault, voicechat, web

_MODULES = [vault, memory, web, telegram, voicechat, music, localplay, system, desktop, browser, protocols, reminders, notify, gmail, calendar, smarthome, utility, routines, coding, skills, notion, tasks, contacts, documents, composio, channels, macros, multimodal, undo, graphmem, activity, coaching, camera, objectives, approvals, relationship]

Handler = Callable[[dict], Awaitable[str]]

_LAZY_GROUPS: dict[str, list] = {
    "coding": [coding], "office": [notion, gmail, calendar], "home": [smarthome, voicechat],
    "docs": [documents], "apps": [composio], "channels": [channels], "macros": [macros],
    "screen": [multimodal, desktop], "camera": [camera], "undo": [undo], "graph": [graphmem],
    "activity": [activity], "coaching": [coaching], "objectives": [objectives],
    "approvals": [approvals], "relationship": [relationship],
}

LAZY_GROUP_TRIGGERS: dict[str, tuple[str, ...]] = {
    "coding": ("code","coding","source","function","bug","refactor","commit","git ","lint","test","repo","github"),
    "office": ("email","mail","inbox","gmail","calendar","schedule","event","meeting","appointment","notion","document","task"),
    "home": ("smart home","home assistant","light","lamp","thermostat","heating","lock","unlock","music room","voice chat"),
    "docs": ("document","this file","read this","pdf","doc","report","attachment"),
    "apps": ("github","gitlab","slack","discord","google drive","google doc","google sheet","spreadsheet","jira","trello","asana","youtube"),
    "channels": ("youtube channel","latest video","random video","channel "),
    "macros": ("macro","routine","shortcut","if then","every morning","every day"),
    "screen": ("screen","screenshot","display","look at my","on my screen","what am i looking"),
    "camera": ("camera","webcam","look around","can you see","look through"),
    "undo": ("undo","revert","roll back","recent actions","last action"),
    "graph": ("related to","connected to","connection between","linked to","relationship between","knowledge graph"),
    "activity": ("screen time","screentime","what am i doing","productivity","activity tracking"),
    "coaching": ("quiz me","test me","practice","german","french","spanish","coaching","vocabulary"),
    "objectives": ("objective","take this on","own this","drive this","long-term goal","multi-day"),
    "approvals": ("approve","approval","pending action","go ahead and send","authorize","reject that"),
    "relationship": ("sensitive subject","running joke","inside joke","read the room","handle gently"),
}

def _schemas_of(mods: list) -> list[dict[str, Any]]:
    out=[]
    for mod in mods: out.extend(mod.SCHEMAS)
    return out

def tool_schemas() -> list[dict[str, Any]]: return _schemas_of(_MODULES)
def core_tool_schemas() -> list[dict[str, Any]]: return _schemas_of(CORE_MODULES)
def group_tool_schemas(group: str) -> list[dict[str, Any]]: return _schemas_of(_LAZY_GROUPS.get(group, []))
def groups_for_text(text: str) -> set[str]:
    t=(text or "").lower(); return {g for g,kws in LAZY_GROUP_TRIGGERS.items() if any(k in t for k in kws)}
def schemas_by_name(names) -> list[dict[str, Any]]:
    want=set(names); return [s for s in tool_schemas() if s["function"]["name"] in want]
def tool_handlers() -> dict[str, Handler]:
    handlers={}
    for mod in _MODULES: handlers.update(mod.HANDLERS)
    return handlers
def tool_names() -> list[str]: return [s["function"]["name"] for s in tool_schemas()]

_LAZY_MODULES = {m for mods in _LAZY_GROUPS.values() for m in mods}
CORE_MODULES = [m for m in _MODULES if m not in _LAZY_MODULES]
