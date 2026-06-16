"""Web tools — search, scrape, and interactive browse.

Three complementary capabilities, each behind its own key (all degrade gracefully):

* ``web_search``  — Tavily API: fast LLM-grade web search with answer + sources. Best for
  "look up / what's the latest on X". (Other search scrapers can be slotted in the same way.)
* ``scrape_url``  — Jina Reader (r.jina.ai): fetch a single URL as clean Markdown (JS-rendered),
  **free and keyless**. Best for "open this page and tell me what it says" / "read me the headline".
* ``browse_web``  — Browserbase: a real headless Chrome for tasks that need interaction
  (click, fill, multi-step). Connects Playwright over CDP to a Browserbase session.

These are Jarvis's OWN web reach. Heavy multi-step domain research still goes to the fleet
(ispir) via delegate_to_fleet — these are for quick, self-served lookups.
"""

from __future__ import annotations

from jarvis.brain.cache import CACHE
from jarvis.brain.tools.base import clip, http_get, http_post, not_configured, tool_error
from jarvis.config import settings


async def _do_web_search(query: str) -> str:
    r = await http_post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "max_results": 5,
        },
    )
    data = r.json()
    parts: list[str] = []
    if data.get("answer"):
        parts.append(f"Answer: {data['answer']}")
    for res in (data.get("results") or [])[:5]:
        parts.append(f"- {res.get('title', '')}: {clip(res.get('content', ''), 200)} ({res.get('url', '')})")
    return "\n".join(parts) if parts else f"No web results for '{query}', sir."


async def web_search(args: dict) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "What should I search the web for, sir?"
    if not settings.tavily_api_key:
        return not_configured("web search", "a Tavily API key (JARVIS_TAVILY_API_KEY)")
    try:
        # L4 cache: a repeated search inside the TTL window returns instantly (near-zero TTFW).
        return await CACHE.cached(
            "web_search", key=query.lower(), ttl=600, factory=lambda: _do_web_search(query)
        )
    except Exception as e:  # noqa: BLE001
        return tool_error("web search", e)


async def _do_scrape(url: str) -> str:
    # Jina Reader (r.jina.ai): prepend the reader origin and GET — it fetches, renders JS, and
    # returns clean LLM-ready Markdown. Free and keyless; an optional JARVIS_JINA_API_KEY only
    # raises rate limits. 'X-Return-Format: markdown' asks for Markdown explicitly.
    headers = {"X-Return-Format": "markdown"}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    r = await http_get("https://r.jina.ai/" + url, headers=headers)
    return (r.text or "").strip()


async def scrape_url(args: dict) -> str:
    url = (args.get("url") or "").strip()
    if not url:
        return "Which page should I open, sir?"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        # Cache briefly so "read me that page" repeated in one session is instant.
        md = await CACHE.cached("scrape", key=url, ttl=300, factory=lambda: _do_scrape(url))
        return clip(md, 3500) if md else f"I opened {url} but found no readable text, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("page scrape", e)


async def browse_web(args: dict) -> str:
    """Interactive headless browse via Browserbase (Playwright over CDP).

    Needs the Browserbase key+project AND the optional 'browse' extra (Playwright). For a
    plain 'read this page' use scrape_url instead — this is for navigation/extraction tasks.
    """
    url = (args.get("url") or "").strip()
    task = (args.get("task") or "").strip()
    if not url:
        return "Give me a URL to browse, sir."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not (settings.browserbase_api_key and settings.browserbase_project_id):
        return not_configured(
            "the live browser",
            "a Browserbase API key + project id (JARVIS_BROWSERBASE_API_KEY / _PROJECT_ID)",
        )
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        return not_configured("the live browser", "the Playwright extra (uv sync --extra browse)")
    try:
        # Create a Browserbase session, then drive it with Playwright over CDP.
        sess = await http_post(
            "https://api.browserbase.com/v1/sessions",
            headers={"X-BB-API-Key": settings.browserbase_api_key, "Content-Type": "application/json"},
            json={"projectId": settings.browserbase_project_id},
        )
        connect_url = sess.json().get("connectUrl")
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(connect_url)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()
        note = f" (task: {task})" if task else ""
        return f"Browsed {url}{note}. Title: {title}. Content: {clip(text, 2500)}"
    except Exception as e:  # noqa: BLE001
        return tool_error("live browse", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information (news, facts, how-tos, prices) and get "
                "a synthesized answer with sources. Use for anything live or beyond your own "
                "knowledge that doesn't need deep multi-step research."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_url",
            "description": (
                "Fetch a single web page and return its main text as clean Markdown. Use for "
                "'open <site> and tell me the headline / what it says'."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The page URL."}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": (
                "Open a real headless browser to navigate and extract from a page that needs "
                "interaction or JavaScript. Use only when scrape_url isn't enough."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open."},
                    "task": {"type": "string", "description": "Optional: what to do/extract there."},
                },
                "required": ["url"],
            },
        },
    },
]

HANDLERS = {"web_search": web_search, "scrape_url": scrape_url, "browse_web": browse_web}
