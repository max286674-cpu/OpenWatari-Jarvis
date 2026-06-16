# JARVIS — 24/7 Living Voice Agent: Development Plan (from scratch)

> **Now named WATARI** (identity-only rename 2026-06-14; internal package/dir/services stay `jarvis`).

## Backlog after the 2026-06-14 elite-pass (open items, prioritised)

Done this pass: model upgraded to `llama-3.3-70b-versatile` (benchmark-won, ~1.5s first sentence);
streaming voice path (speaks sentence-1 while composing the rest) on both local + WS brains; unified
brain capability (`JARVIS_BRAIN_MODE=remote`, verified streaming over the tailnet); confirmed local
PC-control tools; verified proactive ntfy push; killed the recurring PowerShell popup; fixed the
false-wake + choppy-playback bugs.

Still open (future tasks):
1. **Custom "Watari" wake-word model** — only free way to a literal "Watari" trigger (Porcupine
   denied the user a key). Needs an openWakeWord training run: synthetic Piper voices + negatives
   (~GBs) + a few CPU-hours → a `watari.onnx` dropped into the wake set. Interim trigger = "hey jarvis".
2. **iPhone mic over HTTPS** — the phone literally can't capture mic over plain HTTP. Plan: add
   `tailscale serve` routes (tailnet-only, additive — do NOT disturb the `/inbox` funnel) mapping a
   path → brain HTTP :8766 and `/voice` → WS :8765; rewrite the client to capture mic via
   `getUserMedia`+`MediaRecorder` and POST audio to a new brain `audio` handler that runs Deepgram
   REST STT; build the WS URL as `wss://<tailnet-host>/voice` when served over HTTPS. Needs the
   physical phone to verify.
3. **Edge command channel for REMOTE mode** — PC-control tools work in local mode (brain on laptop);
   when `BRAIN_MODE=remote` they'd hit the VPS. To control the laptop from the unified VPS brain,
   route `process_op`/`run_powershell`/`file_op` back to the edge over a guarded channel.
4. **A "clean up Task Manager" skill** — a curated `process_op` helper that surfaces idle/duplicate/
   heavy processes as safe-to-kill candidates and confirms before killing (today it lists + kills by
   name/pid, which works but leaves the judgement to the model).
5. **Populate memory** — L1 learned facts shows 0; the elaborate 5-layer memory is unproven until it
   actually learns. Exercise enrollment + a few real sessions so recall has substance.
6. **Speed of the unified brain** — VPS first-sentence is ~4s vs ~1.5s local (the VPS is loaded with
   the 30-agent fleet). If remote becomes the default, give the brain its own faster proxy lane.
7. **Mentra OS glasses** — `glasses/` TS scaffold only; hardware-gated, correctly last.

## Context

The previous JARVIS (`D:\JARVIS`, Tauri+SvelteKit+FastAPI) and `C:\openjarvis` are **abandoned legacy** and will not be read or reused. We are building a fresh, voice-first, local-first 24/7 assistant called **Jarvis** that fulfills the full capability list (natural streaming voice, always-listening wake word, proactive scheduling, multi-device, OpenClaw-agent delegation, Obsidian vault, Telegram, MCP servers, speaker biometrics, smart-glasses, latency benchmarks).

**Decisions locked with the user (2026-06-08):**
| Decision | Choice | Consequence |
|---|---|---|
| Brain hosting | **Hybrid: local PC edge + VPS brain** | Voice/audio runs locally (privacy, low mic latency); a VPS service keeps proactive/cron + Telegram + OpenClaw bridge alive 24/7 even when PC is off. |
| STT/TTS | **Local-first, cloud optional** | Default to local engines; keep a swappable cloud adapter behind a flag for quality A/B. |
| Local hardware | **No GPU / integrated only** | Local defaults MUST be CPU-class: Moonshine STT, Piper/Kokoro-ONNX TTS, openWakeWord. Heavy neural TTS (Orpheus/Chatterbox) and large-Whisper are **cloud-only** fallbacks. |
| Voice core | **Pipecat** | Pipeline framework (VAD→STT→LLM→TTS), swappable providers, runs as a local daemon. The LLM stage is a `BrainBridge` to Jarvis's own brain. LiveKit noted as a later option if multi-device concurrency demands it. |
| **Brain identity** | **Jarvis is his own agent** | Jarvis has his **own** reasoning LLM (`llama-3.3-70b-versatile` via freellmapi, with a provider-diverse fallback chain), his own memory, and his own personality. The **OpenClaw fleet is a separate external tool** he consults via ispir — never his mind. He always thinks and speaks as Jarvis. |

**Existing assets we will reuse (big accelerators):**
- **OpenClaw Gateway + 8-agent fleet** on VPS `openclaw@100.107.141.83` — Jarvis's "deep work" backend via `agent` RPC + `agent.wait` + stream events (ispir = router).
- **freellmapi proxy** (`127.0.0.1:3001` on VPS, 96 free OpenAI-compatible models) — Jarvis's direct-answer LLM and reasoning, no per-token cost.
- **Single canonical Obsidian vault** (`~/.openclaw/obsidian-vault` on VPS ↔ `C:\Users\iamva\Documents\Obsidian Vault`) — Jarvis's long-term knowledge via an Obsidian MCP server already in use by the fleet.
- **Telegram bot token** in `pass` (`channels/telegram/business-bot-token`) and chatId `5585548324`.

---

## Build Status (updated 2026-06-12)

Legend: ✅ done & verified end-to-end · 🟡 in progress · ⬜ not started

**Run every check:** `uv run python bench/run_all_tests.py` (config · Phase 1 VAD/barge-in · Phase 3 tools · Phase 4+4b · wake-word perf · Phase 5 biometrics+benchmarks · Phase 6 multi-device · Phase 6 brain-WS-server · Phase 9/9b/9c memory+cache+semantic · Phase 10 proactive · Phase 11 email/calendar/smart-home · Phase 12 utilities · Phase X audit/health/modes · Phase 2 brain). As of 2026-06-12: **17 passed, 0 failed, 1 gated-skip (fleet)** (+ Phase 13 coding/self-improvement). Efficiency analysis + fine-tune targets: `docs/BENCHMARKS.md`. Production switch-on notes: `TODO-NOW.md` §10.

| Phase | Status | Evidence |
|---|---|---|
| 0 — Scaffolding & hello-voice | ✅ | `python -m jarvis.edge.hello_voice`: mic→Deepgram STT→echo→ElevenLabs voice→speaker; cold-start msg; self-hearing fixed via `HalfDuplexGate`; **user-confirmed working** |
| 1 — Local always-listening loop | ✅* | **wake word "hey jarvis"** (openWakeWord, 15.4× realtime CPU, audio local until woken). **Silero VAD** wired (`edge/vad_bargein.py`, CPU). **Barge-in** via `BargeInProcessor` — interrupts mid-reply on user speech, brain cancels its in-flight turn (`InterruptionFrame`). **Smart barge-in identifier** (`edge/device_profile.py`): `JARVIS_BARGE_IN_MODE=auto` detects the live endpoint and auto-enables full-duplex barge-in ONLY on a private device (headphones/AirPods/**Mentra glasses**/**iPhone+earbuds**) and stays half-duplex on open speakers; remote clients declare `JARVIS_DEVICE_HINT`. Pipeline assembles + 25/25 offline checks pass (`bench/test_phase1_vad_bargein.py`). **\*Deferred:** local STT/TTS (Moonshine/Piper) — using cloud Deepgram/ElevenLabs by user's quality choice; + Vazghen's live mic test |
| 2 — Jarvis's own brain + OpenClaw tool | ✅ | **own brain working & tested in-process** (`brain/`: LLMClient w/ failover, context loader, JarvisAgent tool-loop, warmup; wired into edge via `JarvisBrain`). Verified (`bench/test_brain_agent.py`): direct reasoning grounded in memory (570ms warm), `get_time` tool (2.1s), session recall (1.0s), graceful fleet-gating with no sentinel leak. **OpenClaw transport fully mapped** (gateway `/ws` req-frame protocol); live connect needs Vazghen's authorization (shared infra) — `fleet.delegate_to_fleet` ready, gated off. Pending: WS-split to VPS brain service (Phase 4), live fleet auth |
| 3 — Knowledge & channels | ✅* | **Jarvis's own tool layer** (`brain/tools/`, config-driven registry, all degrade gracefully w/o keys). **Obsidian vault** read/search live-verified against the real vault (30 hits for "rabbit farm"; path-traversal blocked; writes stay VPS-authoritative→delegated). **Web**: `web_search` (Tavily) · `scrape_url` (Firecrawl) · `browse_web` (Browserbase+Playwright). **Telegram**: `check_telegram` (Telethon user-client) + `send_telegram` (Bot API). **Spotify**: `spotify` play/pause/next/prev/search. **Fleet locked to ispir-only** — `delegate_to_fleet` has no agent override; ispir is team lead who briefs specialists in depth (persona + memory rules updated). 20/20 offline checks (`bench/test_phase3_tools.py`). **\*Pending:** Vazghen's API keys (Tavily/Firecrawl/Browserbase/Spotify) + one-time Telethon login to light up the cloud tools |
| 3.5 — Agency: system + browser control | ✅ | **`file_op`** (create/delete files+folders, list; protected-path guard) · **`process_op`** (list/kill/start) · **`run_powershell`** (incl. `as_admin` via UAC) · **`browser`** (real visible Chromium: open/click/fill/type/press/read/screenshot/tabs — logs in by typing email+password). All in `brain/tools/`, verified `bench/test_phase4_system_protocols.py` |
| 4 — Proactivity & 24/7 | ✅ (incl. 4b true-24/7) | **Scheduler** (`brain/scheduler.py`, APScheduler + **SQLite** jobstore → reminders survive restart) wired into the edge brain so fired reminders are **spoken** (fired live-verified); **`set_reminder`/`list_reminders`/`cancel_reminder`** (one-shot/at/daily) + **ntfy `send_push`** phone fallback. **Edge boot service** (`scripts/install_edge_service.ps1`) registers a hidden, auto-restarting logon task running `pythonw -m jarvis.edge.assistant` (parse-verified; user ran it — task Ready). **4b TRUE 24/7 (PC-off) — done:** one-shot/`at` reminders are handed to **ntfy server-side scheduled delivery** (`At` header; window 10s–3d) so they reach the phone with the PC off (no double-push: the in-process job then only speaks); **recurring `daily`** reminders register with an always-on **VPS ticker** (`deploy/vps/`, APScheduler+ntfy+HTTP, systemd) via `JARVIS_TICKER_URL` — graceful no-op if unset. 29/29 offline checks (incl. dedicated 4b block). *Deferred (not needed): VPS brain WS-split — brain runs in-process in the edge* |
| 5 — Identity & benchmarks | ✅* | **Speaker biometrics** (`edge/speaker_id.py` + `edge/speaker_gate.py`): SpeechBrain **ECAPA** voiceprint, enrolled via `bench/enroll_voice.py`; `SpeakerGate` drops transcripts that aren't Vazghen's voice (cosine ≥ `JARVIS_SPEAKER_THRESHOLD`). Graceful: no-op until enrolled + `JARVIS_SPEAKER_ID_ENABLED=true`, and degrades to accept-all if the (opt-in `identity` extra) torch backend is absent — never locks him out. **Benchmarks** (`bench/benchmarks.py`→`jarvis.bench_metrics`): **TTFW** (user-stop→first word, measured live by `edge/latency_meter.py`) + **VAQI** 0–100 (latency·responsiveness·smoothness). 23/23 offline checks. **\*Pending:** `uv sync --extra identity` + one-time `enroll_voice.py` to light up the gate (logic fully verified with a stub embedder) |
| 6 — Multi-device | ✅* | **Four devices enabled + routed** (`edge/device_profile.py::resolve_device_route` + `SUPPORTED_DEVICES`): **this host laptop** (speakers, full local pipeline), **iPhone** (thin client→brain WS), **AirPods Pro Max** (private→barge-in ON), **Mentra OS glasses** (`glasses/` MentraOS TS bridge→brain WS, private→barge-in ON). **AirPods auto-route:** connected to *either* phone or laptop ⇒ everything routes to the headphones + barge-in auto-on (laptop via `audio_devices.prefer_private_output`; phone via `headphones_connected` on the `Hello` frame). Protocol carries `device_id` (`shared/protocol.py`: `Hello`+`Utterance`). **Brain WS server built** (`brain/server.py`): hosts ONE shared `JarvisAgent` so phone+glasses+laptop reach the SAME brain+memory; Hello handshake → `lifecycle:thinking` → `tool` fillers → per-sentence `assistant` chunks (incremental TTS) → barge/supersede cancel; optional bearer auth; also serves the phone client over HTTP. **iPhone client built** (`clients/iphone/index.html`): self-contained Safari web app (push-to-talk via Web Speech API + text fallback, `speechSynthesis` playback, "AirPods on this phone" toggle → `headphones_connected`). 22/22 (routing) + 23/23 (server, hermetic) offline checks + a live-socket round-trip; see `docs/multi-device.md`. **\*Pending:** live test needs the physical phone/glasses; Mentra bridge SDK transcription calls still scaffolded (brain link + routing done) |
| **7 — Protocols** | ✅ | password-gated executable routines (FRIDAY/JARVIS style): **`goodnight`** (stop Jarvis) · **`phoenix`** (restart Jarvis) · **`ragnarok`** (restart laptop) · **`backup`** (archive memory) · **`ping`** (phone push test) · **`diagnostics`** (health report) · **`auditpack`** (audit archive) · **`checkpoint`** (non-secret context archive). `run_protocol(name,password)` tool + `brain/protocols.py` (constant-time password check) + detached scripts in `src/jarvis/protocols/`. Jarvis asks for the password first (persona+memory rules). Verified |
| 8 — Memory & automation infra | ✅ | Folded into Phase 9 as memory layers: **Redis** = L4 hot-cache (9b, built, graceful) · **vector** = L5 semantic recall (9c, built, graceful) · **n8n** skipped (overlaps Phase 4). Old `D:\JARVIS` Docker containers are abandoned/disposable |
| **9 — Elite multi-layer memory** | ✅ | **L0–L5 all built.** L1 learned facts + L2 journal (`brain/memory.py`); L3 vault validated always-on at warmup; **L4 hot-cache** (`brain/cache.py`: in-process TTL always-on + optional Redis, fail-open, wired into `web_search`/utilities); **L5 semantic recall** (`brain/semantic.py`: optional embedder, blends cosine into keyword recall, graceful no-op without `sentence-transformers`). Tools `remember`/`recall`/`forget`/`read_journal`. 17+9+8 offline checks (`test_phase9*.py`) |
| **10 — Proactive engine** | ✅ | `brain/proactive.py`: background **tick** + relevance threshold + **interruption budget** + **quiet hours** + repeat-suppression + day-rollover; speaks to listening clients (interrupt) or ntfy push; wired into `brain/server.py` (off unless `JARVIS_PROACTIVE_ENABLED`). Six verbs covered, incl. `confirm_required`/`needs_clarification` policy + a system-prompt clarify/confirm rule. **Modes** (focus/lockdown) mute it on demand. 26/26 checks (`test_phase10_proactive.py`) |
| **11 — Email · Calendar · Smart-home** | ✅ | **Gmail** (`brain/tools/gmail.py`: read/draft, `send` confirm-gated) + **Calendar** (`calendar.py`: list/create) over one Google OAuth app (`brain/google.py`, REST, one-time `bench/google_login.py`) · **Home Assistant** (`smarthome.py`: `ha_state`/`ha_call`, locks confirmed). All self-degrade until credentials set. 15/15 checks. **Needs a one-time user login** (see `TODO-NOW.md` §4–5) |
| **12 — Utilities belt** | ✅ | `brain/tools/utility.py` — weather (Open-Meteo), crypto (CoinGecko), stocks (Yahoo), FX (Frankfurter/ECB), news (HN), wiki, dictionary, unit/currency convert. All no-key, cached, self-degrading; **verified live**. 19/19 checks (`test_phase12_utility.py`) |
| **X — Protocols expansion + audit + self-health** | ✅ | Non-privileged **routines/modes** (`brain/modes.py` + `tools/routines.py`): briefing/focus/lockdown/guest/commute/panic/backup/normal + `self_health`. **Audit log** (`brain/audit.py`: redacted JSONL of every tool call, wired into the agent loop). **Self-health** (`brain/health.py`: vault/cache/ticker, feeds the proactive tick). 23/23 checks (`test_phasex_audit_health_modes.py`) |
| **13 — Coding & self-improvement** | ✅ | `brain/tools/coding.py` — repo-scoped read/write/list + `run_tests`/`lint` + **reversible-only git** (status/diff/log/new_branch/commit/push/revert; NO reset/force-push/rebase by design). Secrets (`.env`, sessions, voiceprint, audit/, backups/) hard-blocked; writes/commits/pushes confirm-gated. **Skills library** (`brain/tools/skills.py` + `skills/*.md`: self-improvement, jarvis-architecture, python, adding-a-tool, git-workflow, debugging, web-and-typescript) read on demand (not prompt-injected). Hardened `.gitignore`; baseline commit made. 30/30 checks (`test_phase13_coding.py`). **GitHub push needs a one-time repo+PAT** (`TODO-NOW.md` §9) |
| **+ Telegram DM reading** | ✅ | `read_chat` (last N of any chat, read or unread, **without** marking seen) + `mark_telegram` (seen/unread, honest that a sent read-receipt can't be reversed). In the brain tool registry |

**Brain-context** (`personality/jarvis.md` + `memory/*.md`): ✅ about-vazghen (Sir · Germany UTC+1 · EN/HY/RU/DE) · projects · openclaw-fleet · environment · **proactive-companion**.

> **Proactive companion is Vazghen's #1 priority** (`memory/proactive-companion.md`): track routine
> (wake/training), calendar + task nudges, anti-distraction interventions, and autonomous
> search/note actions with reported purpose. This concretizes Phase 3 (calendar/Notion/vault MCP +
> activity awareness) and Phase 4 (proactive scheduler + nudge channel + routine memory). Open
> «CONFIRM»: calendar provider, Notion task DB, local activity-monitoring scope.

---

## Target Architecture

Two cooperating processes, one shared protocol:

```
┌──────────────────────── LOCAL PC (Windows 11, CPU-only) ────────────────────────┐
│  jarvis-edge   (Python, Pipecat daemon — runs when PC is on)                     │
│                                                                                  │
│   Mic ─► openWakeWord("Hey Jarvis") ─► Silero VAD ─► STT (Moonshine/faster-      │
│         whisper, local) ─► [BrainBridge processor] ──WebSocket──┐                │
│                                                                 │                │
│   Speaker ◄─ TTS (Piper/Kokoro local | ElevenLabs/Deepgram cloud) ◄─ token      │
│              stream ◄────────────────────────────────────────────┘  (barge-in,  │
│                                                                   SmartTurn, AEC)│
└──────────────────────────────────────────────────────────────────────┬─────────┘
                                                   WebSocket (streaming) │
┌──────────────────────────────── VPS (always-on 24/7) ─────────────────▼─────────┐
│  jarvis-brain  (Python / FastAPI :8770 — systemd service)                        │
│                                                                                  │
│   Orchestrator/Router ─► decide: direct-answer (freellmapi/local LLM)            │
│                                  OR delegate ─► OpenClaw Gateway (agent + wait,   │
│                                                  stream events) ─► ispir/fleet    │
│   Memory & personality & skills  = Markdown files (.md)                          │
│   MCP clients: Obsidian vault · Browserbase (cloud browser) · others             │
│   Channels: Telegram (read unread + send) · ntfy push                            │
│   Proactive scheduler: APScheduler/cron ("remind me every morning")              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Why this split: edge keeps audio + STT/TTS local (privacy, mic latency, honors the local-first decision); brain holds the always-on 24/7 obligations (cron, Telegram, OpenClaw) that must survive the PC being off. The Pipecat "LLM stage" is replaced by a thin `BrainBridge` processor so swapping reasoning backends never touches the audio pipeline.

**Repo layout (new, e.g. `C:\Jarvis\`):**
```
jarvis/
  edge/            # Pipecat daemon, audio I/O, wake word, STT/TTS adapters, TUI
  brain/           # FastAPI orchestrator, OpenClaw bridge, MCP clients, scheduler, channels
  shared/          # WebSocket protocol schema (pydantic), event types
  personality/     # jarvis.md (persona/system prompt), voice-mode files
  memory/          # long-term memory .md (mirrors/links into Obsidian vault)
  skills/          # skill .md files (proactive triggers, how-to knowledge)
  bench/           # TTFW / VAQI latency instrumentation
  glasses/         # (Phase 6) MentraOS TypeScript bridge — only non-Python component
  pyproject.toml   # uv-managed
```

---

## Tech Stack

- **Language:** Python 3.11 (edge + brain). TypeScript **only** for the MentraOS glasses bridge (Phase 6).
- **Env/deps:** `uv` (fast, matches existing tooling). Single `pyproject.toml`.
- **Voice core:** `pipecat-ai` (Apache-2.0). Built-in Silero VAD, SmartTurnDetection, interruption/barge-in.
- **Wake word:** `openwakeword` — ships a pre-trained **"hey jarvis"** model, CPU-friendly (runs many models on a Raspberry Pi).
- **STT (local default):** `useful-moonshine` (Moonshine Base, CPU-fast, edge-grade). Fallback: `faster-whisper` (int8, base/small) for accuracy.
- **TTS (local default):** `piper-tts` (fastest on CPU). Quality tier: `kokoro-onnx` (82M, CPU-runnable). Cloud quality fallback (flagged): ElevenLabs / Deepgram Aura.
- **STT/TTS cloud fallback (flagged):** Deepgram (STT) + ElevenLabs (TTS) adapters — `--provider=cloud`.
- **Direct LLM:** existing **freellmapi** (OpenAI-compatible) as primary; `Ollama`/`llama.cpp` small model for fully-offline mode.
- **Deep work:** OpenClaw Gateway `agent` RPC + `agent.wait` (existing fleet).
- **Speaker biometrics:** `speechbrain` ECAPA-TDNN embeddings (CPU-OK) — enroll your voice, gate commands. (Picovoice Eagle as turnkey alt.)
- **MCP:** `mcp` (official Python SDK) client; servers — Obsidian MCP (community, fleet already uses), `@browserbasehq/mcp-server-browserbase`.
- **Channels:** `telethon` (MTProto user-client — required to *read* unread DMs; Bot API can't) + bot token for sending; `ntfy` for push.
- **Scheduler:** `APScheduler` (in-process) backed by SQLite.
- **TUI (no web UI):** `textual` / `rich` — transcript + state + VAQI readout.
- **Service mgmt:** `systemd` (brain on VPS), Windows Task Scheduler / NSSM (edge), Termux:Boot (Android, Phase 6).

---

## Phased Roadmap

Each phase ships a runnable deliverable + a concrete verification. Phases are ~1–2 weeks each solo.

### Phase 0 — Scaffolding & "hello voice" (Week 1) — ✅ DONE
- Create monorepo + `uv` env; pin `pipecat-ai`. Config via `pydantic-settings` + `.env` with provider flags (`stt_provider`, `tts_provider`, `llm_backend`).
- Minimal Pipecat pipeline, **CLI only**: Mic → STT → echo transcript → TTS → speaker. Start with cloud STT/TTS just to prove the pipe, then swap to local in Phase 1.
- `textual` TUI panel showing live transcript + pipeline state.
- **Repos:** `pipecat-ai/pipecat`, `Textualize/textual`.
- **Verify:** speak a sentence, hear it echoed back; transcript shown in TUI; clean Ctrl-C shutdown.

### Phase 1 — Local always-listening loop, CPU-only (Week 2)
- **Wake word:** openWakeWord "hey jarvis" gating — pipeline only acts on directed speech (ignores ambient/playback).
- **VAD:** Silero (Pipecat built-in). **Turn-taking:** Pipecat SmartTurnDetection. **Barge-in** enabled.
- **Local STT:** Moonshine Base (default) with faster-whisper int8 fallback adapter.
- **Local TTS:** Piper (default) + Kokoro-ONNX (quality) adapters; named "Jarvis" voice.
- **Echo handling:** half-duplex gate + WebRTC AEC so Jarvis never transcribes its own TTS (satisfies "ignore playback / directed-only").
- **Repos:** `dscripka/openWakeWord`, `moonshine-ai/moonshine`, `SYSTRAN/faster-whisper`, `rhasspy/piper`, `thewh1teagle/kokoro-onnx`, `snakers4/silero-vad`.
- **Verify:** fully offline (unplug network). Say "Hey Jarvis, what time is it" → wake → transcribe → stubbed reply → spoken. Confirm ambient TV speech is ignored; confirm barge-in interrupts mid-sentence.

### Phase 2 — Brain + OpenClaw bridge (Weeks 3–4)
- **`shared/` protocol:** pydantic WebSocket message schema mirroring OpenClaw stream events (`stream: assistant | tool | lifecycle`).
- **`jarvis-brain` FastAPI on VPS** (systemd) + **`BrainBridge` Pipecat processor** on edge (replaces the LLM stage): edge sends final transcript, brain streams tokens back for incremental TTS.
- **Jarvis's own agent loop:** his own LLM (`llama-3.3-70b-versatile` primary + ordered fallback chain on rate-limit/error), his own personality (`personality/jarvis.md` as system prompt), his own memory, and his own tool-calling. He reasons and answers **as himself first**.
- **OpenClaw as a tool (separate identity):** `delegate_to_fleet(...)` is just **one tool** in Jarvis's loop — Gateway `agent` RPC + `agent.wait` via **ispir**; relay `stream` events → spoken progress ("On it…"), then Jarvis **re-voices** the result in his own persona. He never becomes the fleet.
- **Memory/personality/skills loaders:** read `.md` files; maintain long-term memory + rolling session context (dialogue awareness) so Jarvis remembers flow across turns.
- **Verify:** "Hey Jarvis, ask the finance agent for BTC price" → brain delegates → ispir/fleet returns cited number → spoken. "What did I just ask you?" → recalls prior turn from session context.

### Phase 3 — Knowledge & channels (Weeks 5–6) — ✅ built (keys pending)
- **Tool registry** (`brain/tools/`): each module exposes `SCHEMAS`+`HANDLERS`; the agent merges
  them with its built-ins. Every handler **degrades gracefully** when unconfigured (returns a
  speakable "isn't configured yet" note) so the full set is always safe to register.
- **Implementation note — direct REST over spawning MCP servers.** Rather than run Node MCP
  servers as subprocesses (brittle on Windows, heavy), each integration is a clean async `httpx`
  call to the same upstream API the MCP server would wrap — functionally identical from Jarvis's
  view (a tool he calls), but more robust + unit-testable offline. The registry can still host a
  real stdio-MCP client later without touching the agent.
- **Obsidian vault** (`tools/vault.py`) → `search_vault` / `read_vault_note` over the LOCAL mirror.
  Path-traversal blocked. **Writes stay VPS-authoritative** → Jarvis asks ispir to write.
- **Web** (`tools/web.py`): `web_search` (**Tavily**), `scrape_url` (**Firecrawl**), `browse_web`
  (**Browserbase** via Playwright-over-CDP). Other search scrapers slot in the same way.
- **Telegram** (`tools/telegram.py`): `check_telegram` (**Telethon** user-client — reads unread
  DMs) + `send_telegram` (**Bot API** — confirm-before-send per persona).
- **Spotify** (`tools/spotify.py`): `spotify(action,query)` — now_playing/play/pause/next/prev/search.
- **Fleet = ispir only.** `delegate_to_fleet` has **no agent override**; ispir is the team lead who
  picks the specialist and briefs them in depth. Enforced in code (schema + signature) and in the
  persona/memory rules.
- **Repos/APIs:** Tavily · Firecrawl · `browserbase` + `microsoft/playwright` · `LonamiWebs/Telethon` · Spotify Web API.
- **Verify:** `bench/test_phase3_tools.py` (20/20 offline). Voice: "search my vault for the
  rabbit-farm charter"; "any unread Telegram?"; "open example.com and tell me the headline";
  "play some jazz on Spotify". (Cloud tools need their keys in `.env`; vault works now.)

### Phase 3.5 — Agency: system + browser control — ✅ built
Jarvis's hands on the machine, so he can *do*, not just talk. All in `brain/tools/`, graceful
when disabled, verified in `bench/test_phase4_system_protocols.py`:
- **`file_op`** — create/delete files & folders, list. Deletes refuse `JARVIS_SYSTEM_PROTECTED_PATHS`
  and drive roots; persona confirms first.
- **`process_op`** — list / kill (by name or pid) / start processes & apps.
- **`run_powershell`** — run PowerShell, `as_admin=true` relaunches elevated via **UAC**.
- **`browser`** (`tools/browser.py`) — a real **visible** persistent Chromium (Playwright): open,
  click (text/selector), fill, type, press, read, screenshot, new_tab, back, close. Logs Vazghen
  in by filling email+password when asked; persistent profile keeps sessions. Needs
  `uv sync --extra browse` + `playwright install chromium`.

### Phase 4 — Proactivity & 24/7 (Week 7) — ✅ engine + desktop always-on + 4b true-24/7

> **Status:** the proactivity *engine* is complete and **fired live-verified** (reminder triggered
> → speak callback + ntfy push), the edge **auto-starts at logon** (`JarvisEdge` task, confirmed
> Ready), and **4b true-24/7 is now done** (see below) — reminders reach the phone even with the PC
> off. While the PC is on, a fired reminder is also spoken live; misfire grace (24h) + coalesce
> still catch anything that was due during a restart.
- **Scheduler** (`brain/scheduler.py`, **APScheduler + SQLite jobstore** → reminders survive a
  restart). Triggers: one-shot delay, absolute `at`, or recurring `daily HH:MM`.
- **Reminder tools**: `set_reminder` / `list_reminders` / `cancel_reminder`. Wired into the edge
  brain (`JarvisBrain.warmup` → `SCHEDULER.start(on_speak=…)`) so a fired reminder is **spoken**.
- **ntfy** (`tools/notify.py`): `send_push` tool + the scheduler's phone-push fallback when voice
  isn't available.
- **Edge boot service** (`scripts/install_edge_service.ps1` / `uninstall_edge_service.ps1`):
  registers a Windows Scheduled Task that launches `.venv\Scripts\pythonw.exe -m jarvis.edge.assistant`
  **at logon, hidden, auto-restart ×3**, working dir = repo (so `.env` loads). Runs as an Interactive
  principal so it reaches the mic/speakers; wake-word gating keeps it idle (no STT/LLM/TTS cost) until
  "Hey Jarvis". One-time activation in the user's own session: `powershell -ExecutionPolicy Bypass -File scripts\install_edge_service.ps1`.
- **Real audio playback** (answering "can Jarvis actually PLAY music?"): YES — YouTube/YouTube Music
  make sound in the autoplay browser, and the **Telegram playlist plays out loud locally** via
  `localplay.py` (download → **ffplay**, windowless) with `stop_music` to halt it. Verified end-to-end
  (played + stopped the latest track).
- **4b · TRUE 24/7 (PC-off) — ✅ done.** Reminders fire/push at the right time even with the laptop
  off, split by kind:
  - **One-shot / `at`** → handed to **ntfy.sh server-side scheduled delivery** (`At` header; ntfy
    holds the message and delivers in its 10s–3d window regardless of PC state). No VPS needed.
    `set_reminder` POSTs the scheduled push at set-time and flips the in-process job to
    `push_phone=False` so the live edge only *speaks* it — no double-push. If ntfy refuses, the
    in-process push is re-enabled as a fallback.
  - **Recurring `daily`** (ntfy can't hold a repeating schedule) → an always-on **VPS ticker**
    (`deploy/vps/jarvis_ticker.py`: APScheduler cron + the same ntfy topic + a tiny HTTP ingest,
    systemd-managed). `set_reminder(daily=…)` best-effort registers the job there over
    `JARVIS_TICKER_URL`; `cancel_reminder` removes it from both. Fully decoupled from the OpenClaw
    fleet/gateway. Deploy with one command — `deploy/vps/install.sh` (see `deploy/vps/README.md`).
    Graceful no-op when `JARVIS_TICKER_URL` is unset (local spoken path still works).
- **Repos:** `agronholm/apscheduler`, `binwiederhier/ntfy`, `ffmpeg` (ffplay).
- **Verify:** `bench/test_phase4_system_protocols.py` (29/29, incl. a dedicated 4b block: ntfy
  window logic, one-shot→ntfy with `at`, push_phone flag, daily→ticker-not-ntfy) + ntfy scheduled
  POST confirmed holding 30s server-side + ticker daemon exercised locally (health/add/list/cancel,
  persisted + cron-scheduled). Voice: "remind me in 2 minutes to stretch" → spoken live + queued to
  phone; "remind me every day at 8 to train" → registered on the always-on host.

### Phase 5 — Identity, polish & benchmarks (Week 8) — ✅ built (enrollment pending)
- **Speaker biometrics** (`edge/speaker_id.py` + `edge/speaker_gate.py`): SpeechBrain **ECAPA-TDNN**
  voiceprint. Enroll once (`bench/enroll_voice.py` records a few clips → averaged, L2-normalised
  embedding → `JARVIS_SPEAKER_PROFILE`). At runtime `SpeakerGate` (after the STT) buffers the
  utterance audio, embeds it, and **drops** the transcript if cosine-sim < `JARVIS_SPEAKER_THRESHOLD`
  — Jarvis stays silent for a stranger / the TV. **Graceful:** a no-op until a profile exists +
  `JARVIS_SPEAKER_ID_ENABLED=true`; if the (opt-in) torch backend is missing it accepts-all rather
  than locking Vazghen out. The gate *decision* is a pure function (`should_accept`) so it's tested
  without torch.
- **Benchmarks** (`jarvis.bench_metrics`, re-exported by `bench/benchmarks.py`): **TTFW** (ms from
  user-stop to first spoken word) measured live by `edge/latency_meter.py` (a pass-through
  processor) into a `TTFW` accumulator (mean/median/p95); **VAQI** = one 0–100 score blending
  latency-vs-target (w .4), responsiveness=1−missed (w .35) and smoothness=1−false-interruptions
  (w .25).
- **Repos:** `speechbrain/speechbrain` (opt-in `identity` extra: speechbrain+torch+torchaudio).
- **Verify:** `bench/test_phase5_identity_bench.py` (23/23) — gate logic, verifier degradation,
  SpeakerGate drop-stranger/pass-Vazghen with a stub embedder, TTFW/VAQI math. Live: `uv sync
  --extra identity` → `enroll_voice.py` → a different speaker is ignored, your voice is served.

### Phase 6 — Multi-device expansion (Weeks 9–12) — ✅ built (live devices pending)
The four devices Vazghen uses are all **enabled and routed from one brain**
(`edge/device_profile.py`, `docs/multi-device.md`):
- **This host laptop** — runs the full local pipeline (`jarvis.edge.assistant`).
- **iPhone** — thin client **built** at `clients/iphone/index.html`: a self-contained Safari web app
  (Add to Home Screen) that auto-connects to the brain WS, push-to-talk via the Web Speech API (text
  box fallback), plays replies with `speechSynthesis`, and has an "AirPods on this phone" toggle that
  sets `headphones_connected`. Served by the brain over HTTP at `http://<laptop-ip>:8766/iphone/`.
- **AirPods Pro Max** — when connected to **either** the phone or the laptop, Jarvis **auto-routes
  everything to the headphones** and turns **barge-in on** (private endpoint). Laptop detects them
  via `audio_devices.prefer_private_output`; the phone declares `headphones_connected=true`.
- **Mentra OS glasses** — `glasses/` MentraOS **TypeScript** bridge (the only non-Python component);
  glasses are a mic/speaker/display, the brain thinks. Declares `device_id="mentra"` → private →
  barge-in on. Brain link + routing implemented; the SDK transcription calls are scaffolded (TODOs).
- **Protocol:** `shared/protocol.py` `Hello`(device_id, headphones_connected) + `Utterance`(device_id).
- **Brain server (built):** `brain/server.py` — `python -m jarvis.brain.server` hosts ONE shared
  `JarvisAgent` over the WebSocket so phone+glasses+laptop reach the **same brain + memory** (turns
  serialised). Streams `lifecycle:thinking` → `tool` fillers → per-sentence `assistant` chunks
  (`final` on last) → `lifecycle:cancelled` on barge/supersede; optional `JARVIS_API_AUTH_TOKEN`
  bearer auth; bind `JARVIS_BRAIN_HOST=0.0.0.0` for the phone. Also serves `clients/` over HTTP.
- **Scaling option:** **LiveKit** rooms if many devices must share one *live* session (still behind
  `BrainBridge`).
- **Verify:** `bench/test_phase6_multidevice.py` (22/22) — device routing, the AirPods auto-route rule
  on laptop+phone, alias resolution, A2DP-over-HFP preference, protocol round-trips — plus
  `bench/test_phase6_brain_server.py` (23/23, hermetic) — Hello handshake, streamed chunks, tool
  fillers, barge cancel, shared-agent session, bearer auth, and a live-socket round-trip. Live
  multi-device test needs the physical phone + glasses.

### Phase 7 — Protocols (FRIDAY/JARVIS-style, password-gated) — ✅ built
The "last phase": named, privileged routines Jarvis runs **only** with Vazghen's password — the
identity gate. Each is a small standalone executable script, launched **detached** so it survives
Jarvis being killed (needed for stop/restart).
- **`goodnight`** → stops Jarvis (terminates the edge process).
- **`phoenix`** → restarts Jarvis (kills the old process, launches a fresh one).
- **`ragnarok`** → restarts the laptop (`shutdown /r` with a 15s grace; `shutdown /a` aborts).
- **Mechanics:** `run_protocol(name, password)` tool → `brain/protocols.py` verifies the password
  with `hmac.compare_digest` (constant-time) → launches `src/jarvis/protocols/<name>.py` detached.
  Passwords come from `JARVIS_PROTOCOL_*_PASSWORD` (**change the defaults**). Jarvis is told (persona
  + `memory/tools.md`) to **ask for the password first** and never run a protocol without it.
- **Add a protocol:** drop a script in `src/jarvis/protocols/` and add an entry to the registry in
  `brain/protocols.py` (name, script, password, spoken line, description).
- **Verify:** `bench/test_phase4_system_protocols.py` — wrong/missing password refuses; correct
  password launches the right script (the launch is stubbed in the test so nothing is killed).

---

### Phase 8 — Memory & automation infrastructure (Redis · Neo4j · n8n) — ⬜ planned
**Origin:** three containers were found running in Docker Desktop (`jarvis-redis`, `jarvis-neo4j`,
`jarvis-n8n`) — **leftovers from the abandoned `D:\JARVIS`** (their volumes mount `D:\JARVIS\...`).
Their *data* is disposable (the 6 631 neo4j `JarvisMemory` nodes are legacy health-check/audit
records — props `all_ok`/`failed_checks`/`path`, not semantic memory; redis holds 98
`jarvis:memory:hot:*` cache keys; n8n holds legacy workflows). **None are required** for the
current build to work — our memory is flat Markdown + APScheduler and that is intentional. But two
of the three *patterns* are real upgrades worth adopting (pointed at `C:\Jarvis`, fresh data):

- **8a · Redis hot-cache — adopt EARLY (best speed ROI, the #1 goal).** A lightweight in-memory
  tier in front of the slow paths: cache freellmapi answers to repeated questions, YTMusic/Tavily
  search results, vault-search hits, and rolling session context across edge restarts. Cuts TTFW on
  cache hits from seconds to ~0 and survives a brain restart. Small, optional, degrades to "no cache"
  if absent. *Deliverable:* `brain/cache.py` (redis-py, `JARVIS_REDIS_URL`, graceful no-op fallback)
  wrapped around `LLMClient.complete` + the web/music tools.
- **8b · Neo4j graph memory — LATER (quality, after flat memory proves limiting).** A knowledge
  graph of entities/notes/decisions linked by typed relations gives **associative recall**
  ("what's related to the rabbit farm?", "who did I discuss X with?") that substring search over
  `.md` can't. Conceptually consistent with the OpenClaw fleet's existing graphify/graph-memory
  direction. Heavier (2 GB heap) and a real architecture change, so it waits until the Markdown
  memory is demonstrably the bottleneck. *Deliverable:* a memory-graph builder + a `graph_recall`
  tool; the `.md` files stay the source of truth, the graph is a derived index.
- **8c · n8n workflow automation — OPTIONAL / likely SKIP.** Visual no-code automation overlaps
  what Phase 4 already does in code (APScheduler + tools + the proactive bridge). Only worth adopting
  if Vazghen wants to wire external SaaS chains visually without touching Python. Otherwise retire the
  container. *No deliverable unless requested.*

**Cleanup either way:** the three legacy containers point at `D:\JARVIS` and should be stopped/removed
(or re-pointed at `C:\Jarvis`) so they don't run against the abandoned project. **Verify:** `8a` — a
repeated question returns from cache measurably faster (logged), and the brain still answers with redis
stopped (graceful fallback).

---

### Phase FINAL — Physical hardware acquisition & integration — ⛔ BLOCKED on buying the devices
**Explicitly the LAST phase, by Vazghen's instruction (2026-06-12):** he does **not** own the
Mentra OS glasses or a Home Assistant device yet, so the two hardware-dependent capabilities are
parked here as a single closing phase to be done *after the hardware is purchased*. Everything in
software is already built and waiting — these items are integration + a live device test, not new
architecture.

- **Mentra OS smart-glasses** — the `glasses/` MentraOS TypeScript bridge + brain WS link + private
  device routing (`device_id="mentra"` → barge-in on) are **already built** (Phase 6). Remaining
  work is hardware-only: pair the physical glasses, finish the SDK transcription/display calls
  (currently scaffolded), and run a live on-device round-trip (speak through the glasses → brain →
  reply shown + spoken). **Blocked until the glasses are bought.**
- **Home Assistant smart-home** — `brain/tools/smarthome.py` (`ha_state`/`ha_call`, locks
  confirm-gated) is **already built** and self-degrades without credentials (Phase 11). Remaining
  work is hardware-only: stand up a Home Assistant instance/hub on a local device, set
  `JARVIS_HOMEASSISTANT_URL` + token, expose the real entities, and verify a live device action
  (e.g. "turn on the desk lamp"). **Blocked until a Home Assistant device/hub is acquired.**

**Acquisition checklist (Vazghen):** (1) buy Mentra OS glasses + a Home-Assistant-capable hub
(e.g. Home Assistant Green/Yellow or a Raspberry Pi running HAOS); (2) hand over the HA URL + a
long-lived access token and the Mentra developer credentials; (3) Jarvis finishes the two
integrations and runs the live device tests above. **Until then this phase stays ⛔ and nothing
else in the roadmap depends on it.**

---

## Expansion (Phases 9–12) — making him *great*, not just working

Approved 2026-06-11. Full design + sequencing in **`docs/EXPANSION-PLAN.md`**. Order:
**9 Memory → 10 Proactivity → 11 Email/Calendar/Smart-home → 12 Utilities.** Phase 8 (Redis/Neo4j)
folds in as memory layers 9b/9c.

### Phase 9 — Elite multi-layer memory — 🟡 L1+L2 built
Six cooperating layers, fastest→deepest; the Markdown layers are the source of truth, the rest are
accelerators. Each degrades gracefully.
- **L0 Working** — current conversation (rolling 12 turns, RAM). *Exists.*
- **L1 Learned/episodic** — one fact per note under `memory/learned/*.md` (frontmatter `created`/`tags`).
  `remember`/`recall`/`forget` tools; keyword+recency scorer (tags ×5); dedup on normalised text. **Built.**
- **L2 Journal** — per-day session summaries under `memory/journal/YYYY-MM-DD.md`; `JarvisAgent.end_session()`
  writes a one-line summary on shutdown; `read_journal` tool for "what did we do yesterday". **Built.**
- **L3 Vault** — the canonical Obsidian knowledge base (read-only, VPS-authoritative). Now **validated as
  always-on** at warmup (`context.validate_vault`); `JARVIS_VAULT_PATH` marked **required**. *Exists, hardened.*
- **L4 Hot-cache (was 8a) — next (9b):** `brain/cache.py` (redis-py, `JARVIS_REDIS_URL`, no-op fallback)
  wrapping `LLMClient.complete` + web/music/vault search. Repeated question → near-zero TTFW; survives a
  brain restart.
- **L5 Semantic/graph (was 8b) — later (9c):** local embedder over L1+L3 for associative recall
  ("what's related to X?"); Neo4j graph only once flat memory is demonstrably the bottleneck.
- **Deliverables (built):** `brain/memory.py` (`MemoryStore`), `brain/tools/memory.py` (4 tools, in registry),
  system-prompt digest injection, vault validation. **Verify:** `bench/test_phase9_memory.py` (17/17 —
  remember/recall/recency/dedup/forget/journal/digest/vault-validate).

### Phase 10 — Proactive engine — ⬜ planned
A background **tick** that gathers signals → asks "is anything worth saying now, and how urgent?" →
acts within an **interruption budget** (+ quiet hours) so he's helpful, not noisy. Each verb you named:
- **remind** — existing scheduler + proactive surfacing.
- **pause** — "hold that thought" / pause TTS / hold a task; `lockdown` protocol for full mute.
- **ask for context** — agent **clarification loop**: ambiguous request → ask back *before* acting.
- **re-ask / confirm** — **confirmation tier** before consequential/outward actions ("send this to X — yes?");
  generalises the existing confirm-before-destructive rule.
- **interrupt** — the tick pushes a TTS frame into the live pipeline mid-idle (the brain already pushes
  spoken reminders this way).
- **speak unprompted** — initiate when a signal's relevance clears a threshold and budget allows; else ntfy
  if the edge is offline.
- **Signals:** time-of-day + routine (L1/`proactive-companion.md`), calendar (P11), unread Telegram/email,
  open L1/L2 threads, opt-in active-window (anti-distraction).
- **Deliverables:** `brain/proactive.py` (tick + relevance scoring + budget + quiet-hours), a
  `ProactiveEvent → speak/ntfy` bridge, agent `clarify()`/`confirm()` helpers, config
  (`JARVIS_PROACTIVE_ENABLED`, interval, quiet hours, daily budget). **Verify:** budget/quiet-hours/
  clarify-confirm logic (no live mic needed).

### Phase 11 — Email · Calendar · Smart-home — ⬜ planned (needs one-time user credentials)
- **Gmail via a Google OAuth app** — `brain/tools/gmail.py`: `read_email` (unread/search/read),
  `draft_email`, `send_email` (**confirm-gated**, outward-facing). One-time OAuth → refresh token in `.env`,
  same pattern as `bench/spotify_login.py`. A real Google Cloud "app", exactly as requested.
- **Google Calendar** — `brain/tools/calendar.py`: `list_events`, `create_event`, `find_free` — the
  backbone of the Phase 10 proactive engine. Same Google app as Gmail.
- **Home Assistant smart-home** (local-first) — `brain/tools/smarthome.py`: `ha_call` (lights/heating/
  locks/scenes), `ha_state` ("is the door locked?"). Local REST/WebSocket + long-lived token
  (`JARVIS_HA_URL`/`JARVIS_HA_TOKEN`); confirm before locks/security. Each self-degrades until configured.

### Phase 12 — Utilities belt — ⬜ planned
One module, many cheap self-degrading tools, prefer **no-key/EU-friendly** providers (reuse fleet keys
where they exist): **weather** (Open-Meteo) · **news** (Guardian/NewsAPI/HN) · **crypto** (CoinGecko) ·
**stocks/ETFs** (Alpha Vantage/Polygon/yfinance) · **economy/FX** (ECB/exchangerate.host) · **translate**
(EN/HY/RU/DE) · unit/currency **convert** · world **clock**/timezones · **dictionary**/synonyms ·
**Wikipedia** lookup. **Deliverable:** `brain/tools/utility.py` (+ `prices.py` if it grows); all registered
together since they degrade gracefully.

### Phase X — Protocols expansion (cross-cutting, lands with P10) — ⬜ planned
Cheap additions on the Phase-7 pattern (a script in `src/jarvis/protocols/` + a registry entry in
`brain/protocols.py`): **`focus`/`deepwork`** (DND + block distracting sites + nudges) · **`briefing`/
`morning`** (weather + calendar + overnight messages + top tasks + news) · **`lockdown`/`privacy`** (mute
mic + pause memory writes) · **`guest`** (public capabilities only, no personal memory/system control) ·
**`panic`/`safe`** (location + message to a trusted contact) · **`commute`** (switch to phone, brief en
route) · **`backup`** (snapshot vault/memory/config). Plus cross-cutting **audit log** of tool actions and
**self-health** (Jarvis notices his own brain/ticker/tunnel/vault down).

---

## Capability → Phase Traceability

| Capability | Phase |
|---|---|
| Natural voice interface (STT/TTS, multi-provider) | 0–1 |
| Streaming low-latency conversation (WS) | 0, 2 |
| Custom wake word "Hey Jarvis" / constantly listening | 1 |
| Ignore ambient/playback, directed-only (AEC, wake gate) | 1 |
| Pure voice, no web UI (CLI/TUI) | 0 |
| Dialogue awareness (long-term memory + session context) | 2 |
| Markdown skill/memory/personality files | 2 |
| Text OpenClaw agents + wait for response; stream events | 2 |
| Connected to Obsidian vault (MCP) | 3 |
| Read & send Telegram | 3 |
| MCP servers incl. Browserbase | 3 |
| Proactive skills (cron, ntfy triggers) | 4 |
| 24/7 always-online; background on desktop | 4 |
| Speaker recognition / voice biometrics | 5 |
| Speed benchmarks (TTFW, VAQI) | 5 |
| Multi-device (Android/Termux, iPhone, glasses); Mentra OS; background on phone | 6 |
| Local PC full suite | 0–5 (native) |
| Password-gated protocols (goodnight/phoenix/ragnarok + focus/briefing/lockdown/guest/panic/commute/backup) | 7, X |
| Persistent memory across sessions (learned facts, journal, recall) | 9 |
| Fast/efficient memory layers (Redis hot-cache, vector/graph recall) | 9b, 9c |
| Proactive companion (initiate, interrupt, pause, clarify, confirm) | 10 |
| Email (Gmail via OAuth app), Calendar | 11 |
| Smart-home (Home Assistant) | 11 |
| Utilities (weather, news, crypto, stocks, FX, translate, convert, wiki) | 12 |
| Audit log + self-health | X |

---

## Repos / SDKs to clone or install (single reference list)

**Core:** `pipecat-ai/pipecat` · `Textualize/textual`
**Ears:** `dscripka/openWakeWord` (hey-jarvis model) · `snakers4/silero-vad` · `moonshine-ai/moonshine` · `SYSTRAN/faster-whisper`
**Voice:** `rhasspy/piper` · `thewh1teagle/kokoro-onnx` · (cloud opt) Deepgram + ElevenLabs adapters
**Brain/LLM:** existing freellmapi proxy · `ollama/ollama` (offline fallback)
**Agents:** existing OpenClaw Gateway (`agent`/`agent.wait`)
**Knowledge/Channels:** `modelcontextprotocol/python-sdk` · Obsidian MCP (`MarkusPfundstein/mcp-obsidian`) · `browserbase/mcp-server-browserbase` · `LonamiWebs/Telethon` · `binwiederhier/ntfy`
**Proactivity:** `agronholm/apscheduler`
**Identity:** `speechbrain/speechbrain` (or Picovoice Eagle)
**Multi-device (later):** MentraOS SDK (TS) · `livekit/agents` (optional)

> Note on the GitHub Copilot list (ASHI, RelayX, Divyashree, Kortana, Aura, Winston, SoulCoreHub): these are small/early personal projects, not maintained frameworks. They're useful as *reference reading* for daemon/VAD/barge-in patterns, but we should **not** base the architecture on them — Pipecat + the curated components above are the production-grade path.

---

## Risks & Mitigations
- **CPU-only latency** (no GPU): keep local defaults lightweight (Moonshine + Piper); expose `--provider=cloud` for quality/latency escape; measure with TTFW from Phase 5 (instrument early in Phase 1 informally).
- **Self-hearing / false wakes:** AEC + half-duplex gate + wake-word + (later) speaker biometrics layered defense.
- **Vault write safety:** vault is VPS-authoritative one-way sync — Jarvis writes via the VPS vault path only, never the local mirror (clobber risk).
- **Telegram reading:** requires MTProto user session (Telethon), not bot API — needs a one-time interactive login + session file kept server-side.
- **Framework lock-in:** all reasoning/transport hidden behind `BrainBridge` + provider adapters, so swapping STT/TTS or adopting LiveKit later is config-level, not rewrite-level.

---

## End-to-end verification (acceptance for the whole system)
1. Cold boot PC → edge auto-starts, connects to VPS brain (Phase 4).
2. "Hey Jarvis" wakes only on your voice (Phase 5), ignores the TV (Phase 1).
3. A direct question answers locally and fast (Phase 0–2); a hard question is delegated to the OpenClaw fleet with spoken progress + cited answer (Phase 2).
4. "Search my vault…", "any unread Telegram?", "open this site…" all work via MCP/channels (Phase 3).
5. A morning reminder fires proactively — spoken if PC on, ntfy if off (Phase 4).
6. Same commands work from phone/glasses against the same brain (Phase 6).
7. TTFW + VAQI logged in the TUI throughout (Phase 5).
