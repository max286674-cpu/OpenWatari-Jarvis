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


SCHEMAS = [
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
    "notion_search": notion_search,
    "notion_read_page": notion_read_page,
    "notion_append": notion_append,
    "notion_comment": notion_comment,
    "notion_create_page": notion_create_page,
}
