"""WakeWordGate — true always-listening, directed-only, multi-wake-word.

Audio is analysed **locally** by openWakeWord and is NOT forwarded to the (cloud) STT
until one of Vazghen's wake words is heard. After a wake, a listening window opens so a
command — and short follow-ups after Jarvis replies — flow through. The window closes on
silence, so ambient speech/media is ignored. Keeps Deepgram engaged only when addressed.

Vazghen's required wake set (see README): jarvis, alfred, robbin, assist, time to work,
wake up, six-one-nine. openWakeWord only ships pretrained models for a few phrases, so only
the resolvable ones load here; the rest are reported as pending (Porcupine path). The engine
is pluggable via ``JARVIS_WAKE_WORD_ENGINE``.

Placement: directly after ``transport.input()`` (before the echo gate and STT).
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger
from pipecat.frames.frames import BotStoppedSpeakingFrame, Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# Desired phrase -> openWakeWord pretrained model name (the only ones available without training).
OPENWAKEWORD_PRETRAINED: dict[str, str] = {
    "jarvis": "hey_jarvis",
    "hey jarvis": "hey_jarvis",
    "alexa": "alexa",
    "hey mycroft": "hey_mycroft",
    "hey rhasspy": "hey_rhasspy",
    "timer": "timer",
    "weather": "weather",
}


def resolve_openwakeword_models(desired: list[str]) -> tuple[list[str], list[str]]:
    """Split desired phrases into (loadable openWakeWord model names, pending phrases)."""
    models: list[str] = []
    pending: list[str] = []
    for phrase in desired:
        key = phrase.strip().lower()
        model = OPENWAKEWORD_PRETRAINED.get(key)
        if model and model not in models:
            models.append(model)
        elif not model:
            pending.append(phrase.strip())
    return models, pending


class WakeWordGate(FrameProcessor):
    def __init__(
        self,
        models: list[str],
        threshold: float = 0.5,
        listen_window_s: float = 8.0,
    ) -> None:
        super().__init__()
        if not models:
            raise ValueError("WakeWordGate needs at least one loadable wake-word model")
        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models()
        self._model = Model(wakeword_models=models, inference_framework="onnx")
        self._names = list(self._model.models.keys())
        self._threshold = threshold
        self._listen_window_s = listen_window_s
        self._open_until = 0.0
        logger.info(f"wake words active: {self._names} (threshold {threshold})")

    @property
    def _awake(self) -> bool:
        return time.monotonic() < self._open_until

    def _wake(self) -> None:
        self._open_until = time.monotonic() + self._listen_window_s

    def _detect(self, frame: InputAudioRawFrame) -> str | None:
        samples = np.frombuffer(frame.audio, dtype=np.int16)
        if frame.num_channels and frame.num_channels > 1:
            samples = samples[:: frame.num_channels]  # first channel
        if frame.sample_rate and frame.sample_rate != 16000:
            import soxr

            samples = soxr.resample(
                samples.astype(np.float32), frame.sample_rate, 16000
            ).astype(np.int16)
        scores = self._model.predict(samples)
        for name, score in scores.items():
            if score >= self._threshold:
                return name
        return None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        # After Jarvis finishes speaking, keep listening briefly for a follow-up.
        if isinstance(frame, BotStoppedSpeakingFrame) and self._awake:
            self._wake()

        if isinstance(frame, InputAudioRawFrame):
            if self._awake:
                await self.push_frame(frame, direction)  # forward command audio to STT
            else:
                hit = self._detect(frame)
                if hit:
                    self._wake()
                    logger.info(f"wake: '{hit}' detected — listening")
                # asleep: swallow audio so the STT never hears ambient speech
            return

        await self.push_frame(frame, direction)
