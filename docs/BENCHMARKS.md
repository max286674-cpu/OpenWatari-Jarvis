# Jarvis — Efficiency Benchmarks & Fine-Tuning

> Regenerate any time with: `uv run python bench/efficiency_report.py`
> (brain rows need the freellmapi tunnel up). Latency rows are wall-clock on the dev laptop,
> CPU-only, against the free freellmapi proxy — treat them as directional, not absolute.

## Status — fine-tuning applied 2026-06-12

The three TUNE items below were executed per `fine-tuning.md` and locked in by `bench/test_finetune.py`
(25/25). Post-tuning measured run:

| Metric | Before | After | Efficient target | Verdict |
|---|---|---|---|---|
| System prompt size | ~5,935–6,818 tok | **1,796 tok** (≤1,961 w/ full digest) | ≤ 2,000 tok | 🟢 cleared |
| Tool surface (per turn) | 66 | **40 core** (66 in registry) | ≤ 48 schemas | 🟢 GOOD |
| L1 recall (keyword) | 0.1 ms | 0.1 ms | ≤ 5 ms | 🟢 GOOD |
| L1 digest (startup) | 0.03 ms | 0.02 ms | ≤ 5 ms | 🟢 GOOD |
| L4 cache miss→hit | 61 ms → ~0 | 61 ms → ~0 | hit ≪ miss | 🟢 GOOD |
| Utility (weather) cold→warm | 2.4 s → ~0 | 3.2 s → ~0 | warm ~0 ms | 🟢 GOOD |
| Brain TTFT (stream) | 70b ~2,840 ms | 8b ~2,150 ms | ≤ 1,200 ms | 🟡 improved* |
| Brain full turn (direct) | ~1.2 s | ~1.2 s | ≤ 2,500 ms | 🟢 GOOD |

\* TTFT still grades TUNE on the dev laptop because ~2.1 s is the localhost→VPS **tunnel** round-trip,
not the model. In production the brain runs on the VPS, so the freellmapi call is localhost with no
tunnel — the model swap (70b → 8b) captures the controllable share. See `fine-tuning.md` Item 3.

## What was done (ranked by impact)

### 1. Trimmed the always-on system prompt — DONE (6,818 → 1,796 tok)
- **Dropped `tools.md` from the prompt** — it duplicated the tool schemas the model already receives.
- **Dropped `openclaw-fleet.md` and `environment.md` from the prompt** — the actionable fleet rule
  (delegate to ispir only) lives in the persona; ports/paths are read from config, not the prompt.
  Both stay on disk as on-demand reference. `context.py` now loads only an explicit `_ALWAYS_ON` set
  (no glob), so a new memory file must be added deliberately and weighed against the budget.
- **Tightened** persona + about-vazghen + proactive-companion + projects, condensed the two static
  instruction blocks, and **capped the learned digest at 12 facts** so a full digest still fits ≤2,000.

### 2. Lean per-turn tool surface — DONE (66 → 40 core)
- Tools are tagged into a CORE set (advertised every turn) and lazy groups (`coding`, `office`,
  `home`) that light up only when the utterance needs them (keyword triggers in `tools/__init__.py`,
  activation + one-turn warm decay in `agent.py`). The **full registry is unchanged** — every handler
  stays callable for tests, the proactive engine, and direct calls — so **no capability is removed**.

### 3. Fast primary model — DONE (primary 70b → 8b-instant)
- `bench/llm_bench.py` shows `llama-3.1-8b-instant` ~300–700 ms faster TTFT than 70b and still
  answering correctly. Promoted it to primary; `llama-3.3-70b-versatile` is now the first fallback
  (quality escalation on error/rate-limit). Knobs: `JARVIS_LLM_PRIMARY_MODEL` / `JARVIS_LLM_FALLBACK_MODELS`.

### 4. Everything else is within target — leave it
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
