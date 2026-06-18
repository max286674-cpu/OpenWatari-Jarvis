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

import random
import time

import numpy as np
from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    TTSSpeakFrame,
)
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
    """Split desired phrases into (loadable openWakeWord models, pending phrases).

    A phrase that is a path to a trained model file (``.onnx``/``.tflite``) — e.g. a custom
    "hey watari" model from ``bench/train_wake_word.py`` — is loaded directly by path. Everything
    else maps to a pretrained model name; unmatched phrases are reported pending.
    """
    import os

    models: list[str] = []
    pending: list[str] = []
    for phrase in desired:
        raw = phrase.strip()
        key = raw.lower()
        if key.endswith((".onnx", ".tflite")):
            if os.path.isfile(raw):
                if raw not in models:
                    models.append(raw)        # custom trained model, loaded by path
            else:
                pending.append(raw)           # configured but not trained yet
            continue
        model = OPENWAKEWORD_PRETRAINED.get(key)
        if model and model not in models:
            models.append(model)
        elif not model:
            pending.append(raw)
    return models, pending


class WakeWordGate(FrameProcessor):
    def __init__(
        self,
        models: list[str],
        threshold: float = 0.5,
        listen_window_s: float = 8.0,
        suppress_during_tts: bool = True,
        ack_phrase: str = "",
    ) -> None:
        super().__init__()
        if not models:
            raise ValueError("WakeWordGate needs at least one loadable wake-word model")
        # Spoken "I heard you" acknowledgement choices (pipe-separated -> random for variety).
        # Spoken only on the FIRST wake word of the session, then never again (self._acked).
        self._ack_choices = [p.strip() for p in (ack_phrase or "").split("|") if p.strip()]
        self._acked = False
        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models()
        self._model = Model(wakeword_models=models, inference_framework="onnx")
        self._names = list(self._model.models.keys())
        self._threshold = threshold
        self._listen_window_s = listen_window_s
        self._open_until = 0.0
        self._bot_speaking = False
        self._suppress_during_tts = suppress_during_tts
        self._resume_after_tts = False
        logger.info(f"wake words active: {self._names} (threshold {threshold})")

    @property
    def _awake(self) -> bool:
        return time.monotonic() < self._open_until

    @property
    def is_idle(self) -> bool:
        """True when waiting for a wake word (not in a listening window, not speaking) — the only
        time the soft 'listening' pulse should sound. Drives edge/listening_pulse.py."""
        return not self._awake and not self._bot_speaking

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

        # Track playback so we can spare the CPU while Watari speaks (see below).
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            if self._suppress_during_tts and self._awake:
                self._resume_after_tts = True
                self._open_until = 0.0
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            # After Watari finishes speaking, keep listening briefly for a follow-up.
            if self._awake or self._resume_after_tts:
                self._wake()
            self._resume_after_tts = False

        if isinstance(frame, InputAudioRawFrame):
            if self._bot_speaking and self._suppress_during_tts:
                # Open speakers path: never run wake inference or forward mic audio while Watari is
                # speaking. His own TTS can otherwise re-trigger wake/listening and leak into STT.
                pass
            elif self._awake:
                await self.push_frame(frame, direction)  # forward command audio to STT
            elif self._bot_speaking:
                # Asleep AND Watari is talking: skip wake inference entirely. Running an ONNX
                # predict on every 20ms frame here starves the audio-output thread and makes
                # playback stutter. We also never want to wake on our own TTS, so just swallow.
                pass
            else:
                hit = self._detect(frame)
                if hit:
                    self._wake()
                    logger.info(f"wake: '{hit}' detected — listening")
                    if self._ack_choices and not self._acked:
                        # Speak a short acknowledgement ONCE (the first wake word of the session) so
                        # Vazghen hears that the wake word landed and Watari is now listening. Later
                        # wakes stay silent so it doesn't preface every command.
                        self._acked = True
                        ack = random.choice(self._ack_choices)
                        await self.push_frame(TTSSpeakFrame(ack), FrameDirection.DOWNSTREAM)
                # asleep: swallow audio so the STT never hears ambient speech
            return

        await self.push_frame(frame, direction)
