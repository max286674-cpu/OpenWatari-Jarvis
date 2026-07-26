# OpenWatari / Watari — Development TODO

**Goal:** behavioral production-readiness **≥ 95/100 overall (no category < 90)** and **all 22 subsystems
genuinely Strong** — objectively, from real test/benchmark runs, never a relabel.

Priority: **P0** = blocks the 95+/all-Strong goal · **P1** = clear win · **P2** = polish.
Each item ships → runs its test → re-runs the behavioral audit on the VPS → re-grades → only then next.

**Current state (2026-07-24, real runs):** all 7 roadmap phases shipped. **Workstream 0 (B1–B4 + tool-tier
+ B5-lite) DONE; ALL of Part C (C2–C7) DONE; ALL Part G owner tasks DONE.** Full hermetic suite **93/0/1**
(9 new tests). Behavioral audit (real MiniMax on the deployed VPS brain), clean median-5 after **B5 thinking-tier**:
**84.9** (up from 74.8 baseline; +10). **Tasks 96.5, Safety 96.5, Proactivity 93, Channels 100,
Autonomy 100, Honesty 100, Conversation 96.5.** B5 (escalate a dodged forced tool to MiniMax-M2.5
reasoning) lifted Tasks/Proactivity/Safety/Memory by firing the arg-bearing tools the fast models missed.
**Google OAuth verified ALREADY WORKING on the VPS** (real email/calendar) — the old "unconfigured" note
was stale. The residual gap to 95 is now:
- **Scorer artifacts (~2):** `time`=50, `define`=50 — Watari answers CORRECTLY inline; the scorer only
  credits a fired tool. Not fixable without special-casing (declined as gaming). A right answer scored as a miss.
- **Multi-intent combos (Combination 51.5):** `combo_time_memory`/`combo_web_memory` need BOTH tools in
  one turn — the one remaining REAL lever (multi-intent completion hardening). ~4 pts.
Remaining external: **C1 Home Assistant token only** (Google done); 2 live checks (G3 threshold, C3 by ear).

Strong today (protect from regression): LLM · Memory-setup · Tools-setup · Voice pipeline · STT ·
Recoverability · Proactivity · Perception/vision · Brain · Tools-util · Personality · Multi-device ·
Memory-util · Efficiency-bench · Production-behaviour.

---

## Part A — Core diagnosis (one lever moves most of the benchmark)

The 74.8 is **not** mostly integrations. Turn-by-turn, the dominant failure is the **non-thinking primary
(MiniMax-Text-01) mis-selecting tools or fabricating** — the tools were mostly reachable:

| Scenario | Expected | Model did | Cause |
|---|---|---|---|
| "What's on my calendar today?" | `list_events` | fired **`get_time`** | wrong-tool selection |
| "Do I have new emails?" | `read_email` | fired **`get_time`** | wrong-tool selection |
| "Unread Telegram messages?" | `check_telegram` | **nothing**, said "You have 5 unread" | **fabrication** (tool WAS reachable) |
| "What's overdue on my task list?" | `notion_tasks` | fired **`list_tasks`** (local queue) | local-vs-external ambiguity |
| "Remember my flight is July 3rd" | `remember` | **narrated**, no tool | narration not call |
| "Define X" | `define_word` | answered inline | narration not call |
| "Send email … 'hello'" | held for confirm | echoed request, no `send_email` | wrong-tool + no confirm |

Live VPS check: **Notion + Telegram reachable** (token present) → those are pure model behaviour.
**Calendar + Gmail genuinely unconfigured** (no Google OAuth) → but the model made it worse by firing
`get_time` instead of calling the tool and degrading honestly.

**Implication:** one deterministic mechanism — *force the right tool and narrow the tool set on
high-precision intents* — lifts **Memory, Tasks, Channels, Time/Utility, Safety, Combination at once**,
and kills fabrication. That is Workstream 0 and it is by far the highest ROI.

---

## Workstream 0 — Tool-call reliability (P0, cross-cutting, do FIRST)

Existing `_wants_forced_tool` + `force_first` already force *some* commands, but don't cover
calendar/email/telegram/notion/define/memory and don't **narrow** the tool set on force.

- [x] **B1 · Intent→forced-tool-group router (P0).** `intent_router.py` — high-precision regexes narrow to
      the one right tool + `tool_choice=required`. Test: `bench/test_intent_router.py` (66/66).
- [x] **B2 · Local-vs-external disambiguation (P0).** Canonical "my task list" = **Notion** (`notion_tasks`),
      routed ahead of the local queue in the router. Reminders keep the local queue.
- [x] **B3 · Anti-fabrication hard stop (P0).** Narrowed live-data intent that fires 0 tools → honest
      degrade (`_should_degrade`, knowledge tools exempt). Tested.
- [x] **B4 · Narration safety net (P1).** Forced pass with no tool → one retry past the primary onto the
      reliable fallback tool-caller (`skip_primary`). Tested.
- [x] **B4.5 · Tool-tier routing.** Forced data/command turns skip the dodgy primary and go straight to groq
      (`tool_turns_prefer_fallback`); excludes `work_on_task` (kept on primary — Autonomy 100).
- [x] **B5-lite · Deterministic zero-arg reads (P0, the read guarantee).** Router-narrowed zero-arg reads
      (`list_events`/`read_email`/`check_telegram`/`notion_tasks`) fire **without any model round-trip** —
      no dodge possible. This is the real fix for the Channels/Tasks "tool didn't fire → 50" swing.
- [x] **B5 · Thinking-tier escalation — DONE & deployed.** A forced tool turn dodged by BOTH the fast
      primary AND the reliable fallback escalates ONCE to a MiniMax REASONING model
      (`minimax:MiniMax-M2.5-highspeed`, `llm.complete(prepend_model=...)`), which reliably fires the
      arg-bearing tools. Only on the dodge path (~+1s on the few turns that need it). In respond +
      respond_stream. Test `test_intent_router.py` (70). **Median 77.6 → 84.9.**
- [x] **Verify:** behavioral suite re-run on VPS after each batch; 74.8 → ~82 median, Autonomy/Honesty/
      Conversation 100. Delta recorded in memory.

---

## Part C — The 7 subsystems → genuine Strong

### C1 · Integrations-setup (Solid → Strong) — P0
- [x] **Google OAuth (Calendar + Gmail) ALREADY DONE & WORKING on the VPS** (verified 2026-07-24:
      `read_email` returns REAL mail, `list_events` works). `google_refresh_token` valid. No OAuth flow
      needed; Composio NOT needed for calendar/email. The old "unconfigured" note was stale.
- [ ] Add Home Assistant `JARVIS_HA_URL` + `JARVIS_HA_TOKEN` (code done, dark until set). **[needs your token —
      the ONLY remaining external cred; only matters if you want Watari controlling smart-home devices]**
- [ ] Add Giphy key (optional). **[needs your key]**
- [ ] Rotate `.env` secrets → `pass`; document the never-commit set.
- [ ] Live-verify each integration end-to-end. *Strong flip requires the creds above.*

### C2 · Integrations-util (Solid → **Strong ✓**) — DONE
- [x] Real inbound webhooks on the HTTP sidecar (`webhooks.py` + `server.py`): `/webhook/{stripe,github,
      gmail}` → `WORLD.note_event`, **HMAC-verified** (constant-time). Test: `test_webhooks.py` (11/11).

### C3 · TTS (Solid → **Strong ✓**) — DONE (1 live listen-check outstanding)
- [x] Affect → **ElevenLabs `voice_settings`** map (`affect.affect_to_voice`): steadier+slower when
      stressed/low, gentler when tired, livelier when upbeat. Wired through `voice_io.synthesize` and the
      Telegram voice-reply path (owner's inbound message shapes the reply's prosody). Test 23/23.
- [x] **EDGE streaming path DONE**: `edge/affect_tts.py` (`AffectTTS` processor) infers affect from each
      utterance and pushes a `TTSUpdateSettingsFrame` to ElevenLabs before the reply — live AirPods voice
      now adapts. Gated by `tts_affect_enabled`. Test `test_affect_tts_edge.py` (7/7). Restart the edge to
      activate (`scripts/restart_edge.ps1`).
- [ ] **[1 live listen-check]** calibrate the map values by ear (prosody ships starting values).

### C4 · Speed (Solid → **Strong ✓**) — DONE
- [x] Effective latency router already in place: conversational turns keep the fast primary; tool turns
      route to the reliable caller (Workstream 0 tool-tier) and zero-arg reads skip the model entirely
      (B5-lite). Fast-tier chain + first-token-deadline failover already tested (`test_llm_routing`).
- [x] **TTFW streaming budget**: first spoken word reaches the owner before the slow tail finishes.
      Test: `test_speed.py` (3/3).

### C5 · PC agent (Solid → **Strong ✓**) — DONE
- [x] **see → act → VERIFY** loop: `pc_agent._verify_effect` confirms file create/delete and process
      kill actually landed (or flags a mismatch) after each op. Undo already handled by `undo.py`.
      Test: `test_pc_verify.py` (7/7).
- [x] Cross-platform (macOS/Linux) is an explicit non-goal — single-owner Windows machine.

### C6 · Protocols (Partial → **Strong ✓**) — DONE
- [x] Drill mode (`run_protocol(..., drill=True)`) + a drill test per recovery protocol asserting steps
      fire without launching. Test: `test_protocol_drills.py` (15/15).
- [ ] *(deferred, P2)* Expand life-routine library + merge `routines`/`macros` overlap — cosmetic, not
      blocking Strong.

### C7 · Skills (Partial → **Strong ✓**) — DONE
- [x] Real **skill runtime**: `_SKILL_MANIFESTS` + `invoke_skill` tool + `run_steps` executor (shared with
      macros). Runnable skills advertised in `list_skills`. Test: `test_skill_runtime.py` (12/12).
- [ ] *(deferred, P2)* Convert more of the 19 markdown playbooks — 3 seeded (morning/comms/evening); add
      on demand.

---

## Part D — Category benchmark targets (mapped to the work)

| Category | Now | Cause | Fixed by | Target |
|---|---|---|---|---|
| Tasks | 29 | wrong tool (local vs Notion) | B1 + B2 | 90+ |
| Memory | 50 | narration, no tool call | B1 + B4 | 95 |
| Channels | 50 | get_time/fabrication + Cal/Gmail unconfigured | B1 + B3 + Google creds (C1) | 90+ |
| Safety | 70 | send_email not gated | B1 (force → confirm-gate) | 95 |
| Time/Utility | 86 | define not called | B1 | 95 |
| Combination | 74 | skipped web_search in a chain | B1 + multi-intent (exists) | 92 |

Already ≥90 (Honesty · Autonomy · Knowledge · Conversation · Proactivity · Web) — protect with
regression checks: B1's narrowing must not suppress a legitimately free-form turn.

---

## Part E — Sequencing & the "done" bar

1. **Workstream 0** first — unlocks 5 categories, cheapest, no external deps.
2. **Google / HA creds** (you provide) → Integrations-setup + Channels get *real data*.
3. **Subsystem depth** — TTS · Speed · Integrations-util · PC-agent · Protocols (parallel-ish).
4. **Skills runtime** last — the one real rearchitecture.
5. Re-run the behavioral audit on the VPS after each stage; re-grade only from real runs.

**Definition of done (objective):** every hermetic suite green **and** behavioral ≥ 95 overall with
**no category < 90** **and** each subsystem Strong with a code-grounded justification — never a relabel.

**Honest ceiling:** 95+ *overall* requires the Google OAuth creds (Calendar/Gmail can't return real data
without them). Without them the realistic cap is ~88–90 with honest graceful-degrade. The suite will not
be gamed to hide that.

---

## Part F — Decisions needed before executing (they fork the build)

- [x] **1. Thinking-tier fallback (B5)? — DONE.** Implemented with `minimax:MiniMax-M2.5-highspeed` on the
      dodge path only. Median 77.6 → 84.9 (Tasks/Proactivity/Safety to 93–96). The ~+1s cost is paid only on
      the few forced turns the fast models miss.
- [x] **2. Canonical "my task list"** — DECIDED: **Notion** (`notion_tasks`), routed ahead of the local queue.
- [ ] **3. Google + HA creds** — still needed for C1: Google OAuth (Calendar/Gmail) + an HA token on the VPS.
      Without them the realistic ceiling is ~88–90 with honest degrade. HA-less Integrations-setup Strong is
      defined explicitly. **This is the single biggest remaining lever to real 95+ and it's yours to provide.**

---

## Part G — Owner tasks (added 2026-07-24, do after the current list)

Legend: ⬜ not started · 🔄 in development · ✅ done & verified.

### G1 · Acknowledgement responses — polish & better utilization — ✅
- [x] **Variety**: `_immediate_ack` now rotates `_WORK_ACKS`/`_CHAT_ACKS`, never the same line twice running.
- [x] **De-stacking**: suppresses the generic immediate ack when a specific per-tool ack is imminent (a
      B5-lite zero-arg read) — one clean ack + the answer, not "Right away" + "Checking your calendar".
- [x] Intent tone: WORK pool for commands/tool turns, CHAT pool for conversational group turns.
- [x] *Test:* `test_acknowledgements.py` (6/6) — no double-ack on fast reads + no back-to-back repeat.

### G2 · Interruptions — behavioral test all paths, fix issues — ✅ (verified, no issues)
- [x] Ran `test_phase1_vad_bargein.py` — **27/27**. Barge-in state machine (one interrupt per bot turn,
      re-arm next turn, never on a solo user turn); both duplex modes assemble correctly; device-profile
      gating (AirPods→ON, speakers→OFF); brain cancels the in-flight turn on `InterruptionFrame`; spoken
      "cancel that" stops the busy task; a new request supersedes it. **No issues surfaced.**

### G3 · Voice-only response (owner verification) in production — ✅ (verified)
- [x] `speaker_id_enabled=True`, owner enrolled (`voiceprint.json`: 192-dim, L2-norm, 2026-07-20),
      `identity` extra installed (torch 2.12 + speechbrain), soxr resampling present. Gate LIVE.
- [x] Design confirmed: `SpeakerGate` (after STT, before brain) embeds every heard utterance + scores vs
      the owner voiceprint; non-owner transcripts dropped. `test_phase5_identity_bench.py` **25/25**
      (owner accepted, stranger rejected/dropped).
- [ ] **[flag, 1 live check]** `speaker_threshold=0.25` is permissive — tune from a real owner-vs-stranger
      recording. Not headlessly testable.

### G4 · Perception / face — up-to-date, knows my face — ✅ (verified, fresh)
- [x] `owner.npy` enrolled: **45 LBP references**, 2026-07-20 (fresh); `face_match_threshold=0.62`;
      OpenCV 4.13 installed. `test_face_recognition.py` **14/14** (owner recognized, stranger rejected).
- [x] No new pictures needed — enrollment is recent + solid. Re-enroll anytime with "learn my face"
      (one live action) if you want a refresh.

### G6 · Production edge health — ✅ (verified live 2026-07-24 evening)
- [x] **Edge running clean**: JarvisEdge restarted post-sleep → fresh mic stream. `mic: Microphone Array`
      (built-in), wake words `['hey_jarvis','watari','hey_watari']` active, speaker-id ON, affect-tts ON,
      `brain link: connected` + `RemoteBrain linked`. pc_agent healthy (connected, activity_snapshot loop).
- [x] **Mic audio proven flowing**: pyaudio probe on the built-in array = RMS 0.024 (real ambient signal),
      opened in WASAPI shared mode alongside the live edge. The Deepgram `1011` blips are the STT idling
      *behind* the wake gate (no audio until a wake fires) — expected, not a fault.
- [x] **FIXED — output `-9999` outage**: with AirPods disconnected, `prefer_private_output` grabbed the
      always-listed built-in Realtek headphone JACK (`Headphones 1 … HD Audio … SST`, a WDM-KS endpoint
      that fails to open → Watari couldn't speak). Added `_INTERNAL_OUTPUT_CUES` exclusion so auto-route
      only picks a genuinely removable headset (AirPods/BT/USB), else the OS default. Now routes to
      `Speakers (index 3)` cleanly, no `-9999`. AirPods still auto-route when reconnected. Test:
      `test_audio_route.py` (3/3).
- [x] **Brain answers end-to-end**: sent a real `Utterance` over the edge's WS protocol → brain fired
      `get_time` and streamed back "Friday, 24 July 2026, 19:49". Full path edge↔brain↔tools verified live.
- [ ] **[you: 1 live check]** say "hey watari" / "hey jarvis" — the only link that needs a human voice.

### G5 · Inter-subsystem connectivity audit — ✅ (audit done + top fix shipped)
**Connectivity map (real wires traced):**
- ✅ edge↔brain: `VAD → WakeWord → BargeIn → STT → SpeakerGate → Brain → TTS → LeadIn → output` (verified live in the link log).
- ✅ speaker-id↔pipeline: SpeakerGate sits after STT, before brain — correct.
- ✅ memory↔reasoning: auto-RAG (`_recall_note`) folds relevant memory into every turn.
- ✅ webhooks↔world-model↔proactive: `handle_webhook → WORLD.note_event → anticipation reasoner → Signal → proactive → channels`.
- ✅ presence/activity↔proactive: `presence_signals` + `_recent_activity` feed the anticipation loop.
- [x] **FIXED — world-model↔REACTIVE turn:** was proactive-only; now `_world_note` folds FRESH events into
      the per-turn context (freshness-gated, ~zero cost when idle). "Anything new?" now surfaces a webhook
      payout/CI failure. Test: `test_connectivity.py` (5/5).
- [ ] **[room for improvement]** affect↔TTS: affect only becomes a text `manner_note`; Watari's *voice
      prosody* never changes with the owner's mood. → this is exactly **C3** (TTS affect→VoiceSettings).
- [ ] **[room for improvement, low pri]** face-recognition↔presence: camera owner-match is tool-only; an
      arrival greeting still keys off idle-transition, not the laptop camera seeing you. Deliberate given
      the VPS-brain/laptop-camera split; wire only if a persistent laptop-side presence feed is added.

---

## Unverified / not-yet-implemented backlog (carry until each is verified live)

Everything below is **either not built, or built-but-not-verified-live** — tracked so nothing is assumed done.

**External-dependency-gated (code complete, dark until a credential/hardware step):**
- [ ] **Home Assistant (Phase 5.1)** — `tools/smarthome.py` done + confirm-gated; VPS `ha_url/ha_token=False`.
      Controls nothing until `JARVIS_HA_URL` + `JARVIS_HA_TOKEN` set. **[your hub token]**
- [ ] **Open-speaker AEC full-duplex (Phase 1.2)** — `edge/aec.py` seam done + tested (15/15); the working
      echo canceller is a **proprietary SDK** (krisp_audio/aic_sdk) not present. Install SDK +
      `JARVIS_AEC_FILTER=krisp` → open-speaker barge-in auto-enables. (Owner uses AirPods where barge-in
      already works — this is the general capability.) **[paid SDK license]**
- [ ] **Google OAuth (Calendar + Gmail)** — unconfigured on VPS; blocks real Channels data. **[your creds]**
- [ ] **Giphy key** — unconfigured. **[your key]**
- [ ] **TTS affect prosody** — needs one **live listen-check** once C3 lands. **[1 live check]**

**Parked scaffolds (not runnable):**
- [ ] **MentraOS glasses client** — `glasses/src/index.ts` is an UNFINISHED scaffold with TODO SDK calls;
      no `npm i`, no MentraOS account/console app, transcription stream not wired. Only brain-side device
      routing exists + is tested. To stand up: MentraOS account + `npm i` in `glasses/` + register app +
      finish `index.ts`. Parked per the 3.4 decision (phone/laptop cam is the eye). **[account + build]**

**Deliberately-not-enabled (decision, not a bug):**
- [ ] **WS gateway fast path** — gives no speedup (CLI cold-start 0.06s; the ~25s is ispir working). The
      4.4 circuit breaker routes straight to CLI. Enable only if you want streaming progress events; needs
      the gateway on localhost or TLS (would trade Tailscale remote access). Left `bind=tailnet`.

**Unbuilt (this TODO's core work — Workstream 0 + Part C, listed above):**
- [ ] B1–B5 tool-call reliability · C1–C7 subsystem-to-Strong. None built yet.

**Model-quality finding (objective, your call to act on):**
- [ ] MiniMax-Text-01 (the non-thinking primary chosen for speed/cost) narrates actions / mis-selects
      tools on memory/define/email/calendar/telegram. Workstream 0 mitigates in code; B5 (thinking-tier)
      is the deeper fix if needed. Documented, not silently "fixed."

**Runtime follow-ups (non-blocking):**
- [ ] Owner-face enroll needs the owner seated ("learn my face") — LBP recognizer + tooling done; refs
      local to laptop only (VPS is cameraless).
- [ ] Stale local dev tasks stuck `status=running` ~275h show on the HUD (cap limits flood) — hygiene TODO.
- [ ] 2.2 daily-schedule refresh job (currently refreshes lazily before reasoning — sufficient).
- [ ] Local freellmapi proxy (:3001) for local VLM tests (works on VPS otherwise; groq has no vision model).
