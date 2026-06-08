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

## Wake words (Alex's required set — do not drop any)
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
Alex uses open speakers and wants to talk over Jarvis → requires **acoustic echo cancellation**.
The only AEC in Pipecat is **Krisp** (paid `krisp_audio` SDK + dev account + `.kef` model + API key
from krisp.ai/developers). Wired behind `audio_in_filter` once that key exists. Until then the
`HalfDuplexGate` mutes the mic while Jarvis speaks (no self-hearing, but no barge-in yet).

## Setup
```bash
cp .env.example .env        # then fill in ElevenLabs + Deepgram keys
uv sync --extra edge --extra cloud-voice
```

See `docs/` for the phased roadmap (the approved plan).
