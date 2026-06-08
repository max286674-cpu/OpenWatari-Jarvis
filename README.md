# Jarvis

A 24/7, voice-first, local-first living assistant.

- **Edge** (`src/jarvis/edge`) — a [Pipecat](https://github.com/pipecat-ai/pipecat)
  voice pipeline that runs on the local PC: wake word → VAD → STT → TTS, with
  streaming and barge-in. The "LLM" slot is a thin `BrainBridge` that talks to the brain.
- **Brain** (`src/jarvis/brain`) — a FastAPI orchestrator that runs 24/7 on the VPS.
  It answers simple things directly (freellmapi) and delegates real work to the existing
  **OpenClaw 8-agent fleet** (Gateway `agent` + `agent.wait`). It also owns the proactive
  scheduler and the Telegram / MCP channels.

The brain is **not** a new agent framework — Jarvis's "agent brain" *is* the OpenClaw fleet,
reached over a WebSocket. Pipecat is the voice shell; OpenClaw is the mind.

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
