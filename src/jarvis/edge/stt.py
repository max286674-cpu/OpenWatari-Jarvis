"""STT builder — pick + configure the speech-to-text service for the voice pipeline.

Multilingual by design: Vazghen may speak English, French, German, Armenian, Russian or
Ukrainian. Two engines, a clear trade-off:

* **Deepgram** (default, low-latency cloud): nova-3 ``language='multi'`` code-switches across
  English / French / German / Russian (and more) with great latency. It does **not** support
  Armenian, and Ukrainian isn't in the ``multi`` set.
* **Whisper** (``faster-whisper``, local): auto-detects and transcribes **all six** including
  **Armenian** and **Ukrainian**. Heavier on a no-GPU CPU, but the only configured engine that
  covers everything. Select with ``JARVIS_STT_PROVIDER=whisper``.

Either way the brain always **replies in English** (see ``personality/jarvis.md``); STT only
decides which spoken languages Jarvis can *understand*.
"""

from __future__ import annotations

from loguru import logger

from jarvis.config import STTProvider, settings


def _auto_whisper(model: str):
    """Whisper STT that genuinely AUTO-DETECTS the spoken language.

    Pipecat's ``WhisperSTTService`` forces ``language='en'`` on faster-whisper (it resolves
    ``language=None`` to English so its ``assert_given`` check passes), which mis-transcribes
    Armenian/Russian/French/etc. We override ``run_stt`` to call the model with ``language=None``
    (true auto-detect across all six languages) and report the *detected* language. Task stays the
    default 'transcribe', preserving the spoken language; the brain then always replies in English.
    """
    import asyncio
    from collections.abc import AsyncGenerator

    import numpy as np
    from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
    from pipecat.services.whisper.stt import WhisperSTTService
    from pipecat.utils.time import time_now_iso8601

    class _AutoDetectWhisper(WhisperSTTService):
        async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
            if not self._model:
                yield ErrorFrame("Whisper model not available")
                return
            await self.start_processing_metrics()
            audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            # language=None => faster-whisper detects the spoken language itself (all six).
            segments, info = await asyncio.to_thread(
                self._model.transcribe, audio_float, language=None
            )
            detected = getattr(info, "language", None)
            text = ""
            threshold = self._settings.no_speech_prob
            for seg in segments:
                if threshold is None or seg.no_speech_prob < threshold:
                    text += f"{seg.text} "
            text = text.strip()
            await self.stop_processing_metrics()
            if text:
                await self._handle_transcription(text, True, detected)
                logger.debug(f"Whisper[{detected}]: {text}")
                yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), detected)

    return _AutoDetectWhisper(model=model, language=None)


def build_stt():
    """Construct the configured STT service (raises if a required key is missing)."""
    if settings.stt_provider == STTProvider.whisper:
        logger.info(
            f"STT: Whisper local (multilingual AUTO-DETECT, model={settings.whisper_model}) "
            "— understands EN/FR/DE/HY/RU/UK"
        )
        return _auto_whisper(settings.whisper_model)

    # Deepgram (default).
    if not settings.deepgram_api_key:
        raise RuntimeError("JARVIS_DEEPGRAM_API_KEY is not set (.env)")
    from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions

    opts = LiveOptions(
        model=settings.deepgram_model,
        language=settings.deepgram_language,  # 'multi' = EN/FR/DE/RU code-switch
        smart_format=True,
    )
    logger.info(
        f"STT: Deepgram {settings.deepgram_model} (language={settings.deepgram_language}) "
        "— understands EN/FR/DE/RU; for Armenian/Ukrainian set STT provider to 'whisper'"
    )
    return DeepgramSTTService(api_key=settings.deepgram_api_key, live_options=opts)
