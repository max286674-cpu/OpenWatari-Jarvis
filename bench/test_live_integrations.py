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


async def main() -> None:
    from jarvis.brain.tools import notify, spotify, telegram, vault, web

    # vault (local, always configured if path set)
    r = await vault.search_vault({"query": "project"})
    record("Vault search", bool(settings.vault_path), "isn't configured" not in r and "couldn't" not in r.lower(), r)

    # Tavily
    r = await web.web_search({"query": "what is the capital of France"})
    record("Tavily web_search", bool(settings.tavily_api_key), "Paris" in r or "Answer" in r, r)

    # Firecrawl
    r = await web.scrape_url({"url": "example.com"})
    record("Firecrawl scrape_url", bool(settings.firecrawl_api_key), "Example Domain" in r, r)

    # Browserbase
    r = await web.browse_web({"url": "example.com"})
    record("Browserbase browse_web",
           bool(settings.browserbase_api_key and settings.browserbase_project_id),
           "Example Domain" in r, r)

    # Telegram read (Telethon)
    r = await telegram.check_telegram({"limit": 5})
    record("Telegram read", bool(settings.telegram_api_id and settings.telegram_api_hash),
           "isn't configured" not in r and "couldn't" not in r.lower(), r)

    # Spotify now-playing
    r = await spotify.spotify({"action": "now_playing"})
    record("Spotify", bool(settings.spotify_refresh_token),
           "isn't configured" not in r and "couldn't" not in r.lower(), r)

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
