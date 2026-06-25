"""Self-improvement loop — adapted from NousResearch/hermes-agent's ``background_review``.

Hermes, after a turn, forks the agent to replay the conversation and ask itself "should anything be
saved to memory?", writing straight to its memory store while the main conversation + prompt cache
stay untouched. We apply the same idea to Watari's brain: a background pass replays the recent
conversation and asks the model what DURABLE facts about the owner are worth remembering long-term,
then writes them to **L1 learned memory** (``STORE.remember``, which dedups).

Why it matters here: Watari's 5-layer memory was elaborate but EMPTY (L1 = 0 facts) because nothing
ever wrote to it. This loop is what makes the memory actually learn as you talk — and it runs OFF
the hot path (a separate task) so it never slows a reply.

Invariants (mirroring Hermes): only ADD/dedup, never delete here; never touch the live conversation
or the main model's prompt; degrade silently on any error.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from jarvis.brain.memory import STORE

# Adapted from Hermes' _MEMORY_REVIEW_PROMPT, tightened to return machine-parseable output.
_EXTRACT_PROMPT = (
    "You are Watari's private memory reviewer. Read the conversation and extract DURABLE facts about "
    "the owner that are worth remembering for months: his stable preferences and persona, decisions he "
    "made, people/projects/places he mentioned, and expectations about how Watari should behave. "
    "IGNORE transient chit-chat, one-off task mechanics, the current time/date, and anything already "
    "obvious. Each fact must be a short, self-contained third-person sentence. "
    'Return ONLY a compact JSON array (max 8), e.g. ["the owner prefers replies under two sentences.", '
    '"the owner renamed his assistant to Watari."]. If nothing is worth saving, return [].'
)


def _parse_facts(raw: str) -> list[str]:
    """Pull a JSON array of fact strings out of the model's reply, defensively."""
    m = re.search(r"\[.*\]", raw or "", re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[str] = []
    for x in arr:
        s = str(x).strip()
        if 3 < len(s) <= 240:
            out.append(s)
    return out[:8]


async def review_and_learn(history: list[dict[str, Any]], llm, store: Any = STORE) -> list[str]:
    """Replay ``history``, extract durable facts, write the new ones to L1. Returns facts learned."""
    convo = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    )
    if len(convo) < 40:
        return []  # not enough said to learn anything
    try:
        msg = await llm.complete(
            [{"role": "system", "content": _EXTRACT_PROMPT},
             {"role": "user", "content": convo[:6000]}],
            temperature=0.2,
        )
    except Exception as e:  # noqa: BLE001 — self-improvement is best-effort, never breaks a turn
        logger.warning(f"self-improve review skipped ({type(e).__name__}: {e})")
        return []
    facts = _parse_facts(getattr(msg, "content", "") or "")
    before = store.count()
    learned: list[str] = []
    for f in facts:
        if store.remember(f, tags=["learned", "auto"]):
            learned.append(f)
    new = store.count() - before
    if learned:
        logger.info(f"self-improve: reviewed {len(history)} msgs -> {new} new fact(s) into L1 memory")
    return learned
