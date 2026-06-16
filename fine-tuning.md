# Jarvis — Production-Readiness Plan

> **What this document is.** The efficiency-tuning work (system-prompt trim, per-turn tool surface,
> fast primary model) is **done and verified** — see the "Completed" note below. This file now tracks
> the remaining gap between *"19/19 tests green"* and *"a companion that survives a week unattended on
> real hardware."* Every test today is **hermetic**: it proves each piece behaves and degrades
> gracefully in isolation. What has **never** run is the thing that defines a voice companion — the
> live mic→STT→brain→TTS→speaker loop, unattended, for days. Closing that is what's left.
>
> Items are graded **P0** (blocks 24/7), **P1** (needed before trusting it unattended), **P2**
> (validation that needs your hardware to *finish*, but the engineering is ours), **P3** (roadmap).
> Each item states: current evidence, why it matters, the fix, the **extent** (acceptance criteria),
> and how to verify. Excludes credential/login steps you own (those stay in `TODO-NOW.md`).

## Completed & verified (efficiency pass, 2026-06-12)
- **System prompt** 6,818 → **1,796 tok** (≤1,961 with a full digest). Guard: `bench/test_finetune.py`.
- **Per-turn tool surface** 66 → **40 core** (full 66 still in the registry; lazy groups
  coding/office/home auto-activate). No capability removed.
- **Primary model** `llama-3.3-70b-versatile` → **`llama-3.1-8b-instant`** (70b is first fallback).
- All locked by `bench/test_finetune.py` (25/25) and the full suite (19/19). Treated here as a
  finished baseline; this plan builds on top of it.

---

## Progress (this pass)
- ✅ **P0 #1** scheduler-in-brain — `bench/test_scheduler_brain.py` (7/7).
- ✅ **P0 #2** brain service unit + `/healthz` — `deploy/vps/jarvis-brain.service` + `install-brain.sh`.
- ✅ **P0 #3** edge auto-reconnect — `src/jarvis/edge/brain_client.py`, `bench/test_edge_reconnect.py` (9/9).
- ✅ **P1 #4** resilience — `bench/test_resilience.py` (8/8); **found + fixed a real failover bug**
  (`except (_FAILOVER, _EmptyResponse)` was a nested tuple → `TypeError` on the first rate-limit).
- ✅ **P1 #6** memory hygiene — `src/jarvis/brain/maintenance.py`, `bench/test_memory_hygiene.py` (12/12).
- ✅ **P1 #7** security pass — system-delete guard for own secrets + audit value-scrub;
  `bench/test_security_hardening.py` (15/15); `SECURITY.md` updated.
- ⏳ Remaining: **P1 #5** offline harness, **P2 #8–10** live-hardware harnesses, **P3** multi-device.

## P0 — Blockers for true 24/7

### 1. Move the reminder scheduler into the always-on brain  ✅ DONE
**Evidence.** `SCHEDULER.start()` is called in `src/jarvis/edge/brain_bridge.py:50` — on the **laptop
edge** — while the brain server (`src/jarvis/brain/server.py`) starts only the proactive engine, never
the scheduler. `Scheduler.add_reminder()` adds jobs to a SQLite jobstore but does **not** start the
scheduler; nothing starts it server-side.

**Why it matters.** The whole point of the brain being always-on (VPS) is that timed work fires even
when the PC is off. Today a recurring/daily reminder only fires while the laptop edge is running, and
a phone- or glasses-only session has **no running scheduler at all**. The one-shot ntfy path (Phase
4b VPS ticker) still works, so this isn't "reminders never fire" — it's "reminders depend on the
laptop being awake," which contradicts the 24/7 promise.

**Fix.**
- Start `SCHEDULER` inside `server.serve()` with a brain-side `on_speak` emitter that routes a fired
  reminder through `BrainServer.proactive_emit(...)` (speak to any connected device, else ntfy push) —
  the same network-aware path the proactive engine already uses.
- Make the edge stop owning the scheduler when it's talking to a remote brain (keep the local-only
  fallback for a fully-local run, but don't double-fire: exactly one process owns the jobstore).
- Guard against double-push: the existing `push_phone`/ntfy-window logic must still hold when the
  owner is the brain.

**Extent (acceptance).** With only the brain running (no laptop edge), a reminder set for +1 min
fires and is delivered (spoken to a connected client, or ntfy push if none). Exactly one delivery,
no duplicates. A daily reminder survives a brain restart (persisted jobstore).

**Verify.** Extend `bench/test_phase4_system_protocols.py` (or a new `test_scheduler_brain.py`):
start `BrainServer`, schedule +2 s, assert the emitter is invoked exactly once with the message.

### 2. Package the brain as a deployable always-on service  ✅ DONE
**Evidence.** `deploy/vps/` ships only the **ticker** (`jarvis-ticker.service`, `install.sh`). There
is no `jarvis-brain.service` and no brain install/health script. The edge already has
`scripts/install_edge_service.ps1` + `uninstall_edge_service.ps1`; the brain has no equivalent.

**Why it matters.** "24/7" requires the brain to start on boot, restart on crash, and be reachable.
Right now it's a foreground `python -m jarvis.brain.server` — one closed terminal from death.

**Fix.**
- Add `deploy/vps/jarvis-brain.service` (systemd: `Restart=always`, `RestartSec`, `EnvironmentFile`
  pointing at the `.env`, `WantedBy=multi-user.target`, sane `MemoryMax`/`OOMScoreAdjust`).
- Add `deploy/vps/install-brain.sh` (uv sync the `brain`+`channels` extras, enable+start the unit,
  print a health line) and a `/healthz`-style check (a tiny WS ping or an HTTP liveness route).
- Document the bind: brain on `127.0.0.1` behind the existing tunnel, or `0.0.0.0` **with**
  `JARVIS_API_AUTH_TOKEN` set (the server already enforces the bearer token when it's non-empty).

**Extent.** `systemctl enable --now jarvis-brain` brings the brain up; `systemctl kill` proves it
auto-restarts; a health check returns OK. The final `deploy` run is yours; the artifacts are ours.

**Verify.** A `deploy/vps/README.md` runbook + the health check returning OK locally (the unit file
is validated with `systemd-analyze verify` where available, else reviewed).

### 3. Edge↔brain auto-reconnect with backoff + heartbeat  ✅ DONE
**Evidence.** The edge `BrainBridge` opens one WebSocket; there is no reconnect loop. If the brain
restarts (deploy, crash, OOM) the edge stays silently disconnected until the user restarts it.

**Why it matters.** Over a week the brain *will* restart at least once. Without reconnection the
companion goes mute with no signal. This is the most common "silent death" in always-on systems.

**Fix.**
- Wrap the edge's brain connection in a supervised loop: on disconnect, reconnect with exponential
  backoff (cap ~30 s) + jitter; re-send `Hello` on reconnect to re-register the session.
- Add an application-level heartbeat (periodic ping / lifecycle frame) so a half-open socket is
  detected and recycled rather than hanging.
- Surface state to the TUI ("reconnecting…") so a degraded link is visible, not silent.

**Extent.** Kill the brain mid-session; within backoff the edge reconnects automatically and the next
utterance works, with no manual restart. A dropped (half-open) socket is detected within one
heartbeat interval.

**Verify.** A test that stands up `BrainServer`, connects a client, restarts the server, and asserts
the client re-establishes and completes a turn.

---

## P1 — Needed before trusting it unattended

### 4. Resilience under fault injection  ✅ DONE
**Evidence.** Degradation is tested **per tool** (missing key → spoken "not configured"). Pipeline-
level faults are not: freellmapi dropping mid-turn, a TTS stream cutting, the WS disconnecting between
chunks, Redis or the scheduler SQLite being unavailable.

**Why it matters.** Unattended, these *will* happen. The system must keep its footing — fall through
the LLM fallback chain, recover the socket, keep serving without the cache — rather than wedge or
crash the turn.

**Fix.** A `bench/test_resilience.py` that injects each fault and asserts graceful behaviour:
- LLM primary raises → next model in `settings.llm_chain` answers (already coded; prove it end-to-end).
- Redis URL points at a dead port → cache silently falls back to in-process (already coded; assert
  `backend == "memory"` and the turn still completes).
- Scheduler jobstore path unwritable → `add_reminder` returns a spoken error, doesn't crash the brain.
- A `respond()` that raises inside a tool → the turn returns a safe spoken line, audit records the
  failure, history isn't corrupted.

**Extent.** Every injected fault yields a *speakable* outcome and a still-running brain; no unhandled
exception escapes a turn.

**Verify.** `test_resilience.py` green; add it to `run_all_tests.py`.

### 5. Prove the offline (local-first) path
**Evidence.** Local STT (`whisper`/`moonshine`) and TTS (`piper`/`kokoro`) are wired, but
`JARVIS_OFFLINE_STT_ENABLED` / `_TTS_ENABLED` default **false** and the Phase-1 "unplug the network"
run has never happened. The local-first promise is currently unverified.

**Why it matters.** Local-first is a stated non-negotiable. If the cloud STT/TTS keys lapse or the
network drops, Jarvis must still hear and speak. Today that's an assumption, not a fact.

**Fix.** A guided `bench/voice_offline_check.py`: force local providers + a small offline LLM (or a
canned brain), run one full turn with the network blocked, and report STT text + TTS audio produced.
Document the one-time model downloads.

**Extent.** With the network down and offline flags on, one full spoken turn completes locally.

**Verify.** The harness is ours; the final run needs your machine + a one-time model fetch (P2-style).

### 6. Long-running memory hygiene (compaction / rotation)  ✅ DONE
**Evidence.** `memory/learned/*.md` and `memory/journal/*.md` grow unbounded; there is no dedup,
compaction, or rotation. The startup digest pulls the most recent N (now capped at 12).

**Why it matters.** Over weeks: duplicate/contradictory learned facts degrade recall quality, journal
files bloat, and the prompt budget we just reclaimed is slowly re-spent. A 24/7 companion accumulates
state every day — it needs a janitor.

**Fix.** A scheduled maintenance job (daily, via the brain scheduler from item 1):
- De-duplicate near-identical learned facts (normalise + similarity), keep the newest.
- Roll journal files monthly; archive old ones out of the hot path.
- Optionally summarise stale facts into a compact "long-term" file so nothing is lost but the active
  set stays small.

**Extent.** Learned-fact count stays bounded with no duplicates; recall quality holds; the digest
stays within budget indefinitely.

**Verify.** `bench/test_memory_hygiene.py`: seed duplicates + an old journal, run compaction, assert
dedup + rotation + that recall still finds the canonical fact.

### 7. Security pass on the high-power tools  ✅ DONE
**Evidence.** `run_powershell` (incl. elevated), the auto-login browser (types your real credentials),
and system file/dir delete are all confirm-gated — good — but never security-reviewed. Logs/audit
should never carry secrets.

**Why it matters.** These run on *your* machine with *your* privileges, autonomously, 24/7. The
confirm tier stops the obvious; it doesn't stop injection, an over-broad delete that slips the
protected-paths check, or a secret leaking into a log line.

**Fix.**
- Review `run_powershell` for injection/escaping; confirm the protected-paths refusal covers
  symlinks, UNC paths, env-var expansion, and drive roots.
- Confirm the browser never echoes typed credentials into logs/audit; confirm `audit.py` redaction
  covers every secret-shaped field.
- Tighten `coding.py::_safe_path` review (already blocks `.env`/sessions/voiceprint/`audit/`) for any
  bypass.
- Capture findings + fixes in `SECURITY.md`.

**Extent.** A documented review with each finding either fixed or explicitly accepted; redaction
proven by test.

**Verify.** `bench/test_security_hardening.py`: injection attempts refused, protected-path escapes
refused, a secret passed through a tool never appears in the audit record.

---

## P2 — Validation that needs your hardware to finish (engineering is ours)

### 8. Measure TTFW + VAQI on real hardware
**Evidence.** The Phase-5 instruments exist (`bench/`), but no real numbers have ever been produced —
TTFW (time from you stopping to Jarvis's first word) and VAQI (interruption/missed-response/latency
composite) are unmeasured. This is *the* "is it actually fast and natural" question.

**Fix.** A one-command `bench/voice_live_bench.py`: you speak ~10 scripted utterances; it logs TTFW
per turn, barge-in success, and missed responses, then prints VAQI. The brain slice (TTFT) is already
measured; this closes the loop through STT + TTS on your mic/speaker.

**Extent.** Real TTFW (target ≤~1.2 s local) and a VAQI baseline logged across a 10-utterance battery.

**Verify.** You run it once; we read the numbers and tune from real data.

### 9. Barge-in / AEC live check
**Evidence.** `barge_in_mode="auto"` (headphones vs speakers) is coded but never tested against real
self-hearing. On open speakers the mic can re-hear the TTS.

**Fix.** A short live procedure (part of item 8's harness): confirm barge-in interrupts on headphones
and that the half-duplex gate prevents self-interruption on speakers.

**Extent.** Barge-in interrupts mid-sentence on a private endpoint; no self-interruption on speakers.

### 10. Live integration happy-paths
**Evidence.** Every credentialed tool is only *degradation*-tested. The real read-email / write-Notion
/ read-Telegram / calendar-create paths have never run against live APIs.

**Fix.** Make `bench/test_live_integrations.py` comprehensive (one real call per integration, writes
behind a `--allow-writes` flag). It runs green only once your keys are in.

**Extent.** One successful live call per configured integration, writes confirmed against a scratch
target.

**Verify.** You add keys (your `TODO-NOW.md` steps); we run the live suite.

---

## P3 — Roadmap (not MVP)
**Multi-device (Phase 6).** Android/Termux edge-lite, the iPhone web client, and the Mentra glasses
bridge are scaffolded but unvalidated. Not required for the PC companion to be production-ready;
revisit after P0–P2 land.

---

## Execution order
1. **P0 #1** scheduler-in-brain → **#2** brain service unit → **#3** edge reconnection (the 24/7 spine).
2. **P1 #4** resilience tests → **#6** memory hygiene → **#7** security pass (the unattended-trust layer).
3. **P1 #5** offline harness + **P2 #8–10** live harnesses (built now, you run them once).
4. **P3** multi-device, later.

Gate after each: `uv run python bench/run_all_tests.py` stays green, new guards added per item.
