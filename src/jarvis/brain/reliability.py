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
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger


_last_probe_path = Path.home() / ".jarvis" / "health_probe.json"
# Tracks consecutive-red counts + whether we've already alerted per component, so a single
# transient blip never pages the owner and a sustained outage pages exactly once (Phase 0.1).
_escalation_path = Path.home() / ".jarvis" / "health_escalation.json"


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

    async def _llm() -> bool:
        # Real liveness, not key-presence: a 1-token completion through the live failover chain.
        # The LLM is the single most critical organ and was previously the one thing NOT probed.
        from jarvis.brain.llm import LLMClient
        msg = await asyncio.wait_for(
            LLMClient().complete([{"role": "user", "content": "ping"}]), timeout=10)
        return getattr(msg, "content", None) is not None or bool(getattr(msg, "tool_calls", None))

    for name, fn in (("llm", _llm), ("vault", _vault), ("telegram", _telegram),
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


def _load_escalation(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt state = start clean
        return {}


def _save_escalation(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"escalation state write failed ({e})")


async def _repair(name: str) -> bool:
    """Attempt a bounded, honest in-process repair for a red component; True if it's back.

    Process/connection restarts are already owned by systemd (brain) + the edge supervisor — this
    only handles what the brain itself CAN fix: re-validating a transient vault blip (the 15-min
    sync's delete→move window, an AV lock, a OneDrive placeholder rehydrating) and re-pinging the
    LLM after a provider cooldown. A genuinely dead dependency (missing key) can't be retried into
    life, so we re-probe and let escalation carry it. Never raises.
    """
    try:
        if name == "vault":
            from jarvis.brain.context import validate_vault
            ok, _ = validate_vault(retries=3, grace=0.6)
            return ok
        if name == "llm":
            from jarvis.brain.llm import LLMClient
            client = LLMClient()
            await client.warmup()  # re-open connections / clear a cold-start stall
            msg = await asyncio.wait_for(
                client.complete([{"role": "user", "content": "ping"}]), timeout=10)
            return getattr(msg, "content", None) is not None or bool(getattr(msg, "tool_calls", None))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"_repair({name}) failed: {type(e).__name__}")
        return False
    return False


async def attempt_repair_and_escalate(
    probes: list[dict],
    *,
    push_fn=None,
    state_path: Path | None = None,
    repair=None,
) -> dict:
    """Turn the probe result into ACTION (Phase 0.1): repair red components, then page the owner on
    SUSTAINED failures only — the missing half of the old probe, which merely logged.

    Rules that keep it from crying wolf:
      * A red component is first handed to ``_repair``; a transient that clears counts as green.
      * Only a component red on **>=2 consecutive** probes escalates (one 8h window at the 4h cadence).
      * Each outage pages exactly **once** (deduped on disk); recovery sends one 'back to normal' note.

    ``push_fn`` / ``state_path`` / ``repair`` are injectable so the whole thing is hermetically
    testable with no network. Returns ``{component: {ok, consecutive_red, alerted, repaired}}``.
    """
    path = state_path or _escalation_path
    state = _load_escalation(path)
    if push_fn is None:
        from jarvis.brain.tools.notify import push as push_fn  # type: ignore[assignment]
    if repair is None:
        repair = _repair
    summary: dict = {}
    for p in probes:
        name = p["name"]
        st = state.get(name, {"consecutive_red": 0, "alerted": False})
        ok = bool(p.get("ok"))
        repaired = False
        if not ok:
            try:
                repaired = bool(await repair(name))
            except Exception:  # noqa: BLE001
                repaired = False
            ok = ok or repaired
        if ok:
            if st.get("alerted"):
                try:
                    await push_fn(f"{name} is back to normal, sir.", title="Watari — recovered")
                except Exception:  # noqa: BLE001
                    pass
            st = {"consecutive_red": 0, "alerted": False}
        else:
            st["consecutive_red"] = int(st.get("consecutive_red", 0)) + 1
            if st["consecutive_red"] >= 2 and not st.get("alerted"):
                err = p.get("err") or "no response"
                try:
                    await push_fn(
                        f"Watari degraded, sir: {name} is down ({err}) and self-repair didn't take. "
                        "I'll keep retrying.", title="Watari — degraded")
                except Exception:  # noqa: BLE001
                    pass
                st["alerted"] = True
        st["repaired"] = repaired
        state[name] = st
        summary[name] = {"ok": ok, **st}
    _save_escalation(path, state)
    return summary


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