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
    """The model that powers Jarvis's OWN brain / reasoning.

    OpenClaw is deliberately NOT in this enum: it is an external team Jarvis can
    consult, not the engine of his mind. Jarvis always thinks and speaks as himself.
    """

    freellmapi = "freellmapi"  # default — free OpenAI-compatible proxy (on the VPS)
    ollama = "ollama"          # fully-offline local model
    openai = "openai"          # any OpenAI-compatible endpoint


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="JARVIS_"
    )

    # --- Provider selection (the three knobs that define a deployment) -------------------
    stt_provider: STTProvider = STTProvider.deepgram
    tts_provider: TTSProvider = TTSProvider.elevenlabs
    llm_backend: LLMBackend = LLMBackend.freellmapi   # Jarvis's OWN reasoning model

    # --- Wake word ----------------------------------------------------------------------
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"   # openWakeWord bundled model
    wake_word_threshold: float = 0.5
    wake_listen_window_s: float = 8.0     # how long the mic stays open after a wake/reply
    half_duplex: bool = True              # mute mic while Jarvis speaks (no self-hearing);
    #                                       set false only with headphones to allow barge-in

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
    brain_ws_url: str = "ws://127.0.0.1:8765/voice"   # edge -> brain socket
    brain_host: str = "127.0.0.1"
    brain_port: int = 8765
    api_auth_token: str | None = None                 # empty = loopback-only, no auth

    # OpenClaw Gateway (existing fleet) — an EXTERNAL team Jarvis can DELEGATE to, by
    # messaging ispir through the gateway. It is ONE of Jarvis's tools, not his brain.
    openclaw_delegation_enabled: bool = True
    openclaw_gateway_url: str = "http://100.107.141.83:3200"
    openclaw_token: str | None = None
    openclaw_remote_token: str | None = None
    openclaw_gateway_password: str | None = None
    openclaw_router_agent: str = "ispir"
    openclaw_request_timeout_seconds: int = 30

    # freellmapi proxy — Jarvis's OWN reasoning LLM (runs on the VPS, tunneled to localhost).
    freellmapi_base_url: str = "http://localhost:3001/v1"
    freellmapi_api_key: str | None = None
    # Primary + ordered fallbacks (rate-limit/error -> next model). See bench/llm_bench.py.
    llm_primary_model: str = "llama-3.3-70b-versatile"
    llm_fallback_models: str = "llama-3.1-8b-instant,groq/compound,mistral-small-latest,openai/gpt-oss-20b:free"
    llm_request_timeout_seconds: int = 60

    # --- Channels & knowledge -----------------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_allowed_users: str | None = None
    vault_path: str | None = None
    audit_log_dir: str | None = None

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

    @property
    def llm_chain(self) -> list[str]:
        """Primary model first, then ordered fallbacks (deduped, blanks dropped)."""
        chain = [self.llm_primary_model] + [
            m.strip() for m in self.llm_fallback_models.split(",") if m.strip()
        ]
        seen: set[str] = set()
        return [m for m in chain if not (m in seen or seen.add(m))]


settings = Settings()
