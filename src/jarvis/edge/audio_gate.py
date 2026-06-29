"""HalfDuplexGate — stop Jarvis from hearing his own voice.

On open speakers the mic re-captures Jarvis's TTS, so the STT transcribes him and
he echoes himself forever. This gate drops mic audio while Jarvis is speaking (plus
a short tail cooldown for the speaker/buffer latency).

It's a deliberate stopgap: half-duplex means you can't talk over Jarvis yet. Phase 1
replaces this with acoustic echo cancellation (AEC) so barge-in works while he speaks.

Placement: directly after ``transport.input()`` and before the STT. The output
transport pushes Bot{Started,Stopped}SpeakingFrame UPSTREAM, so we observe them here.
"""

from __future__ import annotations

import time

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class HalfDuplexGate(FrameProcessor):
    def __init__(self, cooldown_s: float = 0.4, max_speak_s: float = 30.0) -> None:
        super().__init__()
        self._bot_speaking = False
        self._speaking_since = 0.0
        self._max_speak_s = max_speak_s  # watchdog: clear a stuck "speaking" mute (missed Stopped frame)
        self._muted_until = 0.0
        self._cooldown_s = cooldown_s

    @property
    def _muted(self) -> bool:
        # A stuck _bot_speaking (lost BotStoppedSpeaking) would mute the mic forever; auto-recover.
        if self._bot_speaking and (time.monotonic() - self._speaking_since) > self._max_speak_s:
            self._bot_speaking = False
        return self._bot_speaking or time.monotonic() < self._muted_until

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._speaking_since = time.monotonic()
            logger.debug("gate: muting mic (Jarvis speaking)")
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._muted_until = time.monotonic() + self._cooldown_s

        # Swallow mic audio while muted so the STT never hears Jarvis.
        if isinstance(frame, InputAudioRawFrame) and self._muted:
            return

        await self.push_frame(frame, direction)
