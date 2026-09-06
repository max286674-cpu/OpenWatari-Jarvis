"""TTS builder — pick + configure the text-to-speech voice for the edge pipeline.

Cloud ElevenLabs is the primary voice. Local Piper/Kokoro remain safety fallbacks so the edge
can still speak when a cloud service is unavailable.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from jarvis.config import TTSProvider, settings

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _tts_language() -> str | None:
    """Map the human-readable reply-language setting to an ElevenLabs ISO language code."""
    raw = (settings.reply_language or "").strip().lower()
    if not raw:
        return "ru"
    mapping = {
        "russian": "ru", "русский": "ru", "ru": "ru",
        "english": "en", "английский": "en", "en": "en",
        "german": "de", "немецкий": "de", "de": "de",
        "french": "fr", "французский": "fr", "fr": "fr",
        "ukrainian": "uk", "украинский": "uk", "uk": "uk",
        "armenian": "hy", "армянский": "hy", "hy": "hy",
    }
    return mapping.get(raw, "ru")


def _is_russian_reply() -> bool:
    return _tts_language() == "ru"


def _build_elevenlabs():
    if not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
        raise RuntimeError(
            "TTS provider is 'elevenlabs' but JARVIS_ELEVENLABS_API_KEY / JARVIS_ELEVENLABS_VOICE_ID "
            "are not set. Add them to .env, or switch to a fully-local voice with "
            "JARVIS_TTS_PROVIDER=piper."
        )
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from pipecat.frames.frames import ErrorFrame
    from jarvis.edge import voice_health

    language = _tts_language()
    logger.info(
        f"TTS: ElevenLabs {settings.elevenlabs_model} (cloud, streaming, "
        f"language={language or 'auto'}, voice={settings.elevenlabs_voice_id})"
    )

    class _MonitoredElevenLabs(ElevenLabsTTSService):
        """Record cloud errors so the voice watchdog can fail over to local Piper."""

        async def push_error_frame(self, error: ErrorFrame) -> None:
            voice_health.record_cloud_error(str(getattr(error, "error", "")))
            await super().push_error_frame(error)

    return _MonitoredElevenLabs(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model,
            language=language,
        ),
    )


def _build_piper():
    try:
        from pipecat.services.piper.tts import PiperTTSService
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Piper (local TTS) isn't installed. Run: uv sync --extra local-voice"
        ) from e

    download_dir = _REPO_ROOT / ".piper-voices"
    download_dir.mkdir(exist_ok=True)
    # The old en_US-ryan-high default is unsafe for this Russian-speaking deployment: it can
    # pronounce Russian badly and emit missing-phoneme warnings. Keep an explicitly configured
    # non-English Piper voice only when the owner deliberately chose one; otherwise force native RU.
    voice = settings.piper_voice
    if voice == "en_US-ryan-high" or not voice:
        voice = "ru_RU-ruslan-medium"
    logger.info(f"TTS: Piper LOCAL (voice={voice}) — offline, no key, no cloud")
    return PiperTTSService(
        download_dir=download_dir,
        settings=PiperTTSService.Settings(model=None, voice=voice, language=None),
    )


def _build_kokoro():
    try:
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Kokoro (local TTS) isn't installed. Run: uv sync --extra local-voice"
        ) from e

    logger.info(f"TTS: Kokoro LOCAL (voice={settings.kokoro_voice}) — offline, no key, no cloud")
    return KokoroTTSService(
        settings=KokoroTTSService.Settings(
            model=None, voice=settings.kokoro_voice, language=Language.EN
        ),
    )


_BUILDERS = {
    TTSProvider.elevenlabs: _build_elevenlabs,
    TTSProvider.piper: _build_piper,
    TTSProvider.kokoro: _build_kokoro,
}
_CLOUD = {TTSProvider.elevenlabs}


def build_tts():
    """Construct configured TTS; fall back to local speech if cloud construction fails."""
    prov = settings.tts_provider
    fb = settings.tts_fallback_provider
    if prov in _CLOUD and settings.voice_local_fallback and fb not in _CLOUD:
        from jarvis.edge import voice_health

        if not voice_health.cloud_tts_healthy():
            logger.warning(f"cloud TTS '{prov.value}' unhealthy at startup — using local '{fb.value}'")
            return _BUILDERS[fb]()
        voice_health.mark_cloud_active(True)
    try:
        return _BUILDERS.get(prov, _build_elevenlabs)()
    except Exception as e:  # noqa: BLE001
        if prov in _CLOUD and settings.voice_local_fallback and fb not in _CLOUD:
            logger.warning(f"cloud TTS '{prov.value}' unavailable ({e}); falling back to local '{fb.value}'")
            return _BUILDERS[fb]()
        raise
