"""Notion tools — read, write, and comment on Vazghen's Notion pages (Phase 11+).

Uses a Notion **internal integration** token: create one at https://www.notion.so/my-integrations,
then **share** the specific pages/databases you want Jarvis to touch with that integration (Notion is
deny-by-default — the integration only ever sees pages explicitly shared with it, which is the right
safety boundary). Set ``JARVIS_NOTION_TOKEN``.

Tools: ``notion_search`` (find a page), ``notion_read_page`` (read its text), ``notion_append``
(add content — write), ``notion_comment`` (leave a comment), ``notion_create_page`` (new sub-page).
Writes/comments are confirm-gated. Everything degrades to a spoken note until the token is set.
"""

from __future__ import annotations

from jarvis.brain.tools.base import clip, not_configured, tool_error
from jarvis.config import settings

_API = "https://api.notion.com/v1"
_NEEDS = "a Notion integration token (JARVIS_NOTION_TOKEN) and the page shared with the integration"


def _configured() -> bool:
    return bool(settings.notion_token)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": settings.notion_version,
        "Content-Type": "application/json",
    }


async def _post(path: str, json: dict) -> dict:
    from jarvis.brain.tools.base import http_post

    r = await http_post(f"{_API}{path}", headers=_headers(), json=json)
    return r.json()


async def _get(path: str) -> dict:
    from jarvis.brain.tools.base import http_get

    r = await http_get(f"{_API}{path}", headers=_headers())
    return r.json()


async def _patch(path: str, json: dict) -> dict:
    from jarvis.brain.tools.base import http_patch

    r = await http_patch(f"{_API}{path}", headers=_headers(), json=json)
    return r.json()


def _rich_text(blocks_or_rich) -> str:
    """Flatten a Notion rich_text array to plain text."""
    out = []
    for rt in blocks_or_rich or []:
        txt = (rt.get("plain_text") or rt.get("text", {}).get("content") or "")
        if txt:
            out.append(txt)
    return "".join(out)


def _title_of(page: dict) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            t = _rich_text(prop.get("title"))
            if t:
                return t
    # database results expose the title differently
    return _rich_text(page.get("title")) or "(untitled)"


async def notion_search(args: dict) -> str:
    if not _configured():
        return not_configured("Notion", _NEEDS)
    query = (args.get("query") or "").strip()
    try:
        data = await _post("/search", {"query": query, "page_size": 8})
        results = data.get("results") or []
        if not results:
            return f"No Notion pages matching '{query}', sir." if query else "No shared Notion pages, sir."
        lines = []
        for r in results[:8]:
            kind = r.get("object", "page")
            lines.append(f"{_title_of(r)} [{kind} {r.get('id', '')[:8]}]")
        return f"Found {len(lines)} in Notion, sir: " + "; ".join(lines)
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion search", e)


async def notion_read_page(args: dict) -> str:
    if not _configured():
        return not_configured("Notion", _NEEDS)
    page_id = (args.get("page_id") or "").strip()
    if not page_id:
        return "Which Notion page, sir? Give me its id (search for it first if needed)."
    try:
        data = await _get(f"/blocks/{page_id}/children?page_size=100")
        texts: list[str] = []
        for b in data.get("results") or []:
            bt = b.get("type", "")
            payload = b.get(bt, {})
            txt = _rich_text(payload.get("rich_text"))
            if txt:
                prefix = "• " if "list_item" in bt else ("# " if bt.startswith("heading") else "")
                texts.append(prefix + txt)
        body = "\n".join(texts)
        return clip(body, 4000) if body else "That page has no readable text blocks, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion read", e)


async def notion_append(args: dict) -> str:
    if not _configured():
        return not_configured("Notion", _NEEDS)
    page_id = (args.get("page_id") or "").strip()
    text = (args.get("text") or "").strip()
    if not (page_id and text):
        return "I need a page id and the text to add, sir."
    try:
        await _post(f"/blocks/{page_id}/children", {
            "children": [{
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
            }],
        })
        return "Added that to the Notion page, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion write", e)


async def notion_comment(args: dict) -> str:
    if not _configured():
        return not_configured("Notion", _NEEDS)
    page_id = (args.get("page_id") or "").strip()
    text = (args.get("text") or "").strip()
    if not (page_id and text):
        return "I need a page id and the comment text, sir."
    try:
        await _post("/comments", {
            "parent": {"page_id": page_id},
            "rich_text": [{"type": "text", "text": {"content": text[:1900]}}],
        })
        return "Comment posted on the Notion page, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion comment", e)


async def notion_create_page(args: dict) -> str:
    if not _configured():
        return not_configured("Notion", _NEEDS)
    parent_id = (args.get("parent_id") or "").strip()
    title = (args.get("title") or "").strip()
    content = (args.get("content") or "").strip()
    if not (parent_id and title):
        return "I need a parent page id and a title, sir."
    try:
        body: dict = {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        }
        if content:
            body["children"] = [{
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content[:1900]}}]},
            }]
        await _post("/pages", body)
        return f"Created the Notion page '{title}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion create", e)


def _prop_value(prop: dict):
    """Extract a plain value from a Notion property cell (date->iso str, status/select->name, etc.)."""
    t = prop.get("type")
    v = prop.get(t)
    if t == "date":
        return (v or {}).get("start")
    if t in ("status", "select"):
        return (v or {}).get("name")
    if t == "checkbox":
        return bool(v)
    if t == "title":
        return _rich_text(v)
    if t == "formula":
        f = v or {}
        return f.get("string") or f.get("date", {}).get("start") if isinstance(f.get("date"), dict) else f.get("string")
    return None


def _detect_props(schema: dict) -> dict:
    """From a DB schema, guess which properties are the title, the deadline date, and the done/status."""
    props = schema.get("properties") or {}
    title = date_prop = status_prop = None
    for name, meta in props.items():
        tp = meta.get("type")
        low = name.lower()
        if tp == "title":
            title = name
        elif tp == "date" and (date_prop is None or any(k in low for k in ("deadline", "due", "date"))):
            date_prop = name
        elif tp in ("status", "checkbox") and (status_prop is None or any(
                k in low for k in ("status", "done", "complete", "state"))):
            status_prop = name
    return {"title": title, "date": date_prop, "status": status_prop}


def _is_done(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val or "").strip().lower() in {"done", "complete", "completed", "closed", "archived"}


# The Tasks DB has no native recurrence field, so a task is treated as RECURRING when its title says
# so ("water plants daily", "weekly review", "every morning"). Heuristic + additive: a miss just
# means it isn't called out as recurring, never a wrong action.
_RECURRING_HINTS = ("recurring", "daily", "weekly", "monthly", "every day", "every week",
                    "every morning", "every evening", "each day", "each week", "every month")


def _is_recurring(title: str) -> bool:
    t = (title or "").lower()
    return any(h in t for h in _RECURRING_HINTS)


async def notion_tasks(args: dict) -> str:
    """Read the tasks dashboard DB and report what's due (today / overdue / upcoming), by voice."""
    if not _configured():
        return not_configured("Notion", _NEEDS)
    db_id = (args.get("database_id") or settings.notion_tasks_db_id or "").strip()
    if not db_id:
        return ("No tasks database is configured yet, sir. Share your tasks dashboard with the "
                "'Personal Assistant' integration in Notion, then set JARVIS_NOTION_TASKS_DB_ID.")
    scope = (args.get("scope") or "today").strip().lower()
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    try:
        schema = await _get(f"/databases/{db_id}")
        p = _detect_props(schema)
        data = await _post(f"/databases/{db_id}/query", {"page_size": 100})
        overdue: list[str] = []
        due_today: list[str] = []
        upcoming: list[tuple[date, str]] = []
        recurring: list[str] = []
        for page in data.get("results") or []:
            props = page.get("properties") or {}
            title = _prop_value(props.get(p["title"], {})) or "(untitled)" if p["title"] else _title_of(page)
            if p["status"] and _is_done(_prop_value(props.get(p["status"], {}))):
                continue  # skip completed
            if _is_recurring(title):
                recurring.append(title)
            dstr = _prop_value(props.get(p["date"], {})) if p["date"] else None
            if not dstr:
                continue
            try:
                d = datetime.fromisoformat(dstr.replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if d < today:
                overdue.append(f"{title} ({(today - d).days}d overdue)")
            elif d == today:
                due_today.append(title)
            elif d <= today + timedelta(days=7):
                upcoming.append((d, title))
        upcoming.sort()
        parts: list[str] = []
        if scope in ("today", "open", "all") and overdue:
            parts.append(f"{len(overdue)} overdue, sir: " + "; ".join(overdue[:6]))
        if scope in ("today", "open", "all"):
            parts.append(f"{len(due_today)} due today" + (": " + "; ".join(due_today[:8]) if due_today else ""))
        if scope in ("week", "upcoming", "open", "all") and upcoming:
            parts.append("this week: " + "; ".join(f"{t} ({d.strftime('%a')})" for d, t in upcoming[:8]))
        # Recurring tasks are surfaced for the broader scopes (and on the morning briefing, which uses
        # 'open') so standing routines get a voice reminder even without a per-day deadline.
        if scope in ("week", "upcoming", "open", "all") and recurring:
            uniq = list(dict.fromkeys(recurring))  # de-dupe, keep order
            parts.append("recurring: " + "; ".join(uniq[:6]))
        if not parts or (not overdue and not due_today and not upcoming and not recurring):
            return "Nothing due, sir — you're clear for today."
        return ". ".join(parts) + "."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion tasks", e)


def _schema_map(schema: dict) -> dict:
    """Map a tasks-DB schema to roles by type + name heuristics (title/date/status/priority/etc.)."""
    props = schema.get("properties") or {}
    m: dict = {"title": None, "date": None, "status": None, "status_options": [],
               "status_done": None, "select": None, "select_options": [],
               "multi_select": None, "multi_options": [], "rich_text": None}
    for name, meta in props.items():
        tp = meta.get("type")
        low = name.lower()
        if tp == "title":
            m["title"] = name
        elif tp == "date" and (m["date"] is None or any(k in low for k in ("deadline", "due", "date"))):
            m["date"] = name
        elif tp == "status" and (m["status"] is None or "status" in low):
            m["status"] = name
            m["status_options"] = [o["name"] for o in meta.get("status", {}).get("options", [])]
            for o in m["status_options"]:
                if o.lower() in {"done", "complete", "completed", "closed"}:
                    m["status_done"] = o
        elif tp == "select" and m["select"] is None:
            m["select"] = name
            m["select_options"] = [o["name"] for o in meta.get("select", {}).get("options", [])]
        elif tp == "multi_select" and m["multi_select"] is None:
            m["multi_select"] = name
            m["multi_options"] = [o["name"] for o in meta.get("multi_select", {}).get("options", [])]
        elif tp == "rich_text" and m["rich_text"] is None:
            m["rich_text"] = name
    return m


def _match_option(value, options: list[str]):
    """Map a user value to one of the DB's option names, tolerating typos (e.g. 'high' -> 'Hight')."""
    if not value or not options:
        return None
    v = str(value).strip().lower()
    for o in options:
        if o.lower() == v:
            return o
    for o in options:
        if v in o.lower() or o.lower() in v:
            return o
    for o in options:
        if v[:3] and o.lower().startswith(v[:3]):
            return o
    return None


def _build_task_props(m: dict, args: dict, *, for_create: bool) -> dict:
    """Construct a Notion properties payload for create/update from natural fields."""
    props: dict = {}
    title = (args.get("title") or args.get("task") or "").strip()
    if title and m["title"]:
        props[m["title"]] = {"title": [{"text": {"content": title[:1900]}}]}
    if "deadline" in args and m["date"]:
        dl = (args.get("deadline") or "").strip()
        props[m["date"]] = {"date": {"start": dl} if dl else None}  # blank clears it
    if args.get("status") and m["status"]:
        st = _match_option(args["status"], m["status_options"])
        if st:
            props[m["status"]] = {"status": {"name": st}}
    elif for_create and m["status"] and m["status_options"]:
        props[m["status"]] = {"status": {"name": m["status_options"][0]}}  # default e.g. "To Do"
    if args.get("priority") and m["select"]:
        pr = _match_option(args["priority"], m["select_options"])
        if pr:
            props[m["select"]] = {"select": {"name": pr}}
    if args.get("category") and m["multi_select"]:
        cats = [c.strip() for c in str(args["category"]).split(",") if c.strip()]
        sel = [{"name": o} for c in cats if (o := _match_option(c, m["multi_options"]))]
        if sel:
            props[m["multi_select"]] = {"multi_select": sel}
    if args.get("notes") and m["rich_text"]:
        props[m["rich_text"]] = {"rich_text": [{"text": {"content": str(args["notes"])[:1900]}}]}
    return props


async def _resolve_task(db_id: str, args: dict):
    """Return (page_id, title, error). Explicit page_id wins; else match a task by title text."""
    pid = (args.get("page_id") or "").strip()
    if pid:
        return pid, args.get("query") or args.get("title"), None
    query = (args.get("query") or args.get("title") or "").strip()
    if not query:
        return None, None, "Which task, sir? Tell me a word from its name."
    data = await _post(f"/databases/{db_id}/query", {"page_size": 100})
    ql = query.lower()
    matches = [(p["id"], _title_of(p)) for p in (data.get("results") or []) if ql in _title_of(p).lower()]
    if not matches:
        return None, None, f"No task matching '{query}', sir."
    if len(matches) > 1:
        return None, None, ("A few tasks match, sir: " + "; ".join(t for _, t in matches[:6]) +
                            ". Which one?")
    return matches[0][0], matches[0][1], None


def _tasks_db(args: dict) -> str | None:
    return (args.get("database_id") or settings.notion_tasks_db_id or "").strip() or None


async def notion_create_task(args: dict) -> str:
    """Create a new row in the tasks dashboard (title + optional deadline/status/priority/category)."""
    if not _configured():
        return not_configured("Notion", _NEEDS)
    db_id = _tasks_db(args)
    if not db_id:
        return "No tasks database is configured yet, sir (set JARVIS_NOTION_TASKS_DB_ID)."
    title = (args.get("title") or args.get("task") or "").strip()
    if not title:
        return "What should the task be, sir?"
    try:
        m = _schema_map(await _get(f"/databases/{db_id}"))
        props = _build_task_props(m, args, for_create=True)
        await _post("/pages", {"parent": {"database_id": db_id}, "properties": props})
        extra = f" (due {args['deadline']})" if args.get("deadline") else ""
        return f"Added '{title}' to your tasks, sir{extra}."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion create task", e)


async def notion_update_task(args: dict) -> str:
    """Update a task's status / deadline / priority (find it by a word in its name, or page_id)."""
    if not _configured():
        return not_configured("Notion", _NEEDS)
    db_id = _tasks_db(args)
    if not db_id:
        return "No tasks database is configured yet, sir."
    try:
        page_id, title, err = await _resolve_task(db_id, args)
        if err:
            return err
        m = _schema_map(await _get(f"/databases/{db_id}"))
        props = _build_task_props(m, args, for_create=False)
        if not props:
            return "What should I change, sir — status, deadline, or priority?"
        await _patch(f"/pages/{page_id}", {"properties": props})
        return f"Updated '{title or 'that task'}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion update task", e)


async def notion_complete_task(args: dict) -> str:
    """Mark a task done (find it by a word in its name, or page_id)."""
    if not _configured():
        return not_configured("Notion", _NEEDS)
    db_id = _tasks_db(args)
    if not db_id:
        return "No tasks database is configured yet, sir."
    try:
        page_id, title, err = await _resolve_task(db_id, args)
        if err:
            return err
        m = _schema_map(await _get(f"/databases/{db_id}"))
        done = m["status_done"] or (m["status_options"][-1] if m["status_options"] else None)
        if not (m["status"] and done):
            return "I couldn't find a 'Done' status on that database, sir."
        await _patch(f"/pages/{page_id}", {"properties": {m["status"]: {"status": {"name": done}}}})
        return f"Marked '{title or 'that task'}' as {done}, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion complete task", e)


async def notion_delete_task(args: dict) -> str:
    """Delete (archive) a task from the dashboard (find it by a word in its name, or page_id)."""
    if not _configured():
        return not_configured("Notion", _NEEDS)
    db_id = _tasks_db(args)
    if not db_id:
        return "No tasks database is configured yet, sir."
    try:
        page_id, title, err = await _resolve_task(db_id, args)
        if err:
            return err
        await _patch(f"/pages/{page_id}", {"archived": True})
        return f"Deleted '{title or 'that task'}' from your tasks, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Notion delete task", e)


SCHEMAS = [
    {"type": "function", "function": {
        "name": "notion_create_task",
        "description": "Create a new task in Vazghen's Notion tasks dashboard. Use for 'add a task to "
                       "…', 'remind me to …', 'put X on my list'. Deadline must be an ISO date "
                       "(YYYY-MM-DD) — compute it yourself from today if he says 'tomorrow'/'Friday'.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "The task text (the title)."},
            "deadline": {"type": "string", "description": "Optional due date, YYYY-MM-DD."},
            "status": {"type": "string", "description": "Optional: To Do / In progress / Done."},
            "priority": {"type": "string", "description": "Optional: High / Medium / Low."},
            "category": {"type": "string", "description": "Optional, comma-separated: Work, Home, Business, Personal, Family, Personal development."},
            "notes": {"type": "string", "description": "Optional extra notes."}},
            "required": ["title"]}}},
    {"type": "function", "function": {
        "name": "notion_update_task",
        "description": "Change a task's status, deadline, or priority. Identify it by a word from its "
                       "name (query) or a page_id. Use for 'move the rent task to Friday', "
                       "'set groceries to high priority', 'mark X in progress'.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A word from the task name to find it."},
            "page_id": {"type": "string", "description": "Optional exact page id instead of query."},
            "status": {"type": "string", "description": "To Do / In progress / Done."},
            "deadline": {"type": "string", "description": "New due date YYYY-MM-DD (blank clears it)."},
            "priority": {"type": "string", "description": "High / Medium / Low."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "notion_complete_task",
        "description": "Mark a task as Done. Identify it by a word from its name (query) or page_id. "
                       "Use for 'I finished X', 'mark X done', 'check off X'.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A word from the task name."},
            "page_id": {"type": "string", "description": "Optional exact page id."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "notion_delete_task",
        "description": "Delete (archive) a task from the dashboard. Identify it by a word from its name "
                       "(query) or page_id. Confirm with Vazghen first.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A word from the task name."},
            "page_id": {"type": "string", "description": "Optional exact page id."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "notion_tasks",
        "description": "Read Vazghen's Notion TASKS dashboard and report what needs doing: overdue, "
                       "due today, upcoming this week (with deadlines), and recurring/standing tasks. "
                       "Use for 'what's on my plate today?', 'any deadlines?', 'what's due this "
                       "week?', 'what are my recurring tasks?'.",
        "parameters": {"type": "object", "properties": {
            "scope": {"type": "string", "enum": ["today", "week", "open", "all"],
                      "description": "today = overdue+today (default); week = upcoming 7 days; open/all = everything."},
            "database_id": {"type": "string", "description": "Optional DB id; defaults to the configured tasks DB."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "notion_search",
        "description": "Search Vazghen's Notion (only pages shared with the integration) for a page "
                       "or database. Returns titles + ids. Use first to find a page id.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text; blank lists shared pages."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "notion_read_page",
        "description": "Read the text content of a Notion page by id ('read me the project page').",
        "parameters": {"type": "object", "properties": {
            "page_id": {"type": "string", "description": "Notion page id (from notion_search)."}},
            "required": ["page_id"]}}},
    {"type": "function", "function": {
        "name": "notion_append",
        "description": "Append a paragraph of text to a Notion page (a write). Confirm with Vazghen first.",
        "parameters": {"type": "object", "properties": {
            "page_id": {"type": "string", "description": "Notion page id."},
            "text": {"type": "string", "description": "The text to add."}},
            "required": ["page_id", "text"]}}},
    {"type": "function", "function": {
        "name": "notion_comment",
        "description": "Leave a comment on a Notion page. Confirm with Vazghen first.",
        "parameters": {"type": "object", "properties": {
            "page_id": {"type": "string", "description": "Notion page id."},
            "text": {"type": "string", "description": "The comment text."}},
            "required": ["page_id", "text"]}}},
    {"type": "function", "function": {
        "name": "notion_create_page",
        "description": "Create a new sub-page under a Notion parent page. Confirm with Vazghen first.",
        "parameters": {"type": "object", "properties": {
            "parent_id": {"type": "string", "description": "Parent page id (must be shared with the integration)."},
            "title": {"type": "string", "description": "New page title."},
            "content": {"type": "string", "description": "Optional first paragraph."}},
            "required": ["parent_id", "title"]}}},
]

HANDLERS = {
    "notion_create_task": notion_create_task,
    "notion_update_task": notion_update_task,
    "notion_complete_task": notion_complete_task,
    "notion_delete_task": notion_delete_task,
    "notion_tasks": notion_tasks,
    "notion_search": notion_search,
    "notion_read_page": notion_read_page,
    "notion_append": notion_append,
    "notion_comment": notion_comment,
    "notion_create_page": notion_create_page,
}
