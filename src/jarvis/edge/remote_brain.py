"""RemoteBrain — the unified-brain twin of the in-process JarvisBrain.

When ``JARVIS_BRAIN_MODE=remote`` (or ``auto`` and the brain is reachable), the laptop edge stops
running its own agent and becomes a thin client to the 24/7 VPS brain: there is then ONE Watari and
ONE memory across the laptop, phone, and glasses. Audio (STT/TTS, wake word, VAD) still runs locally
for privacy + mic latency; only the finished transcript goes to the brain, which streams the reply
back sentence-by-sentence for incremental TTS — same low-latency feel as local.

Pipeline placement is identical to JarvisBrain: STT -> RemoteBrain -> TTS.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from pipecat.frames.frames import Frame, InterruptionFrame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.edge.brain_client import BrainClient
from jarvis.shared.protocol import StreamEvent, StreamKind


class RemoteBrain(FrameProcessor):
    def __init__(
        self,
        session_id: str = "laptop-edge",
        device_id: str = "laptop",
        headphones_connected: bool = False,
    ) -> None:
        super().__init__()
        self._client = BrainClient(
            session_id=session_id,
            device_id=device_id,
            headphones_connected=headphones_connected,
            on_event=self._on_event,
        )
        self._task: asyncio.Task | None = None

    async def start(self, connect_timeout_s: float = 3.0) -> bool:
        """Begin the supervised link. Returns True once connected within the timeout (so the
        caller can fall back to the local brain if the VPS is unreachable)."""
        self._task = asyncio.create_task(self._client.run())
        deadline = asyncio.get_running_loop().time() + connect_timeout_s
        while asyncio.get_running_loop().time() < deadline:
            if self._client.connected:
                logger.info("RemoteBrain: linked to the VPS brain")
                return True
            await asyncio.sleep(0.1)
        logger.warning("RemoteBrain: VPS brain not reachable within timeout")
        return self._client.connected

    async def _on_event(self, ev: StreamEvent) -> None:
        # Assistant text and spoken tool-progress both go to TTS; lifecycle events are control-only.
        if ev.kind in (StreamKind.assistant, StreamKind.tool) and ev.delta.strip():
            await self.push_frame(TTSSpeakFrame(ev.delta.strip()))

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame):
            await self._client.barge()          # tell the brain to cancel the in-flight turn
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            text = (getattr(frame, "text", "") or "").strip()
            if text:
                logger.info(f"heard: {text!r} -> brain")
                await self._client.send_utterance(text)
            return  # consume; the reply arrives async via _on_event

        await self.push_frame(frame, direction)

    async def stop(self) -> None:
        await self._client.stop()
