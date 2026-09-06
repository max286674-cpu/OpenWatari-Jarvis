"""WakeWordGate — true always-listening, directed-only, multi-wake-word.

Audio is analysed locally by openWakeWord and is NOT forwarded to STT until one of the owner's
wake words is heard. Current Priler/Jarvis prerecorded reaction clips can optionally be used for
the exact wake acknowledgement; arbitrary LLM replies continue through the normal TTS provider.
"""

from __future__ import annotations

import asyncio
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
    """Split desired phrases into loadable models and pending custom phrases."""
    import os

    models: list[str] = []
    pending: list[str] = []
    for phrase in desired:
        raw = phrase.strip()
        key = raw.lower()
        if key.endswith((".onnx", ".tflite")):
            if os.path.isfile(raw):
                if raw not in models:
                    models.append(raw)
            else:
                pending.append(raw)
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
        barge_in: bool = False,
        hot_mic_after_wake: bool = False,
        hot_mic_idle_minutes: int = 30,
    ) -> None:
        super().__init__()
        if not models:
            raise ValueError("WakeWordGate needs at least one loadable wake-word model")

        self._ack_choices = [p.strip() for p in (ack_phrase or "").split("|") if p.strip()]
        self._priler_enabled = False
        try:
            from jarvis.edge.priler_reactions import enabled as priler_enabled
            self._priler_enabled = priler_enabled()
        except Exception as exc:  # pragma: no cover - optional voice bridge
            logger.debug(f"Priler reaction bridge unavailable: {exc}")

        import openwakeword
        from openwakeword.model import Model

        openwakeword.utils.download_models()
        self._model = Model(wakeword_models=models, inference_framework="onnx")
        self._names = list(self._model.models.keys())
        self._threshold = threshold
        self._listen_window_s = listen_window_s
        self._hot_mic = hot_mic_after_wake
        self._hot_mic_idle_s = float(hot_mic_idle_minutes) * 60.0
        self._open_until = 0.0
        self._bot_speaking = False
        self._speaking_since = 0.0
        self._max_speak_s = 30.0
        self._suppress_during_tts = suppress_during_tts
        self._resume_after_tts = False
        self._barge_in = barge_in
        self._barge_threshold = min(0.95, threshold + 0.15)
        self._needs_reset = False
        logger.info(
            f"wake words active: {self._names} (threshold {threshold}"
            + (", barge-in on wake word" if barge_in else "")
            + (", Priler reaction ack ON" if self._priler_enabled else "")
            + ")"
        )

    @property
    def _awake(self) -> bool:
        return time.monotonic() < self._open_until

    @property
    def is_idle(self) -> bool:
        return not self._awake and not self._bot_speaking

    def _wake(self) -> None:
        if self._hot_mic:
            target = time.monotonic() + self._hot_mic_idle_s
            self._open_until = max(self._open_until, target)
        else:
            self._open_until = time.monotonic() + self._listen_window_s

    def _detect(self, frame: InputAudioRawFrame, threshold: float | None = None) -> str | None:
        samples = np.frombuffer(frame.audio, dtype=np.int16)
        if frame.num_channels and frame.num_channels > 1:
            samples = samples[:: frame.num_channels]
        if frame.sample_rate and frame.sample_rate != 16000:
            import soxr

            samples = soxr.resample(samples.astype(np.float32), frame.sample_rate, 16000).astype(np.int16)
        scores = self._model.predict(samples)
        min_score = threshold if threshold is not None else self._threshold
        best_name, best = max(scores.items(), key=lambda kv: kv[1], default=("", 0.0))
        if 0.2 <= best < min_score:
            logger.info(f"wake near-miss: '{best_name}' {best:.2f} < {min_score:.2f} threshold")
        for name, score in scores.items():
            if score >= min_score:
                return name
        return None

    async def _play_priler_ack(self) -> None:
        """Play an exact current Priler reaction and expose speaking state to the pipeline."""
        from jarvis.edge.priler_reactions import play_random_reply

        await self.push_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        self._bot_speaking = True
        self._speaking_since = time.monotonic()
        try:
            await play_random_reply()
        finally:
            self._bot_speaking = False
            await self.push_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    async def _ack(self) -> None:
        if self._priler_enabled:
            try:
                await self._play_priler_ack()
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Priler reaction failed; falling back to TTS ack: {exc}")

        # Never fall back to the old English framework acknowledgements when the assistant
        # is configured for Russian. This keeps the first spoken response in the same language
        # as the actual assistant reply.
        if self._ack_choices:
            raw_language = ""
            try:
                from jarvis.config import settings
                raw_language = (settings.reply_language or "").strip().lower()
            except Exception:
                pass
            if raw_language in {"russian", "русский", "ru"}:
                ack = random.choice(["Да, сэр.", "Слушаю, сэр.", "Да, сэр, я слушаю."])
            else:
                ack = random.choice(self._ack_choices)
            await self.push_frame(TTSSpeakFrame(ack), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._speaking_since = time.monotonic()
            if self._suppress_during_tts and self._awake:
                self._resume_after_tts = True
                self._open_until = 0.0
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            if self._awake or self._resume_after_tts:
                self._wake()
            self._resume_after_tts = False

        if isinstance(frame, InputAudioRawFrame):
            if self._bot_speaking and (time.monotonic() - self._speaking_since) > self._max_speak_s:
                logger.warning(
                    f"wake gate: bot-speaking stuck >{self._max_speak_s:.0f}s — force-clearing; resuming wake detection"
                )
                self._bot_speaking = False
                self._resume_after_tts = False
            if self._bot_speaking and self._suppress_during_tts:
                if self._barge_in:
                    if self._needs_reset:
                        self._model.reset()
                        self._needs_reset = False
                        return
                    hit = self._detect(frame, self._barge_threshold)
                    if hit:
                        logger.info(f"barge-in: wake word '{hit}' over TTS — interrupting")
                        await self.broadcast_interruption()
                        self._bot_speaking = False
                        self._resume_after_tts = False
                        self._wake()
                        self._needs_reset = True
            elif self._awake:
                self._needs_reset = True
                await self.push_frame(frame, direction)
            elif self._bot_speaking:
                self._needs_reset = True
            else:
                if self._needs_reset:
                    self._model.reset()
                    self._needs_reset = False
                    return
                hit = self._detect(frame)
                if hit:
                    self._wake()
                    logger.info(f"wake: '{hit}' detected — listening")
                    if self._priler_enabled or self._ack_choices:
                        asyncio.create_task(self._ack())
                return
            return

        await self.push_frame(frame, direction)
