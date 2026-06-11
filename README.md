# Jarvis — a 24/7, voice-first, local-first living assistant

Jarvis is a personal AI companion you **talk to**. He listens for a wake word, answers in a natural
streaming voice, remembers across sessions, acts on your machine and your accounts, reaches you
proactively when it matters, and can even **improve his own code** — safely and reversibly.

He is built from scratch in Python, runs on a no-GPU Windows laptop, and is designed to be *on all
the time*: his brain can run as a service on an always-on host while the voice front-end runs
wherever you are (laptop, phone, smart-glasses).

> **Jarvis is his own agent.** He has his own reasoning model, his own memory, and his own
> personality. The separate OpenClaw fleet is an *external team of specialists* he can **consult**
> as one tool among many — he never becomes it. Pipecat is the voice shell; **Jarvis is the mind.**

---

## Table of contents
- [What he can do](#what-he-can-do)
- [Architecture](#architecture)
- [The build, phase by phase](#the-build-phase-by-phase)
- [Memory — six layers](#memory--six-layers)
- [The tool belt](#the-tool-belt)
- [Proactive companion](#proactive-companion)
- [Self-improvement](#self-improvement-phase-13)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Testing & benchmarks](#testing--benchmarks)
- [Deployment](#deployment)
- [Security](#security)
- [Project layout](#project-layout)

---

## What he can do

- **Natural voice.** Wake on "Jarvis" (and a configurable set), understand you across English /
  French / German / Russian / Armenian / Ukrainian, and reply in a streaming ElevenLabs voice with
  barge-in (you can talk over him on headphones).
- **Think for himself.** His own LLM (via a free OpenAI-compatible proxy) with a model fallback
  chain, his own personality, and a tool-calling loop — answering directly and fast.
- **Remember.** A six-layer memory: the live conversation, durable learned facts, a daily journal,
  your Obsidian vault, a hot-cache, and optional semantic recall.
- **Act.** Files, processes, PowerShell, a real visible browser, music, reminders & phone push,
  Telegram (read *and* send), Gmail, Google Calendar, Notion, Home Assistant smart-home.
- **Look things up.** Weather, crypto, stocks, FX, news, Wikipedia, dictionary, unit/currency
  conversion — mostly key-free.
- **Reach you first.** A proactive engine that surfaces reminders, calendar events, and alerts
  within an interruption budget and quiet hours — speaking if you're listening, pushing if you're not.
- **Improve himself.** Read and edit his own source, run his own test suite, and make **reversible**
  git commits — with hard guardrails so nothing destructive is possible.

Everything **degrades gracefully**: a capability with no credentials simply says "that isn't
configured yet" instead of crashing, so you can light up integrations one at a time.

---

## Architecture

Two cooperating processes over one streaming WebSocket protocol:

```
┌──────────────── LOCAL PC / phone / glasses (the "edge") ───────────────┐
│  Mic → wake word (openWakeWord) → VAD (Silero) → STT (Deepgram/Whisper) │
│      → [BrainBridge] ──WebSocket──┐                                     │
│  Speaker ← TTS (ElevenLabs/Piper) ←┘  (barge-in, smart turn-taking)     │
└────────────────────────────────────────────┬───────────────────────────┘
                          streaming StreamEvents │
┌─────────────────────── always-on host (the "brain") ───────▼───────────┐
│  JarvisAgent: own LLM (+fallback chain) · tool-calling loop · memory     │
│  Tools: vault · web · telegram · gmail · calendar · notion · smart-home  │
│         · utilities · system · browser · reminders · coding/git · …      │
│  Memory L0–L5 · proactive tick · audit log · self-health · protocols     │
│  Optionally consults the external OpenClaw fleet (via ispir) as a tool   │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Edge** (`src/jarvis/edge/`) keeps audio + STT/TTS **local** (privacy, low mic latency).
- **Brain** (`src/jarvis/brain/`) holds the 24/7 obligations (reasoning, memory, scheduler,
  channels) and can run in-process or as a shared WebSocket server (`brain/server.py`) so a laptop,
  the iPhone web client (`clients/iphone/`), and the Mentra glasses all share **one** brain + memory.

---

## The build, phase by phase

| Phase | What | Status |
|---|---|---|
| 0 | Scaffolding & hello-voice (mic→STT→TTS) | ✅ |
| 1 | Local always-listening loop: wake word, VAD, barge-in | ✅ |
| 2 | Jarvis's own brain (LLM + personality + memory + tools) | ✅ |
| 3 | Knowledge & channels: vault, web, Telegram, browser | ✅ |
| 4 | Proactivity & true 24/7: scheduler, ntfy push, VPS ticker | ✅ |
| 5 | Speaker biometrics + TTFW/VAQI benchmarks | ✅ |
| 6 | Multi-device: brain WS server + iPhone client + glasses bridge | ✅ |
| 7 | Password-gated protocols (goodnight/phoenix/ragnarok) | ✅ |
| 9 | **Elite memory** — L1 learned facts, L2 journal, L3 vault, L4 cache, L5 semantic | ✅ |
| 10 | **Proactive engine** — budget, quiet hours, clarify/confirm, modes | ✅ |
| 11 | **Email · Calendar · Notion · Smart-home** | ✅ |
| 12 | **Utilities belt** — weather, crypto, stocks, FX, news, wiki, convert | ✅ |
| X | Audit log · self-health · routines/modes (focus/lockdown/briefing/…) | ✅ |
| 13 | **Coding & self-improvement** — repo-scoped edits + reversible git + skills | ✅ |

The full plan and per-phase detail live in [`docs/ROADMAP.md`](docs/ROADMAP.md);
the expansion design in [`docs/EXPANSION-PLAN.md`](docs/EXPANSION-PLAN.md);
efficiency measurements + fine-tune targets in [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md).

---

## Memory — six layers

| Layer | What | Where |
|---|---|---|
| **L0 Working** | the live conversation (rolling turns) | RAM |
| **L1 Learned** | durable facts he saves (`remember`/`recall`/`forget`) | `memory/learned/*.md` |
| **L2 Journal** | a one-line daily summary for continuity | `memory/journal/*.md` |
| **L3 Vault** | your Obsidian knowledge base (read-only, validated always-on) | `JARVIS_VAULT_PATH` |
| **L4 Hot-cache** | front the slow paths (search, utilities) | in-process TTL + optional Redis |
| **L5 Semantic** | recall by *meaning*, not just keywords | optional local embedder |

L4/L5 are graceful accelerators: no Redis → in-process cache; no embedder → keyword recall. The
Markdown layers are always the source of truth.

---

## The tool belt

All tools live in `src/jarvis/brain/tools/` and self-degrade when unconfigured. Highlights:

- **Knowledge** — `search_vault`, `read_vault_note`, `web_search` (Tavily), `scrape_url`
  (Firecrawl), `browse_web` (Browserbase).
- **Memory** — `remember`, `recall`, `forget`, `read_journal`.
- **Channels** — `check_telegram`, **`read_chat`** (read the last messages of any chat *without*
  marking them seen), **`mark_telegram`**, `send_telegram` (text/GIF/file), `read_email` /
  `draft_email` / `send_email` (Gmail), `notion_search` / `read` / `append` / `comment` / `create`.
- **Calendar & home** — `list_events`, `create_event`, `ha_state`, `ha_call` (Home Assistant).
- **Utilities** — `weather`, `crypto_price`, `stock_price`, `fx_rate`, `news_brief`, `wiki_lookup`,
  `define_word`, `convert`.
- **Media** — `play_music` (YouTube Music, free), `telegram_music`, `spotify`, `stop_music`.
- **The machine** — `file_op`, `process_op`, `run_powershell`, `browser` (a real visible Chromium).
- **Proactive** — `set_reminder`, `list_reminders`, `cancel_reminder`, `send_push`.
- **Routines & health** — `routine` (briefing/focus/lockdown/guest/commute/panic/backup),
  `self_health`.
- **Self-improvement** — `read_source`, `write_source`, `run_tests`, `lint`, `git_status/diff/log`,
  `git_new_branch/commit/push/revert`, `list_skills`, `read_skill`.
- **The team** — `delegate_to_fleet` (ispir-only; gated by default).

A spoken filler is shown for slow tools so a turn is never dead air, and **every tool call is
written to a redacted audit log** (`audit/*.jsonl`).

---

## Proactive companion

A background tick weighs signals (routine, calendar, unread, open threads, self-health) and decides
whether to say something **unprompted** — within an **interruption budget** and **quiet hours**, so
he's helpful, never noisy. He can:

- **remind**, **pause** (hold a thought / lockdown), **ask for context** (clarify before guessing),
  **re-ask / confirm** (before anything outward-facing), **interrupt**, and **speak on his own**.
- Speak to a listening device, or fall back to an ntfy phone push when you're away.
- Be muted on demand: *"focus mode for an hour"*, *"lockdown"*, *"normal"*, *"give me my briefing"*.

It's **on by default** for a 24/7 deployment (toggle `JARVIS_PROACTIVE_ENABLED`).

---

## Self-improvement (Phase 13)

Jarvis can improve his own codebase, with a hard safety rail: **every change is reversible and
verified.**

- **Repo-scoped, secret-blocked file I/O** — he can read/edit project files but never `.env`,
  session files, `voiceprint.json`, the audit log, or anything outside the repo.
- **Verify before trusting** — `run_tests` runs the full suite; he's told to only commit green code.
- **Reversible-only git** — there is *no* reset, force-push, rebase, or branch-delete tool. A revert
  is always a new commit, so history can't be rewritten or lost.
- **Confirm-gated** — writes, commits, and pushes are read back to you for a yes first.
- **Skill playbooks** (`skills/*.md`) — self-improvement loop, a map of his own architecture, Python
  conventions, how to add a tool, git discipline, debugging — read on demand, not bloating the prompt.

Ask: *"read your self-improvement skill, then make recall faster."* He branches, edits, tests, reads
the change back, waits for your yes, commits — and reverts cleanly if anything regresses.

---

## Quick start

Requires **Python 3.11** and [`uv`](https://github.com/astral-sh/uv).

```bash
cp .env.example .env        # then fill in at least ElevenLabs + Deepgram + JARVIS_VAULT_PATH
# uv sync PRUNES extras you don't list — install the FULL set you intend to use in one go:
uv sync --extra edge --extra cloud-voice --extra local-voice --extra brain --extra channels --extra browse --extra identity --extra dev

# verify everything (one command):
uv run python bench/run_all_tests.py        # → 18 passed, 0 failed, 1 gated-skip

# talk to him:
uv run python -m jarvis.edge.assistant      # local voice loop
# or run the shared brain (for phone/glasses):
uv run python -m jarvis.brain.server
```

`TODO-NOW.md` is the **deployment checklist**: every one-time login/credential, in depth, in order.
Complete it + a green test run = ready to deploy.

---

## Configuration

Everything is driven by environment variables (prefix `JARVIS_`) read from `.env`. See
[`.env.example`](.env.example) — every knob is documented inline. Nothing is hard-coded; the same
codebase runs CPU-local-only or cloud-quality just by flipping provider flags. **Never commit
`.env`** (it's gitignored).

---

## Testing & benchmarks

- **`uv run python bench/run_all_tests.py`** — the single gate. Each phase has a hermetic
  `bench/test_phase*.py` (offline, no real network/keys) that prints `=== N/N checks passed ===`.
  Network/fleet tests report SKIP (not FAIL) when their backend is unreachable, so an offline run
  still passes.
- **`uv run python bench/efficiency_report.py`** — measures the hot paths (memory recall, cache,
  brain TTFT, full-turn latency, prompt size) against efficient-operation targets and flags what to
  fine-tune. See [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md).

---

## Deployment

1. Work through `TODO-NOW.md` (voice enrollment, VPS ticker, Google/Notion/Home-Assistant logins,
   GitHub repo, optional Redis/embedder, proactive switch-on).
2. `uv run python bench/run_all_tests.py` → all green.
3. Run the brain as a service on an always-on host and the edge on your laptop (helper scripts in
   `scripts/`). The VPS ticker (`deploy/vps/`) delivers recurring reminders even with the PC off.

---

## Security

Jarvis is powerful — he runs PowerShell, drives a browser, sends messages, and edits his own code.
The safety model (secret handling, confirm tiers, protocol passwords, self-improvement guardrails,
fleet gating, audit log, what's kept out of git) is documented in **[`SECURITY.md`](SECURITY.md)**.
Read it before deploying.

---

## Project layout

```
src/jarvis/
  edge/        # voice pipeline: wake word, VAD, STT/TTS, device routing, barge-in
  brain/       # the agent: LLM, memory, cache, semantic, proactive, audit, health, protocols
    tools/     # the tool belt (one module per capability; SCHEMAS + HANDLERS)
  shared/      # the edge↔brain WebSocket protocol
  protocols/   # password-gated routine scripts
personality/   # jarvis.md — who he is (system-prompt persona)
memory/        # what he knows (Markdown): about-vazghen, projects, tools, learned/, journal/
skills/        # on-demand playbooks (self-improvement, architecture, python, …)
clients/iphone # the phone web client
glasses/       # Mentra OS bridge (TypeScript)
deploy/vps/    # the always-on recurring-reminder ticker
bench/         # the test suite + benchmarks + one-time login helpers
docs/          # ROADMAP, EXPANSION-PLAN, BENCHMARKS, multi-device
TODO-NOW.md    # the deployment checklist (everything only you can do)
```

---

*Built for Vazghen. Jarvis thinks and speaks as himself; the OpenClaw fleet is a resource he
consults, never his mind.*
