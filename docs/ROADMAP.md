# JARVIS — 24/7 Living Voice Agent: Development Plan (from scratch)

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

## Build Status (updated 2026-06-08)

Legend: ✅ done & verified end-to-end · 🟡 in progress · ⬜ not started

| Phase | Status | Evidence |
|---|---|---|
| 0 — Scaffolding & hello-voice | ✅ | `python -m jarvis.edge.hello_voice`: mic→Deepgram STT→echo→ElevenLabs voice→speaker; cold-start msg; self-hearing fixed via `HalfDuplexGate`; **user-confirmed working** |
| 1 — Local always-listening loop | 🟡 | **wake word "hey jarvis" built + startup-verified** (openWakeWord, 16× realtime on CPU, audio stays local until woken; `jarvis.edge.assistant`) — awaiting Alex's live voice test. VAD/SmartTurn (bundled, CPU) + AEC/barge-in pending the headphones-vs-speakers decision |
| 2 — Jarvis's own brain + OpenClaw tool | ⬜ | own agent loop (llama-3.3-70b + fallbacks) + personality + memory; OpenClaw via ispir as a tool |
| 3 — Knowledge & channels | ⬜ | Obsidian vault MCP · Telegram · Browserbase |
| 4 — Proactivity & 24/7 | ⬜ | scheduler · ntfy · background services |
| 5 — Identity & benchmarks | ⬜ | speaker biometrics · TTFW/VAQI |
| 6 — Multi-device | ⬜ | Android/Termux · iPhone · Mentra glasses |

**Brain-context** (`personality/jarvis.md` + `memory/*.md`): ✅ about-alex (Sir · Germany UTC+1 · EN/HY/RU/DE) · projects · openclaw-fleet · environment · **proactive-companion**.

> **Proactive companion is Alex's #1 priority** (`memory/proactive-companion.md`): track routine
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

### Phase 3 — Knowledge & channels (Weeks 5–6)
- **MCP client framework** (config-driven server registry).
- **Obsidian MCP** → read/write/search the canonical vault (Jarvis leverages all memory/projects). Respect the VPS-authoritative one-way sync (writes go through VPS vault).
- **Telegram:** Telethon user-client to read unread DMs + summarize aloud; send replies by voice command.
- **Browserbase MCP:** cloud browser for navigate/extract/fill-form tasks.
- **Repos:** `modelcontextprotocol/python-sdk`, an Obsidian MCP server (e.g. `MarkusPfundstein/mcp-obsidian`), `browserbase/mcp-server-browserbase`, `LonamiWebs/Telethon`.
- **Verify:** "Hey Jarvis, search my vault for the rabbit-farm charter and read me the summary"; "Any unread Telegram?"; "Open example.com and tell me the headline."

### Phase 4 — Proactivity & true 24/7 (Week 7)
- **Scheduler** (APScheduler+SQLite) in brain: cron-style proactive skills defined in `skills/*.md` ("remind me every morning at 8").
- **ntfy** push gateway for notifications when PC/voice is unavailable.
- **Background services:** brain as `systemd` unit on VPS; edge as Windows Task Scheduler / NSSM service (starts on boot, no terminal window).
- **Proactive bridge:** brain events (new Telegram, cron fire) → if edge online, speak the nudge; else ntfy.
- **Repos:** `agronholm/apscheduler`, `binwiederhier/ntfy`.
- **Verify:** schedule a 2-min-out reminder; confirm it speaks on the PC if on, or pushes via ntfy if off. Reboot PC → edge auto-starts and reconnects to brain.

### Phase 5 — Identity, polish & benchmarks (Week 8)
- **Speaker biometrics:** SpeechBrain ECAPA enrollment ("respond only to your voice"); gate command execution by speaker match.
- **Benchmarks:** `bench/` instruments **TTFW** (user-stop → first audible word) and **VAQI** (interruption rate + missed-response rate + latency → single score); surfaced in TUI.
- **Personality pass:** finalize `personality/jarvis.md`; optional voice-modes reusing the OpenClaw Armenian persona pattern.
- **Repos:** `speechbrain/speechbrain` (or Picovoice Eagle).
- **Verify:** a different speaker is ignored; your voice is served. TTFW measured (<~1.2s local target on CPU); VAQI logged across a 10-utterance battery.

### Phase 6 — Multi-device expansion (Weeks 9–12)
- **Android:** Termux + Termux:Boot edge-lite (stream mic → brain, play TTS), battery-optimization disabled.
- **iPhone:** thin client to brain (Shortcuts/WebRTC) since no Termux equivalent.
- **Mentra glasses:** `glasses/` MentraOS **TypeScript** SDK service — glasses are pure mic/speaker/display bridge; brain still does the thinking.
- **Scaling option:** if many devices must share one *live* session concurrently, introduce **LiveKit** rooms as an alternate transport (agent already abstracted behind `BrainBridge`).
- **Repos:** MentraOS SDK (`Mentra-Community`/AugmentOS), `livekit/agents` (only if adopted).
- **Verify:** issue the same command from phone and glasses, hitting the same brain/session; glasses display shows the reply text.

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
