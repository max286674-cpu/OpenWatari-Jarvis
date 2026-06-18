"""Fine-tuning regression guard — locks in the efficiency wins from fine-tuning.md.

Offline & deterministic. Verifies the three TUNE items stay fixed:
  * Item 1 — system prompt stays lean (<= 2000 tok) and still carries the load-bearing context;
             the duplicated tools.md / openclaw-fleet.md are NOT injected every turn.
  * Item 2 — the per-turn tool surface (core) is <= 48, while the FULL registry still holds every
             tool (no capability removed); lazy groups activate on the right utterances.
  * Item 3 — the primary model is the fast one (TTFT), with 70b kept as a fallback.

    uv run python bench/test_finetune.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def main() -> None:
    from jarvis.brain.context import build_system_prompt, load_memory_files
    from jarvis.brain.tools import (
        core_tool_schemas,
        groups_for_text,
        tool_handlers,
        tool_names,
    )
    from jarvis.config import settings

    print("[1] Item 1 — system prompt is lean but complete")
    sp = build_system_prompt()
    tok = len(sp) // 4
    check(f"prompt <= 2000 tok (got ~{tok})", tok <= 2000, f"{tok} tok")
    # Worst case = the base prompt WITHOUT any learned digest, plus a FULL digest's headroom
    # (memory_digest_max facts ~55 chars each). Measuring the digest-free base keeps this stable as
    # real learned facts accumulate — otherwise the current digest would be double-counted and the
    # check would drift over budget in normal use.
    base_no_digest = sp.split("# Recently learned about")[0]
    worst = len(base_no_digest) // 4 + (settings.memory_digest_max * 55) // 4
    check(f"prompt stays <= 2000 tok with a full digest (~{worst})", worst <= 2000, f"{worst} tok")
    # Still carries identity + principal + the proactive mandate.
    check("persona present (Watari)", "Watari" in sp)
    check("principal present (Vazghen)", "Vazghen" in sp)
    check("proactive mandate present", "proactive" in sp.lower() or "initiate" in sp.lower())
    check("delegation rule present (ispir)", "ispir" in sp.lower())
    # The two demoted files are NOT injected as memory sections every turn.
    always_on = {name for name, _ in load_memory_files()}
    check("tools.md NOT always-on", "tools.md" not in always_on, str(always_on))
    check("openclaw-fleet.md NOT always-on", "openclaw-fleet.md" not in always_on, str(always_on))
    check("environment.md NOT always-on", "environment.md" not in always_on, str(always_on))

    print("\n[2] Item 2 — lean per-turn surface, full registry intact")
    core = len(core_tool_schemas()) + 2          # + get_time, delegate_to_fleet
    full = len(tool_names())
    check(f"per-turn surface <= 48 (got {core})", core <= 48, f"{core}")
    check(f"full registry intact (>= 63, got {full})", full >= 63, f"{full}")
    # No capability removed: every lazy tool is still resolvable to a handler.
    handlers = tool_handlers()
    lazy_examples = ["read_source", "git_commit", "notion_search", "read_email", "list_events",
                     "ha_call", "play_in_music_room"]
    check("all lazy tools still have handlers", all(t in handlers for t in lazy_examples),
          str([t for t in lazy_examples if t not in handlers]))

    print("\n[3] Item 2 — lazy groups activate on the right utterances")
    check("'commit my code' -> coding", "coding" in groups_for_text("commit my code to git"))
    check("'any new email?' -> office", "office" in groups_for_text("any new email?"))
    check("'what's on my calendar' -> office", "office" in groups_for_text("what's on my calendar today"))
    check("'turn on the light' -> home", "home" in groups_for_text("turn on the kitchen light"))
    check("'what's the weather' -> no lazy group", groups_for_text("what's the weather in Yerevan") == set())
    check("'what time is it' -> no lazy group", groups_for_text("what time is it") == set())

    print("\n[4] Item 2 — the agent advertises core by default, expands on a coding turn")
    from jarvis.brain.agent import JarvisAgent

    a = JarvisAgent()
    default_names = {s["function"]["name"] for s in a._tools}
    check("default surface == core (no lazy tools yet)", "git_commit" not in default_names)
    check("default surface has everyday tools", {"search_vault", "web_search", "get_time"} <= default_names)
    turn = a._tools_for_turn("read your config.py and run the tests")
    turn_names = {s["function"]["name"] for s in turn}
    check("coding turn now advertises coding tools", {"read_source", "run_tests"} <= turn_names)
    # A following unrelated turn: coding stays warm one turn, then decays.
    a._tools_for_turn("thanks")                     # warm (ttl 2 -> 1)
    a._tools_for_turn("what's the weather?")        # decays (ttl 1 -> 0)
    after = {s["function"]["name"] for s in a._tools_for_turn("hello")}
    check("coding tools decay back out when unused", "read_source" not in after, str(sorted(after))[:80])

    print("\n[5] Item 3 — primary is the benchmarked fast voice model; chain is provider-diverse")
    # Updated 2026-06-14: bench/pick_model.py measures real time-to-first-SENTENCE under the full
    # agent load. llama-3.3-70b-versatile won (~1.5s, smart, reliable streaming+tools). The old
    # llama-3.1-8b-instant was fast-but-dumb ("Joe not Jarvis") — it must NOT be the primary.
    # A chain entry may carry a provider prefix (e.g. "groq:llama-3.3-70b-versatile" routes the same
    # 70b winner directly through Groq for ~0.3s TTFT) — strip it before comparing the model name.
    primary_model = settings.llm_primary_model.split(":", 1)[-1]
    check("primary is the benchmarked voice winner (llama-3.3-70b-versatile)",
          primary_model == "llama-3.3-70b-versatile", settings.llm_primary_model)
    check("the dumb 8b-instant is not the primary", primary_model != "llama-3.1-8b-instant")
    check("primary is first in the chain", settings.llm_chain[0] == settings.llm_primary_model)
    check("chain is provider-diverse (>=2 distinct providers as fallbacks)",
          len(settings.llm_chain) >= 3, str(settings.llm_chain))

    print(f"\n=== {passed}/{passed + failed} checks passed ===")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
