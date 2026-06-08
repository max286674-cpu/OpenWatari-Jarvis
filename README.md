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
- **Wake word:** openWakeWord "hey jarvis" (CPU).

## Setup
```bash
cp .env.example .env        # then fill in ElevenLabs + Deepgram keys
uv sync --extra edge --extra cloud-voice
```

See `docs/` for the phased roadmap (the approved plan).
