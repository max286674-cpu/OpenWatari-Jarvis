"""TTFWMeter — measure Time-To-First-Word live in the pipeline (Phase 5).

Times the gap from when the user stops speaking (``UserStoppedSpeakingFrame``) to the first audible
word of Jarvis's reply (``BotStartedSpeakingFrame``), in milliseconds, and records it into a shared
``TTFW`` accumulator (``bench/benchmarks.py``). Logs each sample; the TUI / a bench run reads the
accumulator for the summary. Pure pass-through — never alters the stream.

Placement: late in the pipeline (e.g. right before ``transport.output()``) so it sees both the
user-stop (pushed upstream by VAD) and the bot-start (pushed upstream by the output transport).
"""

from __future__ import annotations

import time

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    Frame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.bench_metrics import TTFW


class TTFWMeter(FrameProcessor):
    def __init__(self, accumulator: TTFW | None = None) -> None:
        super().__init__()
        self.ttfw = accumulator or TTFW()
        self._user_stopped_at: float | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._user_stopped_at = time.monotonic()
        elif isinstance(frame, BotStartedSpeakingFrame) and self._user_stopped_at is not None:
            ms = (time.monotonic() - self._user_stopped_at) * 1000.0
            self.ttfw.record(ms)
            s = self.ttfw.summary()
            logger.info(f"TTFW {ms:.0f} ms (mean {s['mean']:.0f}, n={s['count']})")
            self._user_stopped_at = None

        await self.push_frame(frame, direction)
