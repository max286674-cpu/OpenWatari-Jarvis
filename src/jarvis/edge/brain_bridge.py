"""JarvisBrain — the real brain in the voice pipeline (replaces EchoBrain in Phase 2).

On each finished transcript it runs Jarvis's own agent loop (personality + memory + tools)
and speaks the reply. Runs the brain IN-PROCESS on the edge for now; the same `JarvisAgent`
will later sit behind the edge<->brain WebSocket (`shared/protocol.py`) when the 24/7 VPS
brain service lands (Phase 4) — the pipeline contract here doesn't change.

Tool progress (e.g. consulting the fleet) is spoken as a short filler so Jarvis never goes
silent during a longer turn.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.brain.agent import JarvisAgent


class JarvisBrain(FrameProcessor):
    def __init__(self, agent: JarvisAgent | None = None) -> None:
        super().__init__()
        self._agent = agent or JarvisAgent()
        self._busy = False  # ignore overlapping transcripts while a turn is in flight
        self._turn_task: asyncio.Task | None = None

    async def warmup(self) -> None:
        await self._agent.warmup()
        self._start_scheduler()

    def _start_scheduler(self) -> None:
        """Start the proactive scheduler and teach it to SPEAK fired reminders through us."""
        try:
            from jarvis.brain.scheduler import SCHEDULER

            loop = asyncio.get_running_loop()

            def speak(message: str) -> None:
                # Called from the scheduler (same loop); push a spoken reminder downstream.
                loop.create_task(self.push_frame(TTSSpeakFrame(f"Reminder, sir: {message}")))

            SCHEDULER.start(on_speak=speak)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scheduler not started: {e}")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        # Barge-in: abort the in-flight turn so Jarvis stops talking and listens.
        if isinstance(frame, InterruptionFrame):
            if self._turn_task and not self._turn_task.done():
                logger.info("brain: interrupted — cancelling current turn")
                self._turn_task.cancel()
            self._busy = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            text = (getattr(frame, "text", "") or "").strip()
            if text and not self._busy:
                self._turn_task = asyncio.create_task(self._handle(text))
            return  # consume the transcription

        await self.push_frame(frame, direction)

    async def _handle(self, text: str) -> None:
        self._busy = True
        try:
            logger.info(f"heard: {text!r}")

            def progress(note: str) -> None:
                # Spoken filler so a longer (e.g. fleet) turn isn't dead air.
                asyncio.create_task(self.push_frame(TTSSpeakFrame(note)))

            reply = await self._agent.respond(text, on_progress=progress)
            if reply:
                logger.info(f"reply: {reply!r}")
                await self.push_frame(TTSSpeakFrame(reply))
        except Exception:  # noqa: BLE001
            logger.exception("brain turn failed")
            await self.push_frame(TTSSpeakFrame("Sorry sir, I hit an error handling that."))
        finally:
            self._busy = False
