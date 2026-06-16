"""Phase 2 — wake-word assistant with Jarvis's real brain.

    mic -> WakeWordGate("Hey Jarvis") -> HalfDuplexGate -> Deepgram STT
        -> JarvisBrain (own LLM + personality + memory + tools) -> ElevenLabs TTS -> speaker

It responds only after a wake word, ignores ambient speech / its own playback, reasons as
Jarvis using his memory, and can consult the OpenClaw fleet as a tool (once authorized).
Run:

    uv run python -m jarvis.edge.assistant
"""

from __future__ import annotations

print("Watari: loading audio stack (first start can take ~15-30s)…", flush=True)

import asyncio  # noqa: E402

from loguru import logger  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.worker import PipelineWorker  # noqa: E402
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService  # noqa: E402
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams  # noqa: E402
from pipecat.workers.runner import WorkerRunner  # noqa: E402

from jarvis.config import settings  # noqa: E402
from jarvis.edge.audio_devices import resolve_output_index  # noqa: E402
from jarvis.edge.audio_gate import HalfDuplexGate  # noqa: E402
from jarvis.edge.brain_bridge import JarvisBrain  # noqa: E402
from jarvis.edge.device_profile import resolve_barge_in  # noqa: E402
from jarvis.edge.stt import build_stt  # noqa: E402
from jarvis.edge.vad_bargein import BargeInProcessor, build_vad_processor  # noqa: E402
from jarvis.edge.wake_word import WakeWordGate, resolve_openwakeword_models  # noqa: E402


def build_worker(brain: JarvisBrain | None = None) -> PipelineWorker:
    """Assemble the pipeline. Construction loads the wake-word model + Jarvis's brain."""
    if not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
        raise RuntimeError("ElevenLabs api key / voice id not set (.env)")

    # Resolve which speaker/headphone Jarvis plays through (config or saved voice pref).
    out_index, out_label = resolve_output_index(
        settings.audio_output_device, auto_route_headphones=settings.auto_route_headphones
    )
    logger.info(f"audio output -> {out_label} (index {out_index})")

    # Smart barge-in: decide full vs half duplex from the LIVE endpoint (headphones/glasses/
    # phone-earbuds → barge-in auto-ON; open speakers → OFF), not a static flag.
    barge_in, out_kind, why = resolve_barge_in(
        settings.barge_in_mode,
        output_name=out_label,
        device_hint=settings.device_hint,
        legacy_enabled=settings.barge_in_enabled,
    )
    logger.info(f"barge-in: {'ON' if barge_in else 'OFF'} — {why} [{out_kind.value}]")
    params = LocalAudioTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=16000,  # 16k for openWakeWord + Deepgram
    )
    if out_index is not None:
        params.output_device_index = out_index
    transport = LocalAudioTransport(params)
    stt = build_stt()  # Deepgram-multi (EN/FR/DE/RU) or Whisper (all six incl. Armenian)
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model,
        ),
    )

    stages: list = [transport.input()]

    # Silero VAD first, so every later stage sees speech-start/stop frames (used for
    # barge-in now, endpointing later). It runs on raw mic audio regardless of wake state.
    if settings.vad_enabled:
        stages.append(build_vad_processor())

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

    # Duplex follows the smart decision above: full (private endpoint) opens the mic during TTS
    # + enables barge-in; half (shared speakers) mutes the mic while Jarvis speaks.
    if barge_in:
        if not settings.vad_enabled:
            logger.warning("barge-in wanted but vad_enabled=False — falling back to half-duplex")
            stages.append(HalfDuplexGate())
        else:
            logger.info("duplex=full — barge-in ON (mic open during TTS)")
            stages.append(BargeInProcessor())
    else:
        stages.append(HalfDuplexGate())
        logger.info("duplex=half — mic muted while Jarvis speaks (speakers-safe, no barge-in)")

    stages.append(stt)

    # Phase 5 — speaker biometrics: after STT, drop transcripts that aren't Vazghen's voice.
    # No-op (graceful) until a voiceprint is enrolled and JARVIS_SPEAKER_ID_ENABLED=true.
    if settings.speaker_id_enabled:
        from jarvis.edge.speaker_gate import SpeakerGate

        gate = SpeakerGate()
        if gate._verifier.has_profile:
            logger.info("speaker-id: ON — only Vazghen's enrolled voice will be obeyed")
        else:
            logger.warning("speaker-id enabled but no voiceprint — run bench/enroll_voice.py "
                           "(gate is a no-op until enrolled)")
        stages.append(gate)

    # Phase 5 — measure TTFW (user-stop → first spoken word) live; pure pass-through, logged.
    from jarvis.edge.latency_meter import TTFWMeter

    stages += [brain or JarvisBrain(), tts, TTFWMeter(), transport.output()]

    return PipelineWorker(Pipeline(stages))


async def build_brain():
    """Pick the brain: LOCAL in-process agent (default, fastest) or REMOTE thin-client to the 24/7
    VPS brain (one shared Watari + memory). 'auto'/'remote' fall back to local if the VPS is down."""
    mode = (settings.brain_mode or "local").lower()
    if mode in ("remote", "auto"):
        from jarvis.edge.remote_brain import RemoteBrain

        rb = RemoteBrain(headphones_connected=False)
        if await rb.start():
            logger.info(f"brain: REMOTE — unified VPS brain at {settings.brain_ws_url}")
            return rb
        await rb.stop()
        if mode == "remote":
            logger.warning("brain: 'remote' requested but the VPS brain is unreachable — "
                           "running the LOCAL brain for this session")
    brain = JarvisBrain()
    await brain.warmup()  # prime the LLM so the first reply isn't a cold ~3s TTFT
    logger.info("brain: LOCAL — in-process agent")
    return brain


async def main() -> None:
    logger.info(
        f"Watari assistant | wake={settings.wake_words_list} "
        f"vad={settings.vad_enabled} duplex={settings.duplex_mode} "
        f"STT={settings.stt_provider.value} TTS={settings.tts_provider.value}"
    )
    logger.info('Say "Hey Jarvis", then your command. Ambient speech is ignored. Ctrl-C to stop.')
    brain = await build_brain()
    runner = WorkerRunner()
    await runner.add_workers(build_worker(brain))
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("stopped")
