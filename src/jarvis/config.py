"""Central configuration for Jarvis (edge + brain).

All secrets and provider choices come from environment / a local `.env` file.
Nothing here is hard-coded so the same codebase runs CPU-local-only or cloud-quality
just by flipping provider flags. See `.env.example` for the full surface.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class STTProvider(str, Enum):
    deepgram = "deepgram"      # cloud, streaming, best accuracy (default for "understands me well")
    whisper = "whisper"        # local faster-whisper int8 (offline fallback)
    moonshine = "moonshine"    # local, CPU-fast (lowest-latency offline)


class TTSProvider(str, Enum):
    elevenlabs = "elevenlabs"  # cloud, streaming — the chosen "Jarvis voice" (default)
    piper = "piper"            # local, fastest on CPU (offline fallback)
    kokoro = "kokoro"          # local, higher quality than Piper, still CPU-runnable


class LLMBackend(str, Enum):
    openclaw = "openclaw"      # delegate to the existing 8-agent fleet via Gateway
    freellmapi = "freellmapi"  # direct answer via the free OpenAI-compatible proxy
    ollama = "ollama"          # fully-offline local model


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="JARVIS_"
    )

    # --- Provider selection (the three knobs that define a deployment) -------------------
    stt_provider: STTProvider = STTProvider.deepgram
    tts_provider: TTSProvider = TTSProvider.elevenlabs
    llm_backend: LLMBackend = LLMBackend.openclaw

    # --- Wake word ----------------------------------------------------------------------
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"   # openWakeWord bundled model
    wake_word_threshold: float = 0.5

    # --- ElevenLabs (the Jarvis voice) --------------------------------------------------
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None          # the specific voice you want Jarvis to have
    elevenlabs_model: str = "eleven_flash_v2_5"     # lowest-latency streaming model
    elevenlabs_streaming: bool = True               # WebSocket streaming on by default

    # --- Deepgram (cloud STT for accurate, streaming recognition) -----------------------
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    deepgram_language: str = "en"

    # --- Local engine assets (used when provider == local) ------------------------------
    whisper_model: str = "base"           # faster-whisper size; "small" for more accuracy
    piper_voice: str = "en_US-ryan-high"
    kokoro_voice: str = "am_adam"

    # --- Brain / orchestrator -----------------------------------------------------------
    brain_ws_url: str = "ws://127.0.0.1:8770/voice"   # edge -> brain socket
    brain_host: str = "0.0.0.0"
    brain_port: int = 8770

    # OpenClaw Gateway (existing fleet) — the actual "agent brain"
    openclaw_gateway_url: str = "http://127.0.0.1:8800"
    openclaw_gateway_token: str | None = None
    openclaw_router_agent: str = "ispir"

    # freellmapi proxy (direct-answer LLM, runs on the VPS)
    freellmapi_base_url: str = "http://127.0.0.1:3001/v1"
    freellmapi_api_key: str | None = None
    freellmapi_model: str = "default"

    # --- Latency / behaviour ------------------------------------------------------------
    directed_only: bool = True            # ignore ambient speech & own playback
    aec_enabled: bool = True              # acoustic echo cancellation (don't hear self)
    ttfw_target_ms: int = 1200            # Time-To-First-Word goal, surfaced in the TUI

    @property
    def using_cloud_voice(self) -> bool:
        return (
            self.stt_provider == STTProvider.deepgram
            or self.tts_provider == TTSProvider.elevenlabs
        )


settings = Settings()
