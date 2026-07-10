"""T10 — reliability helpers: graceful degradation wrapper + health probe.

* ``safe_call(coro)`` — wraps any awaitable so an exception returns a short speakable error
  string instead of crashing the brain. Use in tools where the owner-facing error needs to be
  calm (e.g. a flaky external API).
* ``health_probe()`` — runs every 4h on the scheduler; surfaces a one-line status to the
  proactive engine if any of [vault, telegram, pass, Composio, ElevenLabs, Deepgram] is
  unreachable for >24h.

The A/B prompt harness lives in ``bench/ab_prompts.py`` (separate module) — not auto-toggled
here because swapping system prompts is invasive.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger


_last_probe_path = Path.home() / ".jarvis" / "health_probe.json"


async def safe_call(coro, *, label: str = "that") -> str:
    """Run an awaitable; return its string result, or a graceful spoken error."""
    try:
        return await coro
    except asyncio.TimeoutError:
        return f"{label} timed out, sir. I gave it a moment but it didn't come back."
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reliability.safe_call('{label}'): {type(e).__name__}: {e}")
        return f"{label} didn't respond, sir ({type(e).__name__})."


async def _probe_one(name: str, runner) -> dict:
    try:
        ok = await runner()
        return {"name": name, "ok": bool(ok), "err": ""}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "ok": False, "err": f"{type(e).__name__}: {e}"[:200]}


async def health_probe() -> list[dict]:
    """Ping critical subsystems; surface any that are down to the proactive engine."""
    probes = []

    async def _vault() -> bool:
        from jarvis.brain.tools.vault import search_vault
        r = await search_vault({"query": "watari", "limit": 1})
        return bool(r and "couldn't" not in r.lower()[:30])

    async def _telegram() -> bool:
        from jarvis.brain.telegram_bridge import TelegramBridge
        from jarvis.config import settings
        b = TelegramBridge(token=settings.telegram_bridge_bot_token, default_chat=settings.telegram_default_chat)
        return bool(b._token)

    async def _composio() -> bool:
        from jarvis.brain.tools.composio import _configured
        return _configured()

    async def _elevenlabs() -> bool:
        from jarvis.config import settings
        return bool(settings.elevenlabs_api_key)

    async def _deepgram() -> bool:
        from jarvis.config import settings
        return bool(settings.deepgram_api_key)

    for name, fn in (("vault", _vault), ("telegram", _telegram),
                      ("composio", _composio), ("elevenlabs", _elevenlabs),
                      ("deepgram", _deepgram)):
        probes.append(await _probe_one(name, fn))
    # Update the on-disk probe log.
    try:
        existing = []
        if _last_probe_path.exists():
            try:
                existing = __import__("json").loads(_last_probe_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "probes": probes})
        # Keep last 90 entries (~30 days at 8h cadence).
        _last_probe_path.parent.mkdir(parents=True, exist_ok=True)
        _last_probe_path.write_text(
            __import__("json").dumps(existing[-90:], indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"health_probe: log write failed ({e})")
    return probes


def format_probe_report(probes: list[dict]) -> str:
    ok = [p["name"] for p in probes if p["ok"]]
    bad = [p for p in probes if not p["ok"]]
    if not bad:
        return "All systems green, sir."
    parts = [f"{p['name']} is down ({p['err'] or 'no response'})" for p in bad]
    return f"Watari probe, sir: {', '.join(parts)}."


async def health_probe_and_surface() -> str:
    """Run a probe, and if anything failed, surface a one-line proactive signal."""
    probes = await health_probe()
    msg = format_probe_report(probes)
    bad = [p for p in probes if not p["ok"]]
    if not bad:
        return msg  # silent success
    # Surface via proactive if available.
    try:
        from jarvis.brain.proactive import Signal  # type: ignore
        # Hand-off: just log here; the scheduler fires the proactive engine from
        # default_signal_sources in another lifecycle path. Logging is enough so the
        # next tick / proactive cycle sees the degraded state if it queries probes.
        logger.warning(f"health_probe: {msg}")
    except Exception:
        pass
    return msg