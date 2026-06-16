# Testing Jarvis — how to verify everything

This is the single guide to testing every capability built across the roadmap (Phases 0–13) and the
two fine-tuning passes (efficiency + production-readiness). Testing is layered into **tiers** by what
each needs — nothing, the brain online, your API keys, your microphone, or a full deployment. Run the
tiers that apply to you; Tier 0 alone proves the whole codebase is internally sound.

> **Legend for results.** Test scripts print `[PASS]/[FAIL]` per check and `=== N/M passed ===`.
> The aggregate runner prints `PASS` / `FAIL` / `SKIP`. **SKIP is not failure** — it means a test
> needs something absent right now (the brain proxy, or the gated fleet path).

---

## Tier 0 — One command (the regression gate)

```bash
uv run python bench/run_all_tests.py
```

Runs the whole hermetic suite + the one online brain test, in order, with a single summary. **Expected
today: `24 passed, 0 failed, 1 skipped`** (the skip is the intentionally-gated OpenClaw fleet connect).

- **What it proves:** every component is wired, schemas are well-formed, every credentialed tool
  *degrades gracefully* when unconfigured, the safety rails hold (path traversal, secret refusal,
  reversible-git-only, confirm-gating), the 24/7 spine works (scheduler-in-brain, edge reconnect),
  and the system survives injected faults.
- **What it does NOT prove:** that a credentialed integration actually *succeeds* against the live
  API (only that it degrades), or that the voice loop is fast/natural on real hardware. Those are
  Tiers 3–4.
- **Run one test alone:** `uv run python bench/<name>.py` (e.g. `bench/test_resilience.py`).

### Capability → test map (all covered by Tier 0)
| Capability | Test |
|---|---|
| Config & secrets load (no secrets printed) | `check_config.py` |
| VAD + barge-in decision logic | `test_phase1_vad_bargein.py` |
| Wake word loads, faster than realtime | `test_wakeword.py` |
| Vault read/search, web, Telegram tools + ispir-only delegation | `test_phase3_tools.py` |
| Files/processes/PowerShell + protocols + browser | `test_phase4_system_protocols.py` |
| Speaker biometrics logic + TTFW/VAQI metric math | `test_phase5_identity_bench.py` |
| Multi-device routing + brain WS server | `test_phase6_multidevice.py`, `test_phase6_brain_server.py` |
| Memory L1/L2, L4 cache, L5 semantic | `test_phase9_memory.py`, `_9b_cache`, `_9c_semantic` |
| Proactive engine (budget/quiet-hours/clarify-confirm) | `test_phase10_proactive.py` |
| Gmail/Calendar/Home-Assistant/Notion (graceful) | `test_phase11_integrations.py`, `_notion` |
| Utilities belt (weather/crypto/fx/convert/…) | `test_phase12_utility.py` |
| Audit log + self-health + modes/routines | `test_phasex_audit_health_modes.py` |
| Coding tools + git safety + skills | `test_phase13_coding.py` |
| **Fine-tune #1:** lean prompt + tool surface + fast primary | `test_finetune.py` |
| **Prod #1/#3:** scheduler-in-brain, edge auto-reconnect | `test_scheduler_brain.py`, `test_edge_reconnect.py` |
| **Prod #4/#6/#7:** resilience, memory hygiene, security | `test_resilience.py`, `test_memory_hygiene.py`, `test_security_hardening.py` |
| Brain agent end-to-end (LLM + tools + memory) | `test_brain_agent.py` *(online; auto-SKIP if proxy down)* |

---

## Tier 1 — Offline diagnostics (no creds, informational)

Not pass/fail — they print numbers/answers you read.

```bash
uv run python bench/efficiency_report.py     # prompt size, per-turn tool surface, cache, TTFT
uv run python bench/list_audio_devices.py     # what speaker/headphone targets resolve to
```

`efficiency_report.py` is the source of truth for the fine-tuning targets (prompt ≤2000 tok → ~1796;
tool surface ≤48 → 40 core). Re-run it after any prompt/tool change.

---

## Tier 2 — Brain online (needs the freellmapi tunnel up, no other keys)

Bring up the tunnel so `http://localhost:3001/v1` reaches the VPS proxy, then:

```bash
uv run python bench/test_brain_llm.py        # streaming + tool-calling + model failover
uv run python bench/verify_multilingual.py   # understands EN/FR/DE/HY/RU/UK, always replies in English
uv run python bench/llm_bench.py             # TTFT + correctness per candidate model
uv run python bench/test_model_tiers.py      # pick the fast conversational tier
```

If the tunnel is down these error out quickly (and `test_brain_agent` in Tier 0 SKIPs rather than
FAILs). `llm_bench.py` is how the fast primary (`llama-3.1-8b-instant`) was chosen.

---

## Tier 3 — Live integrations (needs your API keys / logins)

These call the **real** services, so first do the one-time logins (each writes a token/session into
`.env` or a session file — see `TODO-NOW.md`):

```bash
uv run python bench/telegram_login.py        # Telethon session (read your unread DMs)
uv run python bench/google_login.py          # Gmail + Calendar refresh token
# (Notion just needs JARVIS_NOTION_TOKEN in .env + sharing pages with the integration)
```

Then verify everything that has keys, two ways:

```bash
uv run python bench/test_live_integrations.py   # one green/red line per external service
uv run python bench/demo_live_actions.py        # JARVIS performs each action himself via NL commands
```

`test_live_integrations.py` is the *infrastructure* check (does the key work?). `demo_live_actions.py`
is the *behavioural* check (does Jarvis choose and use the tool correctly?). Anything you haven't
configured shows as "not configured" — expected, not a failure. **This is P2 #10.**

---

## Tier 4 — Voice on real hardware (needs your mic + speaker)

The one part no automated test can stand in for. Build up from "does the pipe open" to "is it fast
and natural."

```bash
uv run python bench/run_hello_timed.py       # Phase-0 pipe: mic/speaker open, Deepgram+ElevenLabs connect (8s, no voice needed)
uv run python bench/run_assistant_timed.py   # Phase-1: wake-word model loads + gates wire (8s, no voice needed)
uv run python bench/stt_language_check.py    # speak a few seconds in each language -> transcribed text
uv run python bench/enroll_voice.py          # record clips -> voiceprint.json (then set JARVIS_SPEAKER_ID_ENABLED=true)
```

Then the **live loop** (start the assistant and actually talk to it):

```bash
uv run python -m jarvis.edge.assistant
# Say: "Hey Jarvis, what time is it?"  -> wakes, transcribes, answers in his voice.
# Confirm: ambient TV speech is ignored; barge-in interrupts him mid-sentence (headphones only).
```

What to check by hand here (the roadmap's voice acceptance criteria):
- **TTFW** — gap from you stopping to his first word feels ≲1.2 s. `bench/benchmarks.py` holds the
  TTFW/VAQI metric implementation; a one-command scripted 10-utterance battery is **not built yet**
  (P2 #8 — ask me to add `bench/voice_live_bench.py`).
- **Barge-in / AEC** — interrupts on headphones, no self-interruption on speakers (P2 #9).
- **Speaker ID** — after enrolling, a different speaker is ignored, your voice is served.

---

## Tier 5 — Offline / local-first (P1 #5 — harness not built yet)

The local-first promise (local STT + TTS, no cloud) has the pieces wired but no one-command check.
Manual procedure for now:

```bash
# In .env: JARVIS_STT_PROVIDER=whisper, JARVIS_TTS_PROVIDER=piper,
#          JARVIS_OFFLINE_STT_ENABLED=true, JARVIS_OFFLINE_TTS_ENABLED=true
# Disconnect the network, then run the live loop and confirm one full spoken turn works locally.
uv run python -m jarvis.edge.assistant
```

Ask me to add `bench/voice_offline_check.py` to make this a single guided run.

---

## Tier 6 — 24/7 deployment (the brain service + resilience, on the VPS)

Proves the production spine end-to-end (P0 #1/#2/#3). Run **on the VPS** after `install-brain.sh`:

```bash
curl -fsS http://127.0.0.1:8766/healthz                  # -> ok   (liveness)
sudo systemctl kill jarvis-brain                          # restart proof: returns within ~5s
journalctl -u jarvis-brain -f                             # watch turns / reminders / proactive ticks
```

Behavioural checks against the running brain:
- **Reminder fires 24/7:** ask Jarvis to "remind me in 2 minutes…"; with the laptop *off*, confirm it
  speaks to a connected phone/glasses client, or pushes to your phone via ntfy.
- **Edge reconnects:** with a client connected, `systemctl restart jarvis-brain`; the client should
  reconnect on its own and the next turn works (this is exactly what `test_edge_reconnect.py`
  automates).
- **Memory hygiene ran:** after the daily 04:00 job (or trigger `run_maintenance` manually), check the
  log line and that `memory/learned/archive/` + `memory/journal/archive/` appear as the store grows.

---

## Tier 7 — Full manual acceptance (the roadmap's end-to-end script)

One sitting that exercises the whole companion, in order:
1. **Cold boot** the PC → edge auto-starts (Windows service from `scripts/install_edge_service.ps1`)
   and connects to the brain.
2. **"Hey Jarvis"** wakes only on your voice (Tier 4 enrollment), ignores the TV.
3. **Direct question** answers locally and fast; a **hard/multi-step question** is delegated to the
   fleet (only if you've armed `JARVIS_FLEET_AUTHORIZED=true`) with spoken progress + a cited answer.
4. **"Search my vault…", "any unread Telegram?", "open this site…"** all work (Tier 3 keys).
5. A **reminder** set earlier fires — spoken if you're at the PC, ntfy push if not (Tier 6).
6. **Same command from phone/glasses** hits the same brain/session.
7. A **proactive nudge** appears at a sensible moment (within budget + outside quiet hours).

---

## Quick reference

| I want to test… | Do this |
|---|---|
| Everything that needs nothing | `uv run python bench/run_all_tests.py` |
| Just one capability | `uv run python bench/test_<name>.py` |
| Efficiency targets (prompt/tools/TTFT) | `uv run python bench/efficiency_report.py` |
| The brain LLM itself | Tier 2 (tunnel up) |
| My real API keys work | Tier 3 (`test_live_integrations.py` + `demo_live_actions.py`) |
| The actual voice experience | Tier 4 (`-m jarvis.edge.assistant`) |
| Offline mode | Tier 5 (manual; harness pending) |
| 24/7 deployment survives restarts | Tier 6 (on the VPS) |
| The whole thing as a user would | Tier 7 |

**Gated by design:** `bench/test_fleet_connect.py` (live OpenClaw fleet) stays SKIP until a sanctioned
path is enabled — that's intentional, not a gap.
