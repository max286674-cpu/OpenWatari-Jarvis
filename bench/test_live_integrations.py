"""Live integration smoke test — one green/red readout of every EXTERNAL service.

Unlike run_all_tests.py (which is mostly offline + deterministic), this actually calls each
configured provider with your real keys. Anything unconfigured is reported as SKIP, not FAIL,
so it's safe to run at any stage. Network/credential errors are FAIL.

    uv run python bench/test_live_integrations.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis.config import settings  # noqa: E402

rows: list[tuple[str, str, str]] = []  # (status, name, detail)


def record(name: str, configured: bool, ok: bool, detail: str) -> None:
    status = "SKIP" if not configured else ("PASS" if ok else "FAIL")
    rows.append((status, name, detail.replace("\n", " ")[:90]))


def _ok(r: str) -> bool:
    """A tool result is 'live' if it didn't degrade or error."""
    low = r.lower()
    return "isn't configured" not in r and "couldn't" not in low and "rejected" not in low


async def main() -> None:
    from jarvis.brain.tools import (
        calendar,
        gmail,
        notify,
        notion,
        smarthome,
        telegram,
        vault,
        web,
    )

    # Vault (local, configured if path set)
    r = await vault.search_vault({"query": "project"})
    record("Vault search", bool(settings.vault_path), _ok(r), r)

    # Tavily web search
    r = await web.web_search({"query": "what is the capital of France"})
    record("Tavily web_search", bool(settings.tavily_api_key), "Paris" in r or "Answer" in r, r)

    # Jina Reader page scrape (free + keyless, so always exercised)
    r = await web.scrape_url({"url": "example.com"})
    record("Jina scrape_url", True, "Example Domain" in r or "example" in r.lower(), r)

    # Browserbase interactive browse
    r = await web.browse_web({"url": "example.com"})
    record("Browserbase browse_web",
           bool(settings.browserbase_api_key and settings.browserbase_project_id),
           "Example Domain" in r, r)

    # Telegram read (Telethon user client)
    r = await telegram.check_telegram({"limit": 5})
    record("Telegram read", bool(settings.telegram_api_id and settings.telegram_api_hash), _ok(r), r)

    # Gmail (read) — Phase 11
    r = await gmail.read_email({"query": "is:unread", "max": 3})
    record("Gmail read_email", bool(settings.google_refresh_token), _ok(r), r)

    # Google Calendar (read) — Phase 11
    r = await calendar.list_events({})
    record("Calendar list_events", bool(settings.google_refresh_token), _ok(r), r)

    # Notion (search) — Phase 11. With no shared pages this returns a friendly "no shared pages"
    # note, which still proves the token authenticates (so it counts as live).
    r = await notion.notion_search({"query": "project"})
    record("Notion search", bool(settings.notion_token), _ok(r), r)

    # Home Assistant (state) — Phase 11. SKIP unless configured.
    r = await smarthome.ha_state({})
    record("Home Assistant", bool(settings.ha_url and settings.ha_token), _ok(r), r)

    # ntfy push
    r = await notify.send_push({"message": "Jarvis live-integration check ✅", "title": "Jarvis"})
    record("ntfy push", bool(settings.ntfy_topic), "Pushed" in r, r)

    print("=" * 72)
    print(" LIVE INTEGRATIONS")
    print("=" * 72)
    icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "·"}
    for status, name, detail in rows:
        print(f"  {icon[status]} {status:4} {name:24} {detail}")
    npass = sum(1 for s, _, _ in rows if s == "PASS")
    nfail = sum(1 for s, _, _ in rows if s == "FAIL")
    nskip = sum(1 for s, _, _ in rows if s == "SKIP")
    print(f"\n  {npass} live, {nfail} failed, {nskip} not configured")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    asyncio.run(main())
