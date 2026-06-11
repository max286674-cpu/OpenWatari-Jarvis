# Jarvis

A 24/7, voice-first, local-first living assistant.

- **Edge** (`src/jarvis/edge`) — a [Pipecat](https://github.com/pipecat-ai/pipecat)
  voice pipeline that runs on the local PC: wake word → VAD → STT → TTS, with
  streaming and barge-in. The "LLM" slot is a thin `BrainBridge` that talks to the brain.
- **Brain** (`src/jarvis/brain`) — Jarvis's **own** agent, running 24/7 on the VPS: his own
  reasoning LLM (freellmapi), his own memory, his own personality, and his own tool-calling
  loop. He reasons and answers as himself first. It also owns the proactive scheduler and
  the Telegram / MCP channels.

**Jarvis and OpenClaw are separate.** Jarvis has his own brain. The **OpenClaw 8-agent fleet**
is an *external team of specialists* Jarvis can **consult** — one tool among many — by messaging
`ispir` through the Gateway (`agent` + `agent.wait`) when a task needs deep domain work. When he
relays a specialist's result, he stays Jarvis and re-voices it in his own persona; he never
becomes the fleet. Pipecat is the voice shell; **Jarvis is the mind; OpenClaw is a resource.**

## Voice stack
- **TTS:** ElevenLabs (streaming) for the chosen Jarvis voice; Piper/Kokoro local fallback.
- **STT:** Deepgram (streaming, accurate) by default; faster-whisper / Moonshine local fallback.
- **Wake words:** see below (local, CPU).

## Wake words (Vazghen's required set — do not drop any)
Jarvis must wake on **any** of these:

| Phrase | Engine status |
|---|---|
| **jarvis** | ✅ live now (openWakeWord `hey_jarvis`; also built-in in Porcupine) |
| **alfred** | ⏳ custom — needs Porcupine `.ppn` or a trained openWakeWord model |
| **robbin** | ⏳ custom |
| **assist** | ⏳ custom |
| **time to work** | ⏳ custom (multi-word) |
| **wake up** | ⏳ custom (multi-word) |
| **six-one-nine** | ⏳ custom (multi-word) |

openWakeWord only ships ~6 pretrained models (only "jarvis" matches). The full custom set is
best done with **Picovoice Porcupine** (local, instant custom keywords, free for personal use) —
wired behind `JARVIS_WAKE_WORD_ENGINE=porcupine` once a Picovoice AccessKey + `.ppn` files exist.
The desired list lives in `JARVIS_WAKE_WORDS` and is enforced here so none are forgotten.

## VAD, turn-taking & barge-in (Phase 1)
**Silero VAD** (CPU, bundled — `edge/vad_bargein.py`) detects speech start/stop and feeds the
whole pipeline. Two duplex modes, picked by `JARVIS_BARGE_IN_ENABLED`:

| Mode | When | Behaviour |
|---|---|---|
| **half** (default) | open laptop **speakers** | `HalfDuplexGate` mutes the mic while Jarvis speaks → no self-hearing, but you can't talk over him |
| **full** | **headphones** (incl. AirPods) or AEC | mic stays open during TTS; `BargeInProcessor` interrupts Jarvis the moment you speak, and the brain cancels its in-flight turn |

Enable barge-in: `JARVIS_BARGE_IN_ENABLED=true` in `.env` — **only with headphones**. On open
speakers the mic re-hears Jarvis and he'd interrupt himself. The alternative for speakers is
**acoustic echo cancellation**: the only AEC in Pipecat is **Krisp** (paid `krisp_audio` SDK + dev
account + `.kef` model + API key from krisp.ai/developers), wired behind `audio_in_filter` once that
key exists. Tune VAD with `JARVIS_VAD_CONFIDENCE` / `JARVIS_VAD_START_SECS` / `JARVIS_VAD_STOP_SECS`.

## Knowledge & channel tools (Phase 3)
Jarvis has his **own** reach before he ever bothers the team — a config-driven tool registry
(`src/jarvis/brain/tools/`). Every tool degrades gracefully: with no key it just says the
capability "isn't configured yet" instead of crashing, so you can light them up one at a time.

| Tool | Does | Needs (in `.env`) |
|---|---|---|
| `search_vault` / `read_vault_note` | search & read your Obsidian vault (read-only; writes are delegated) | `JARVIS_VAULT_PATH` (works now) |
| `web_search` | web search + synthesized answer (Tavily) | `JARVIS_TAVILY_API_KEY` |
| `scrape_url` | open one page as clean text (Firecrawl) | `JARVIS_FIRECRAWL_API_KEY` |
| `browse_web` | real headless Chrome for click/JS tasks (Browserbase) | `..._BROWSERBASE_API_KEY` + `_PROJECT_ID`, `uv sync --extra browse` |
| `check_telegram` | read unread DMs (Telethon user-client) | `..._TELEGRAM_API_ID` + `_API_HASH` + one-time login, `uv sync --extra channels` |
| `send_telegram` | send a message (Bot API; confirmed first) | `JARVIS_TELEGRAM_BOT_TOKEN` |
| `spotify` | now-playing / play / pause / skip / search-and-play | `..._SPOTIFY_CLIENT_ID` + `_SECRET` + `_REFRESH_TOKEN` |

**The fleet is ispir-only.** For deep multi-step work Jarvis hands a brief to **ispir** (the team
lead) and ispir alone — `delegate_to_fleet` has no agent override by design. ispir decides which
specialist handles it and briefs them in depth; Jarvis waits for his reply and re-voices it. He
never addresses a specialist directly. (Live fleet connect is still gated pending a sanctioned
gateway path; the code is ready.)

## Agency — his hands on the machine (Phase 3.5)
Jarvis can *do*, not just talk:

| Tool | Does |
|---|---|
| `file_op` | create/delete files & folders, list (deletes refuse protected/system paths) |
| `process_op` | list / kill / start processes & apps |
| `run_powershell` | run PowerShell; `as_admin` relaunches elevated via a **UAC** prompt |
| `browser` | a **real visible** Chromium he drives: open, click, fill, type, press, read, screenshot, tabs — **logs you in by typing your email + password** when you ask. (`uv sync --extra browse` then `playwright install chromium`) |

The persona rule: he **confirms before anything destructive** (deleting, killing, elevated
PowerShell, submitting a form that sends data/money).

## Reminders & push (Phase 4)
`set_reminder` ("remind me in 10 minutes / at 8:00 / daily 07:30"), `list_reminders`,
`cancel_reminder` — backed by APScheduler + a SQLite jobstore so they survive a restart. When one
fires Jarvis **speaks** it (and pushes to your phone via `send_push`/ntfy if `JARVIS_NTFY_TOPIC` is set).

## Protocols — password-gated routines (Phase 7)
FRIDAY/JARVIS-style privileged programs. He runs one **only** if you give the password:

| Protocol | Password env | Does |
|---|---|---|
| `goodnight` | `JARVIS_PROTOCOL_GOODNIGHT_PASSWORD` | shut Jarvis down |
| `phoenix` | `JARVIS_PROTOCOL_PHOENIX_PASSWORD` | restart Jarvis (kill old → start new) |
| `ragnarok` | `JARVIS_PROTOCOL_RAGNAROK_PASSWORD` | restart the laptop |

Say *"run protocol phoenix"* → Jarvis asks for the password → you give it → it runs. A wrong
password runs nothing. **Change the default passwords in `.env`.** Add your own protocol by
dropping a script in `src/jarvis/protocols/` and registering it in `src/jarvis/brain/protocols.py`.

## Audio output: speakers ↔ headphones (incl. AirPods Pro Max)
Jarvis can play through the laptop speakers or your headphones, switchable by voice.

```bash
uv run python bench/list_audio_devices.py          # see devices + how Jarvis resolves them
uv run python -m jarvis.edge.switch_audio headphones
uv run python -m jarvis.edge.switch_audio speakers
```

**AirPods Pro Max — realistic answer:** yes, for *output*. On Windows they pair as a *generic*
Bluetooth device (no Apple SDK), appearing as two endpoints: "Headphones (… Stereo)" = A2DP,
high-quality playback; "Headset (… Hands-Free)" = HFP, bidirectional but telephone-grade. Jarvis
routes **output** to the A2DP endpoint and keeps the **laptop mic for input** — because using the
AirPods as the mic forces the whole link down to low-quality HFP (you can't have HQ playback + the
AirPods mic at the same time). The `switch_audio` preference is honored when the edge worker
(re)starts; the live in-conversation voice toggle is registered as a brain tool in Phase 2.
Set a fixed default with `JARVIS_AUDIO_OUTPUT_DEVICE` in `.env`.

## Setup
```bash
cp .env.example .env        # then fill in ElevenLabs + Deepgram keys
# Full install (voice + wake word + brain + scheduler). Include every extra you use, because
# `uv sync` PRUNES anything not requested — omitting one drops e.g. openwakeword or pyaudio.
uv sync --extra edge --extra cloud-voice --extra brain --extra local-voice
uv sync --extra browse --extra channels   # optional: local browser (then `playwright install chromium`) + Telegram reading
```

See `docs/` for the phased roadmap (the approved plan).
