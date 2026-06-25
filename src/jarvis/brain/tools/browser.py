"""Local interactive browser — a real, visible Chromium Jarvis fully drives.

Unlike ``web.browse_web`` (cloud Browserbase, for headless one-off extraction), this is a
**persistent, visible** browser on the owner's own screen: Jarvis opens windows/tabs, clicks
links and buttons, fills forms, and — when the owner asks him to log in — types the email and
password into the page. The profile is persistent, so logins stick between sessions.

One ``browser`` tool with an ``action`` so the LLM has a single clear verb:
  open · click · fill · type · press · read · screenshot · new_tab · back · close

Needs the optional Playwright extra (``uv sync --extra browse`` then ``playwright install
chromium``). If it's missing the tool says so instead of crashing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

from jarvis.brain.tools.base import clip, not_configured, tool_error
from jarvis.config import settings

# browser.py lives at src/jarvis/brain/tools/ — repo root is 4 parents up (one deeper than
# the brain/ modules, which use parents[3]).
_REPO_ROOT = Path(__file__).resolve().parents[4]


class _Browser:
    """Singleton holding the live Playwright browser + current page across tool calls."""

    def __init__(self) -> None:
        self._pw = None
        self._ctx = None
        self._page = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        async with self._lock:
            if self._ctx is not None:
                return
            from playwright.async_api import async_playwright  # type: ignore

            self._pw = await async_playwright().start()
            profile = settings.browser_profile_dir or str(_REPO_ROOT / ".jarvis-browser")
            self._ctx = await self._pw.chromium.launch_persistent_context(
                profile, headless=settings.browser_headless,
                # autoplay-policy lets YouTube/music start playing without a manual click.
                args=["--start-maximized", "--autoplay-policy=no-user-gesture-required"],
                no_viewport=True,
            )
            self._ctx.set_default_timeout(settings.browser_nav_timeout_ms)
            self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
            logger.info(f"browser: launched (headless={settings.browser_headless}, profile={profile})")

    @property
    def page(self):
        return self._page

    async def new_tab(self):
        self._page = await self._ctx.new_page()
        return self._page

    async def close(self):
        async with self._lock:
            if self._ctx:
                await self._ctx.close()
            if self._pw:
                await self._pw.stop()
            self._pw = self._ctx = self._page = None


_BROWSER = _Browser()


async def browser(args: dict) -> str:
    timeout_s = 25.0
    try:
        return await asyncio.wait_for(_browser_action(args), timeout=timeout_s)
    except asyncio.TimeoutError:
        return (
            "The browser action timed out after 25 seconds, sir. I stopped trying so I don't get "
            "stuck in a loop. You may need to do that one manually or give me a simpler browser step."
        )


async def _browser_action(args: dict) -> str:
    if not settings.browser_tools_enabled:
        return "The browser is disabled, sir (JARVIS_BROWSER_TOOLS_ENABLED)."
    action = (args.get("action") or "").strip().lower()
    try:
        import playwright  # noqa: F401
    except ImportError:
        return not_configured(
            "the live browser",
            "the Playwright extra (uv sync --extra browse, then 'playwright install chromium')",
        )
    try:
        if action != "close":
            _neutralize_speechbrain_lazy_modules()
            await _BROWSER._ensure()
        page = _BROWSER.page

        if action == "open":
            url = (args.get("url") or "").strip()
            if not url:
                return "Which URL, sir?"
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded")
            return f"Opened {url} — '{await page.title()}', sir."

        if action == "new_tab":
            page = await _BROWSER.new_tab()
            url = (args.get("url") or "").strip()
            if url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                await page.goto(url, wait_until="domcontentloaded")
                return f"Opened a new tab at {url}, sir."
            return "Opened a new tab, sir."

        if action == "click":
            target = _locator(page, args)
            if target is None:
                return "Tell me what to click, sir — a button/link text or a CSS selector."
            try:
                await target.click(timeout=8000)
            except Exception:  # noqa: BLE001
                return (f"I couldn't find '{args.get('text') or args.get('selector')}' to click, "
                        "sir — the page may not have it.")
            return f"Clicked {args.get('text') or args.get('selector')}, sir."

        if action == "fill":
            sel = (args.get("selector") or "").strip()
            value = args.get("value") or ""
            if not sel:
                return "Which field should I fill, sir? Give me a selector."
            await page.fill(sel, value)
            shown = "•••" if args.get("secret") else clip(value, 40)
            return f"Filled {sel} with {shown}, sir."

        if action == "type":
            text = args.get("text") or args.get("value") or ""
            sel = (args.get("selector") or "").strip()
            if sel:
                await page.click(sel)
            await page.keyboard.type(text)
            return "Typed that in, sir."

        if action == "press":
            key = (args.get("key") or "Enter").strip()
            await page.keyboard.press(key)
            return f"Pressed {key}, sir."

        if action == "back":
            await page.go_back()
            return f"Went back — '{await page.title()}', sir."

        if action == "read":
            title = await page.title()
            body = await page.inner_text("body")
            return f"{title}\n{clip(body, 3000)}"

        if action == "screenshot":
            path = (args.get("path") or str(_REPO_ROOT / "browser-shot.png")).strip()
            await page.screenshot(path=path, full_page=False)
            return f"Saved a screenshot to {path}, sir."

        if action == "close":
            await _BROWSER.close()
            return "Closed the browser, sir."

        return f"I don't know the browser action '{action}', sir."
    except Exception as e:  # noqa: BLE001
        _neutralize_speechbrain_lazy_modules()
        return tool_error("browser", e)


def _neutralize_speechbrain_lazy_modules() -> None:
    """Avoid Playwright error reporting tripping over SpeechBrain's optional lazy k2 module.

    Playwright calls inspect.stack() on API errors. inspect.getmodule() scans sys.modules and calls
    hasattr(module, "__file__"); SpeechBrain's LazyModule for k2 raises ImportError there if k2 is
    not installed. Giving that lazy module a harmless __file__ prevents an unrelated optional
    SpeechBrain dependency from masking the real browser error.
    """
    for name, mod in list(sys.modules.items()):
        if not name.startswith("speechbrain.integrations.k2_fsa") or mod is None:
            continue
        try:
            object.__setattr__(mod, "__file__", "")
        except Exception:
            try:
                setattr(mod, "__file__", "")
            except Exception:
                pass


def _locator(page, args: dict):
    text = (args.get("text") or "").strip()
    sel = (args.get("selector") or "").strip()
    if sel:
        return page.locator(sel).first
    if text:
        # Match a link or button (or any element) by visible text.
        return page.get_by_text(text, exact=False).first
    return None


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": (
                "Drive a real visible web browser on the owner's screen: open a URL or new tab, "
                "click links/buttons (by visible text or CSS selector), fill form fields, type "
                "text, press keys (e.g. Enter), go back, read the page, or screenshot it. Use "
                "this for anything interactive — logging in (fill the email and password fields "
                "when he asks you to), clicking through a site, submitting forms. Confirm before "
                "submitting anything that sends data or money."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "click", "fill", "type", "press", "read",
                                 "screenshot", "new_tab", "back", "close"],
                    },
                    "url": {"type": "string", "description": "For open/new_tab."},
                    "selector": {"type": "string", "description": "CSS selector (fill/click/type)."},
                    "text": {"type": "string", "description": "Visible text to click."},
                    "value": {"type": "string", "description": "Value to fill into a field."},
                    "secret": {"type": "boolean", "description": "Set true for passwords (won't be echoed)."},
                    "key": {"type": "string", "description": "Key to press, e.g. 'Enter'."},
                    "path": {"type": "string", "description": "Screenshot file path."},
                },
                "required": ["action"],
            },
        },
    },
]

HANDLERS = {"browser": browser}
