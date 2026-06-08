# Environment & infrastructure (no secrets here)

> Operational context for Jarvis. Secrets live only in `.env` (gitignored).

## Machines
- **Local PC** — Windows 11, **no dedicated GPU** (CPU-only). Runs `jarvis-edge` (voice).
  Primary working dir for this project: `C:\Jarvis`.
- **VPS** — `100.107.141.83` (user `openclaw`). Always-on. Hosts the OpenClaw fleet, the
  freellmapi proxy, and (Phase 2+) `jarvis-brain`.

## Key services & ports
- **freellmapi proxy** — OpenAI-compatible, `http://localhost:3001/v1` (tunnel to VPS).
  99 models. Jarvis's brain primary model: `llama-3.3-70b-versatile` (+ fallback chain).
- **OpenClaw Gateway** — `http://100.107.141.83:3200` (router agent: ispir).
- **jarvis-brain** — FastAPI on `127.0.0.1:8765` (Phase 2), edge↔brain WebSocket at `/voice`.

## Knowledge / files
- **Obsidian vault** — `C:\Users\iamva\Documents\Obsidian Vault` (one-way mirror of the
  VPS vault `~/.openclaw/obsidian-vault`; **VPS is authoritative** — write there, not local).
- **Audit log dir** — vault `40-Logs/`.

## Voice stack (current)
- STT: **Deepgram** nova-3 (cloud, streaming). Offline fallback: faster-whisper / Moonshine.
- TTS: **ElevenLabs** streaming, the chosen Jarvis voice. Offline fallback: Piper / Kokoro.
- Wake word: **openWakeWord** "hey jarvis" (CPU). Echo handling: HalfDuplexGate → AEC (Phase 1).

## Conventions
- Python 3.12, `uv`, src-layout package `jarvis` (`edge/`, `brain/`, `shared/`).
- Config via `pydantic-settings`, env prefix `JARVIS_`. Run edge: `python -m jarvis.edge.hello_voice`.
