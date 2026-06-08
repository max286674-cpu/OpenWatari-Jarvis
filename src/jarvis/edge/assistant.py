"""Phase 1 — wake-word assistant (still EchoBrain until Phase 2).

    mic -> WakeWordGate("Hey Jarvis") -> HalfDuplexGate -> Deepgram STT
        -> EchoBrain -> ElevenLabs TTS -> speaker

Now it only responds after "Hey Jarvis" and ignores ambient speech / its own playback.
Run:

    uv run python -m jarvis.edge.assistant
"""

from __future__ import annotations

print("Jarvis: loading audio stack (first start can take ~15-30s)…", flush=True)

import asyncio  # noqa: E402

from loguru import logger  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.worker import PipelineWorker  # noqa: E402
from pipecat.services.deepgram.stt import DeepgramSTTService  # noqa: E402
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService  # noqa: E402
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams  # noqa: E402
from pipecat.workers.runner import WorkerRunner  # noqa: E402

from jarvis.config import settings  # noqa: E402
from jarvis.edge.audio_gate import HalfDuplexGate  # noqa: E402
from jarvis.edge.echo_brain import EchoBrain  # noqa: E402
from jarvis.edge.wake_word import WakeWordGate, resolve_openwakeword_models  # noqa: E402


def build_worker() -> PipelineWorker:
    """Assemble the Phase-1 pipeline. Construction loads the wake-word model."""
    if not settings.deepgram_api_key:
        raise RuntimeError("JARVIS_DEEPGRAM_API_KEY is not set (.env)")
    if not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
        raise RuntimeError("ElevenLabs api key / voice id not set (.env)")

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,  # 16k for openWakeWord + Deepgram
        )
    )
    stt = DeepgramSTTService(api_key=settings.deepgram_api_key)
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model,
        ),
    )

    stages: list = [transport.input()]
    if settings.wake_word_enabled:
        models, pending = resolve_openwakeword_models(settings.wake_words_list)
        if pending:
            logger.warning(
                f"wake words pending custom engine (Porcupine/training): {pending}"
            )
        if models:
            stages.append(
                WakeWordGate(
                    models=models,
                    threshold=settings.wake_word_threshold,
                    listen_window_s=settings.wake_listen_window_s,
                )
            )
        else:
            logger.warning("no loadable wake words — mic ungated (open)")
    if settings.half_duplex:
        stages.append(HalfDuplexGate())
    stages += [stt, EchoBrain(), tts, transport.output()]

    return PipelineWorker(Pipeline(stages))


async def main() -> None:
    logger.info(
        f"Jarvis assistant | wake='{settings.wake_word_model}' "
        f"half_duplex={settings.half_duplex} STT={settings.stt_provider.value} "
        f"TTS={settings.tts_provider.value}"
    )
    logger.info('Say "Hey Jarvis", then your command. Ambient speech is ignored. Ctrl-C to stop.')
    runner = WorkerRunner()
    await runner.add_workers(build_worker())
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("stopped")
