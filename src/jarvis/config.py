"""Central configuration for Jarvis (edge + brain)."""

from __future__ import annotations
from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict

class STTProvider(str, Enum):
    deepgram = "deepgram"
    whisper = "whisper"
    moonshine = "moonshine"

class TTSProvider(str, Enum):
    elevenlabs = "elevenlabs"
    piper = "piper"
    kokoro = "kokoro"

class LLMBackend(str, Enum):
    freellmapi = "freellmapi"
    ollama = "ollama"
    openai = "openai"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="JARVIS_")
    assistant_name: str = "Watari"
    user_name: str = ""
    user_address: str = ""
    understood_languages: str = "Russian,English"
    reply_language: str = "Russian"
    persona_file: str = "jarvis.md"
    user_tz: str = "Europe/Minsk"
    stt_provider: STTProvider = STTProvider.whisper
    tts_provider: TTSProvider = TTSProvider.elevenlabs
    voice_local_fallback: bool = True
    tts_fallback_provider: TTSProvider = TTSProvider.piper
    tts_affect_enabled: bool = True
    stt_fallback_provider: STTProvider = STTProvider.whisper
    llm_backend: LLMBackend = LLMBackend.freellmapi
    wake_word_enabled: bool = False
    wake_word_engine: str = "openwakeword"
    wake_words: str = "jarvis"
    wake_word_threshold: float = 0.32
    wake_barge_in_enabled: bool = True
    wake_listen_window_s: float = 8.0
    hot_mic_after_wake: bool = True
    hot_mic_idle_minutes: int = 30
    edge_reflexes_enabled: bool = True
    wake_ack_phrase: str = "Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю."
    listening_pulse: bool = False
    listening_pulse_period_s: float = 2.5
    porcupine_access_key: str | None = None
    vad_enabled: bool = True
    barge_in_enabled: bool = False
    barge_in_mode: str = "auto"
    aec_filter: str = "none"
    device_hint: str | None = None
    vad_confidence: float = 0.50
    vad_start_secs: float = 0.2
    vad_stop_secs: float = 0.45
    vad_min_volume: float = 0.05
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model: str = "eleven_flash_v2_5"
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    deepgram_language: str = "multi"
    deepgram_endpointing_ms: int = 500
    audio_output_device: str | None = None
    audio_input_device_index: int | None = None
    audio_input_device_name: str | None = None
    audio_output_device_index: int | None = None
    audio_out_sample_rate: int = 22050
    auto_route_headphones: bool = True
    auto_route_headset_mic: bool = True
    whisper_model: str = "base"
    whisper_language: str = "ru"
    moonshine_model: str = "moonshine/tiny"
    stt_hotwords: str = ""
    mic_gain: float = 1.0
    piper_voice: str = "ru_RU-ruslan-medium"
    kokoro_voice: str = "am_michael"
    desktop_tools_enabled: bool = True
    computer_max_steps: int = 8
    computer_vision_model: str = "qwen/qwen3-vl-30b-a3b-instruct"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    brain_mode: str = "local"
    brain_ws_url: str = "ws://127.0.0.1:8765/voice"
    brain_host: str = "127.0.0.1"
    brain_port: int = 8765
    client_http_port: int = 8766
    api_auth_token: str | None = None
    self_improve_enabled: bool = True
    self_improve_every_turns: int = 6
    code_self_improve_enabled: bool = False
    code_self_improve_max_steps: int = 8
    telegram_bridge_bot_token: str | None = None
    pc_control_url: str | None = None
    openclaw_delegation_enabled: bool = True
    fleet_authorized: bool = False
    openclaw_gateway_url: str = ""
    openclaw_token: str | None = None
    openclaw_router_agent: str = "ispir"
    openclaw_request_timeout_seconds: int = 30
    openclaw_cli_path: str = "openclaw"
    openclaw_cli_ssh_target: str | None = None
    freellmapi_base_url: str = "http://localhost:3001/v1"
    freellmapi_api_key: str | None = None
    llm_primary_model: str = "minimax:MiniMax-Text-01"
    llm_fallback_models: str = "groq:llama-3.3-70b-versatile,groq:llama-3.1-8b-instant,gemini-3.5-flash"
    vision_models: str = "qwen/qwen3-vl-30b-a3b-instruct,gemini-3.5-flash"
    llm_request_timeout_seconds: int = 20
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    cerebras_api_key: str | None = None
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    llm_first_token_timeout_seconds: float = 4.0
    llm_unhealthy_cooldown_seconds: float = 45.0
    llm_fast_model: str | None = None
    tool_turns_prefer_fallback: bool = True
    llm_thinking_model: str | None = "minimax:MiniMax-M2.5-highspeed"

settings = Settings()
