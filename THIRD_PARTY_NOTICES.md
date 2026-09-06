# Third-party notices

OpenWatari itself is released under the **MIT License** (see [`LICENSE`](LICENSE)). It is a *framework*
that orchestrates a number of third-party libraries and cloud services. This file records the
licenses of the **direct** dependencies and the obligations that come with them, so you can
distribute a fork with confidence.

> This list is best-effort and informational, not legal advice. Before a public release, regenerate
> it from your locked environment — e.g. `uv run --with pip-licenses pip-licenses --format=markdown`
> (or `uvx pip-licenses`) — and review anything that isn't a permissive license.

## How to read this

- **Permissive (MIT / BSD / Apache-2.0 / Unlicense):** you may use, modify, and redistribute freely.
- **Weak copyleft (LGPL):** see the dedicated note below.
- Third-party model/audio assets can have terms separate from the code that loads them.

## Direct dependencies

| Package | Role | License |
|---|---|---|
| `pipecat-ai` | real-time voice pipeline (VAD/STT/LLM/TTS) | BSD-2-Clause |
| `pydantic`, `pydantic-settings` | config + schema | MIT |
| `python-dotenv` | `.env` loading | BSD-3-Clause |
| `loguru` | logging | MIT |
| `pyaudio` | local mic/speaker I/O | MIT |
| `textual`, `rich` | terminal UI | MIT |
| `openwakeword` | wake-word detection | Apache-2.0 |
| `kokoro-onnx` | local TTS runtime | MIT |
| `openai` (SDK) | OpenAI-compatible client for the LLM | Apache-2.0 |
| `fastapi` | brain HTTP/WS surface | MIT |
| `uvicorn` | ASGI server | BSD-3-Clause |
| `websockets` | edge↔brain transport | BSD-3-Clause |
| `httpx` | HTTP client | BSD-3-Clause |
| `apscheduler` | proactive scheduler | MIT |
| `sqlalchemy` | SQLite job store | MIT |
| `yt-dlp` | resolve a track for free playback | Unlicense (public domain) |
| `ytmusicapi` | YouTube Music search | MIT |
| `redis` (redis-py) | optional L4 hot-cache | MIT |
| `telethon` | Telegram user client (read/send) | MIT |
| **`py-tgcalls` / `ntgcalls`** | **stream music into a Telegram voice chat** | **LGPL-3.0** |
| `playwright` | headless browser driver | Apache-2.0 |
| `speechbrain` | ECAPA speaker embeddings | Apache-2.0 |
| `torch`, `torchaudio` | tensor backend for speaker-ID | BSD-3-Clause |
| `pygame` | optional playback of external MP3 reaction clips | LGPL-2.1-or-later |
| `numpy`, `scipy` | numerics | BSD-3-Clause |
| `ruff`, `pytest`, `pytest-asyncio` | dev tooling | MIT |

## Priler/Jarvis reaction voice packs

OpenWatari can optionally fetch prerecorded reaction clips from the **current** `Priler/jarvis`
repository at runtime. The clips are deliberately **not vendored into this repository**.

Source: https://github.com/Priler/jarvis

The upstream repository contains three current voice packs: `jarvis-howdy`, `jarvis-og`, and
`jarvis-remaster`. Their `voice.toml` files identify Abraham (Priler) as the author. The current
repository's `LICENSE.txt` declares **Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International (CC BY-NC-SA 4.0)** for the distributed material, while its Rust `Cargo.toml`
separately declares the workspace as GPL-3.0-only. Do **not** assume the audio recordings inherit
the Rust source license.

If you redistribute the downloaded recordings, review the upstream asset terms and retain the
required attribution/license information. The OpenWatari integration only downloads the selected
recordings on demand.

## The one copyleft dependency: `py-tgcalls` (LGPL-3.0)

`py-tgcalls` and its native core `ntgcalls` are **LGPL-3.0**. They are pulled in only by the
optional `channels` extra and used only for streaming audio into a Telegram group voice chat.

## Cloud services (Terms of Service, not open-source licenses)

These are bring-your-own-key services. The framework ships no keys; you accept each provider's Terms
when you sign up. They are not covered by this project's MIT license.

- ElevenLabs (TTS), Deepgram (STT), OpenAI-compatible LLM provider / freellmapi, Tavily, Jina Reader,
  Browserbase, Google, Notion, Home Assistant, Picovoice, GitHub, ntfy.
- Media playback: respect the applicable service Terms of Service.

## Pretrained models

Local engines can download model weights on first use. Model weights can carry licenses distinct from
the code that loads them; check the upstream model card before redistributing any weights.

## Naming & trademark note

This project is **OpenWatari** and the assistant is **Watari**. *Jarvis* is referenced only as the
blueprint/inspiration; the internal Python package keeps the short name `jarvis` for compatibility.
