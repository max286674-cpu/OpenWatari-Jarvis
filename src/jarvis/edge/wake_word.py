"""WakeWordGate — true always-listening, directed-only.

Audio is analysed **locally** by openWakeWord and is NOT forwarded to the (cloud) STT
until "Hey Jarvis" is heard. After a wake, a listening window opens so a command — and
short follow-ups after Jarvis replies — flow through without re-triggering. The window
closes on silence, so ambient speech and media are ignored. This keeps Deepgram (and
privacy/cost) engaged only when Alex is actually talking to Jarvis.

Placement: directly after ``transport.input()`` (before the echo gate and STT).
"""

from __future__ import annotations

import time

import numpy as np
from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class WakeWordGate(FrameProcessor):
    def __init__(
        self,
        model_name: str = "hey_jarvis",
        threshold: float = 0.5,
        listen_window_s: float = 8.0,
    ) -> None:
        super().__init__()
        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models()
        self._model = Model(wakeword_models=[model_name], inference_framework="onnx")
        self._name = model_name
        self._threshold = threshold
        self._listen_window_s = listen_window_s
        self._open_until = 0.0

    @property
    def _awake(self) -> bool:
        return time.monotonic() < self._open_until

    def _wake(self) -> None:
        self._open_until = time.monotonic() + self._listen_window_s

    def _score(self, frame: InputAudioRawFrame) -> float:
        samples = np.frombuffer(frame.audio, dtype=np.int16)
        if frame.num_channels and frame.num_channels > 1:
            samples = samples[:: frame.num_channels]  # take first channel
        if frame.sample_rate and frame.sample_rate != 16000:
            import soxr

            samples = soxr.resample(
                samples.astype(np.float32), frame.sample_rate, 16000
            ).astype(np.int16)
        return float(self._model.predict(samples).get(self._name, 0.0))

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        # After Jarvis finishes speaking, keep listening briefly for a follow-up.
        if isinstance(frame, BotStoppedSpeakingFrame) and self._awake:
            self._wake()

        if isinstance(frame, InputAudioRawFrame):
            if self._awake:
                await self.push_frame(frame, direction)  # forward command audio to STT
            else:
                if self._score(frame) >= self._threshold:
                    self._wake()
                    logger.info(f"wake: '{self._name}' detected — listening")
                # asleep: swallow audio so the STT never hears ambient speech
            return

        await self.push_frame(frame, direction)
