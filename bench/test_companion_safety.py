"""Companion safety + memory hardening tests (offline, deterministic).

Covers four fixes from the 2026-06-16 audit:
  1. Confirmation tier is ENFORCED in code (not just the system prompt): an outward-facing /
     destructive tool is blocked until Vazghen affirms — a weak model can't fire it unprompted.
  2. Proactive messages persist durably (L2 journal), so a nudge is referable DAYS later, not just
     inside the 12-turn working window.
  3. Smart session reset clears stale WORKING memory after an idle gap (durable memory kept).
  4. write_vault saves notes only on the authoritative host, scoped safely inside the vault.

Run: uv run python bench/test_companion_safety.py
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from jarvis.brain.agent import USER_TZ, JarvisAgent, _is_affirmation
from jarvis.config import settings

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  XX  {name}")


def test_affirmation() -> None:
    check("affirmation: 'yes, send it'", _is_affirmation("yes, send it"))
    check("affirmation: 'go ahead'", _is_affirmation("go ahead"))
    check("affirmation: 'do it'", _is_affirmation("do it"))
    check("non-affirmation: 'actually cancel that'", not _is_affirmation("actually cancel that"))
    check("non-affirmation: 'what time is it'", not _is_affirmation("what time is it"))


def test_begin_turn_supersede() -> None:
    agent = JarvisAgent()
    agent._pending_confirm = {"name": "send_email", "args": {}}
    agent._last_turn_at = datetime.now(USER_TZ)
    agent._begin_turn("yes please")
    check("affirmation grants the pending confirm",
          agent._confirm_granted is True and bool(agent._pending_confirm))
    agent._pending_confirm = {"name": "send_email", "args": {}}
    agent._begin_turn("actually, what's the weather")
    check("a new non-affirmative request supersedes the pending one",
          agent._confirm_granted is False and agent._pending_confirm is None)


def test_smart_reset() -> None:
    agent = JarvisAgent()
    agent._idle_reset_min = 180
    agent._history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    agent._last_turn_at = datetime.now(USER_TZ) - timedelta(minutes=200)
    agent._begin_turn("are you there")
    check("idle gap (>threshold) clears working memory", agent._history == [])

    agent._history = [{"role": "user", "content": "hi"}]
    agent._last_turn_at = datetime.now(USER_TZ) - timedelta(minutes=5)
    agent._begin_turn("still here?")
    check("recent gap keeps working memory", agent._history != [])

    agent._history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
    agent.reset_session("manual")
    check("explicit reset_session clears history", agent._history == [])


def test_proactive_durable() -> None:
    agent = JarvisAgent()
    captured: list[str] = []
    from jarvis.brain import memory as memmod

    orig = memmod.STORE.journal_append
    memmod.STORE.journal_append = lambda summary, when=None: captured.append(summary)  # type: ignore
    try:
        agent.note_proactive("You have a standup in 10 minutes, sir.")
    finally:
        memmod.STORE.journal_append = orig  # type: ignore
    check("proactive note in working history (1-min recall)",
          any("standup" in m.get("content", "") for m in agent._history))
    check("proactive note persisted to journal (10-day recall)",
          any("[proactive]" in c and "standup" in c for c in captured))


async def test_confirm_gate() -> None:
    agent = JarvisAgent()
    sent: list[dict] = []

    async def spy(args: dict) -> str:
        sent.append(args)
        return "sent"

    agent._registry["send_email"] = spy
    calls = [{"id": "1", "name": "send_email", "arguments": '{"to":"anna","body":"late"}'}]

    agent._confirm_granted = False
    msgs: list[dict] = []
    await agent._execute_calls(msgs, calls)
    blocked = any("CONFIRM_REQUIRED" in m.get("content", "") for m in msgs if m.get("role") == "tool")
    check("confirm gate BLOCKS send_email without a yes",
          blocked and not sent and bool(agent._pending_confirm))

    agent._confirm_granted = True
    await agent._execute_calls([], calls)
    check("confirm gate RUNS send_email after a grant", len(sent) == 1)
    check("grant consumed (one yes = one action)",
          agent._confirm_granted is False and agent._pending_confirm is None)

    msgs3: list[dict] = []
    await agent._execute_calls(msgs3, [{"id": "2", "name": "get_time", "arguments": "{}"}])
    check("read tool (get_time) is never gated",
          not any("CONFIRM_REQUIRED" in m.get("content", "") for m in msgs3 if m.get("role") == "tool"))


async def test_vault_write() -> None:
    from jarvis.brain.tools.vault import write_vault

    settings.vault_writable = False
    r = await write_vault({"content": "hello"})
    check("vault write refused when host isn't authoritative", "off" in r.lower())

    old_path, old_w = settings.vault_path, settings.vault_writable
    with tempfile.TemporaryDirectory() as d:
        settings.vault_path = d
        settings.vault_writable = True
        try:
            await write_vault({"note": "Decisions", "content": "Chose MIT license.", "mode": "create"})
            f = Path(d) / "Watari" / "Decisions.md"
            check("vault write creates a note",
                  f.is_file() and "MIT" in f.read_text(encoding="utf-8"))
            await write_vault({"note": "Decisions", "content": "Added OpenWatari rename."})
            check("vault write appends to an existing note", "OpenWatari" in f.read_text(encoding="utf-8"))
            await write_vault({"note": "../../escape", "content": "x"})
            check("vault write can't traverse outside the vault",
                  not (Path(d).parent / "escape.md").exists())
        finally:
            settings.vault_path, settings.vault_writable = old_path, old_w


def main() -> None:
    test_affirmation()
    test_begin_turn_supersede()
    test_smart_reset()
    test_proactive_durable()
    asyncio.run(test_confirm_gate())
    asyncio.run(test_vault_write())
    print(f"\n=== {PASS}/{PASS + FAIL} checks passed ===")
    raise SystemExit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
