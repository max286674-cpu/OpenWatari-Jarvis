"""De-risk Phase 1: openWakeWord 'hey_jarvis' loads + runs on Windows CPU."""

import time

import numpy as np
import openwakeword
from openwakeword.model import Model

print("downloading openWakeWord models (first run only)…", flush=True)
openwakeword.utils.download_models()

m = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
print("models:", list(m.models.keys()))

# 80ms frames of 16kHz int16 audio (1280 samples) — openWakeWord's expected chunk.
frame = np.zeros(1280, dtype=np.int16)
# warm up
for _ in range(5):
    m.predict(frame)
t0 = time.perf_counter()
N = 50
for _ in range(N):
    pred = m.predict(frame)
per_ms = (time.perf_counter() - t0) / N * 1000
print(f"per-frame inference: {per_ms:.2f} ms  (frame = 80ms of audio)")
print("realtime factor:", round(80 / per_ms, 1), "x faster than realtime")
print("silence score:", round(pred["hey_jarvis"], 4))
realtime_ok = per_ms < 80

# Wake acknowledgement: a detection must emit a spoken ack so you HEAR that Watari woke. Simulate a
# hit (no real audio) and assert the gate pushes an ack TTSSpeakFrame downstream toward the TTS.
import asyncio  # noqa: E402

from pipecat.frames.frames import InputAudioRawFrame, TTSSpeakFrame  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402

from jarvis.config import settings  # noqa: E402
from jarvis.edge.wake_word import WakeWordGate  # noqa: E402


async def _check_wake_ack() -> bool:
    gate = WakeWordGate(models=["hey_jarvis"], threshold=0.6,
                        ack_phrase=settings.wake_ack_phrase, suppress_during_tts=True)
    pushed: list = []

    async def _cap(f, direction=FrameDirection.DOWNSTREAM):
        pushed.append(f)

    gate.push_frame = _cap
    gate._detect = lambda f: "hey_jarvis"   # simulate a wake hit
    await gate.process_frame(
        InputAudioRawFrame(audio=b"\x00\x00" * 320, sample_rate=16000, num_channels=1),
        FrameDirection.DOWNSTREAM)
    acks = [f.text for f in pushed if isinstance(f, TTSSpeakFrame)]
    print("wake-ack emitted on detection:", acks)
    return bool(acks) and acks[0] in settings.wake_ack_phrase.split("|")

ack_ok = asyncio.run(_check_wake_ack()) if settings.wake_ack_phrase.strip() else True


async def _check_speaker_barge_in() -> bool:
    """Saying the wake word OVER TTS on speakers must interrupt playback and open listening."""
    from pipecat.frames.frames import BotStartedSpeakingFrame

    gate = WakeWordGate(models=["hey_jarvis"], threshold=0.6,
                        suppress_during_tts=True, barge_in=True)
    interrupted: list = []

    async def _cap(f, direction=FrameDirection.DOWNSTREAM):
        pass

    async def _int():
        interrupted.append(True)

    gate.push_frame = _cap
    gate.broadcast_interruption = _int
    gate._detect = lambda f, threshold=None: "hey_jarvis"
    await gate.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert gate._bot_speaking
    await gate.process_frame(
        InputAudioRawFrame(audio=b"\x00\x00" * 320, sample_rate=16000, num_channels=1),
        FrameDirection.DOWNSTREAM)
    print("barge-in on wake word over TTS:", bool(interrupted), "| listening after:", gate._awake)
    return bool(interrupted) and gate._awake and not gate._bot_speaking

barge_ok = asyncio.run(_check_speaker_barge_in())


async def _check_no_phantom_refire() -> bool:
    """After a wake + listening window, the stale oww buffer must NOT re-fire the ack (the
    observed every-9.5s phantom 'Sir?' loop). The first frame after resume resets the model."""
    gate = WakeWordGate(models=["hey_jarvis"], threshold=0.6,
                        ack_phrase="Sir?", suppress_during_tts=True)
    pushed: list = []

    async def _cap(f, direction=FrameDirection.DOWNSTREAM):
        pushed.append(f)

    gate.push_frame = _cap
    gate._detect = lambda f, threshold=None: "hey_jarvis"  # stale buffer would keep scoring high
    mic = InputAudioRawFrame(audio=b"\x00\x00" * 320, sample_rate=16000, num_channels=1)

    await gate.process_frame(mic, FrameDirection.DOWNSTREAM)      # real wake -> ack #1
    await gate.process_frame(mic, FrameDirection.DOWNSTREAM)      # awake: forwarded, predict paused
    gate._open_until = 0.0                                        # window expires
    await gate.process_frame(mic, FrameDirection.DOWNSTREAM)      # resume: must RESET, not re-fire
    acks = [f for f in pushed if isinstance(f, TTSSpeakFrame)]
    print("acks after wake + window expiry:", len(acks), "(must be 1)")
    return len(acks) == 1

phantom_ok = asyncio.run(_check_no_phantom_refire())
print("OK — wake word ready" if (realtime_ok and ack_ok and barge_ok and phantom_ok)
      else "WARN — wake word issue")
