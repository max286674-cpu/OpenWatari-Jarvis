"""Tools to inspect the background task queue — Watari's status-keeping.

Read-only (no confirm-gate): list what's running and report the status/progress of a given task.
The heavy lifting (enqueuing fleet work in the background) is wired into the fleet delegation tool;
these tools are how you ask "what are you working on?" / "how's the website going?".
"""

from __future__ import annotations

from jarvis.brain.tasks import TASKS


async def list_tasks(_args: dict) -> str:
    active = TASKS.active()
    if not active:
        return "Nothing running in the background right now, sir."
    lines = [f"{len(active)} task(s) in progress, sir:"]
    lines += [f"- {TASKS.summary_line(t)}" for t in active]
    return "\n".join(lines)


async def task_status(args: dict) -> str:
    topic = (args.get("topic") or args.get("id") or "").strip()
    # Direct id hit first.
    t = TASKS.get(topic) if topic else None
    if t:
        return TASKS.summary_line(t)
    matches = TASKS.find(topic)
    if not matches:
        return "I don't have any background tasks matching that, sir."
    if len(matches) == 1:
        return TASKS.summary_line(matches[0])
    return "A few match, sir:\n" + "\n".join(f"- {TASKS.summary_line(t)}" for t in matches)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": ("List the background tasks Watari is currently running (e.g. fleet "
                            "delegations), with how long each has been going and its latest status. "
                            "Use for 'what are you working on?' / 'anything still running?'."),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_status",
            "description": ("Report the status/progress of a background task by a word from its "
                            "description (or its id). Use for 'how's the website going?' / "
                            "'is that done yet?'."),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string",
                              "description": "A word from the task (e.g. 'website') or its id."}
                },
                "required": ["topic"],
            },
        },
    },
]

HANDLERS = {"list_tasks": list_tasks, "task_status": task_status}
