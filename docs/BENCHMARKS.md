# Jarvis — Efficiency Benchmarks & Fine-Tuning

> Regenerate any time with: `uv run python bench/efficiency_report.py`
> (brain rows need the freellmapi tunnel up). Latency rows are wall-clock on the dev laptop,
> CPU-only, against the free freellmapi proxy — treat them as directional, not absolute.

## Latest run (2026-06-12)

| Metric | Measured | Efficient target | Verdict |
|---|---|---|---|
| System prompt size | ~23.7k chars (~5,935 tok) | ≤ 2,000 tok | 🔴 **TUNE** |
| Tool surface | 45 tools | ≤ 48 schemas | 🟡 OK |
| L1 recall (keyword) | 0.11 ms | ≤ 5 ms | 🟢 GOOD |
| L1 digest (startup) | 0.03 ms | ≤ 5 ms | 🟢 GOOD |
| L4 cache miss→hit | 61 ms → 0.002 ms | hit ≪ miss | 🟢 GOOD |
| Utility (weather) cold→warm | 2,438 ms → ~0 ms | warm ~0 ms | 🟢 GOOD |
| Brain TTFT (stream) | 1,672 ms | ≤ 1,200 ms | 🔴 **TUNE** |
| Brain full turn (direct) | 6,077 ms | ≤ 2,500 ms | 🔴 **TUNE** |

The local machinery Jarvis owns is already fast — memory recall is sub-millisecond, and the new L4
cache turns a 61 ms lookup into essentially free on repeat (the same shape proven live on the weather
call: 2.4 s cold, ~0 ms warm). **The latency that matters for a voice companion lives in two places:
the size of the prompt the model re-reads every turn, and the model/proxy itself.**

## What to fine-tune (ranked by impact)

### 1. Trim the always-on system prompt (🔴 biggest lever)
At ~5,935 tokens it's ~3× the target. Every turn re-reads it, so it taxes **both** TTFT and cost on
every single exchange. Causes: all of `memory/*.md` (about-vazghen, projects, openclaw-fleet,
environment, **tools.md**, proactive-companion) are injected in full, and `tools.md` now duplicates
descriptions the model *already* receives as structured tool schemas.

Concrete moves (each independent, low-risk):
- **Stop injecting `tools.md` into the prompt.** The 45 tool schemas already carry name + description
  + params; the prose duplicate is the largest redundant block. Keep `tools.md` as human docs, drop
  it from `_MEMORY_ORDER` in `context.py`. *Est. −1,500–2,000 tok.*
- **Summarise the long memory files** (openclaw-fleet, projects) to a tight brief and let Jarvis pull
  detail on demand via `search_vault`/`recall`. *Est. −1,000–1,500 tok.*
- **Lazy-load** rarely-needed context (fleet roster, environment minutiae) behind a tool instead of
  the prompt. Target landing zone: ~2,000–2,500 tok.

### 2. Pick a voice-tuned primary model (🔴 TTFT + turn time)
TTFT 1,672 ms and a 6.1 s full turn are dominated by `llama-3.3-70b-versatile` on the free proxy.
For a spoken companion, **TTFT is perceived latency** — a smaller, faster model often wins the felt
experience even at a slight quality cost.
- Run `uv run python bench/llm_bench.py` to rank models by TTFT on the live proxy.
- Consider making `llama-3.1-8b-instant` (already in the fallback chain) the **primary** for snappy
  turns, and escalate to 70B only for genuinely hard asks (a future "hard question → bigger model"
  router). Knob: `JARVIS_LLM_PRIMARY_MODEL` / `JARVIS_LLM_FALLBACK_MODELS`.
- The 6.1 s full-turn figure is a single sample and noisier than TTFT; re-measure with n≥5 before
  drawing conclusions.

### 3. Everything else is within target — leave it
Memory layers, the cache, and the utility belt are all green. The L4 cache already removes the
biggest repeat-lookup cost; adding **Redis** (set `JARVIS_REDIS_URL`) extends that win *across brain
restarts*, which is the one thing the in-process tier can't do — worth it once the brain runs 24/7,
not urgent before.

## Notes on method
- `bench/efficiency_report.py` is informational (never fails the build); the pass/fail gate stays
  `bench/run_all_tests.py`.
- TTFW (time-to-first-*word*, incl. TTS) and VAQI are measured separately on real devices — see
  `TODO-NOW.md` item 3; those are the true end-to-end voice numbers. This report covers the brain
  slice that precedes TTS.
