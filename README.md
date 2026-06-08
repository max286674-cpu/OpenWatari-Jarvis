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

## Barge-in (interrupting Jarvis on speakers)
Vazghen uses open speakers and wants to talk over Jarvis → requires **acoustic echo cancellation**.
The only AEC in Pipecat is **Krisp** (paid `krisp_audio` SDK + dev account + `.kef` model + API key
from krisp.ai/developers). Wired behind `audio_in_filter` once that key exists. Until then the
`HalfDuplexGate` mutes the mic while Jarvis speaks (no self-hearing, but no barge-in yet).

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
uv sync --extra edge --extra cloud-voice
```

See `docs/` for the phased roadmap (the approved plan).
