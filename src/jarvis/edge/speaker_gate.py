"""SpeakerGate — drop transcripts that aren't in the owner's voice (Phase 5).

Sits AFTER the STT. It keeps a short rolling buffer of recent mic audio; when the STT produces a
``TranscriptionFrame``, it embeds that buffered audio and compares it to the enrolled voiceprint
(``SpeakerVerifier``). If the voice doesn't match, the transcript is **dropped** so the brain never
acts on it — Jarvis simply stays silent for a stranger. Everything else (audio, control frames)
passes through untouched.

Graceful by construction: if speaker-id is off, no profile is enrolled, or the ECAPA backend isn't
installed, ``verify`` returns accept=True, so the gate is a no-op (see ``speaker_id.py``).
"""

from __future__ import annotations

from collections import deque

from loguru import logger
from pipecat.frames.frames import Frame, InputAudioRawFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from jarvis.edge.speaker_id import SpeakerVerifier


class SpeakerGate(FrameProcessor):
    def __init__(self, verifier: SpeakerVerifier | None = None, window_s: float = 6.0) -> None:
        super().__init__()
        self._verifier = verifier or SpeakerVerifier()
        self._window_s = window_s
        self._buf: deque[bytes] = deque()
        self._buf_bytes = 0
        self._sample_rate = 16000
        # bytes for the window at 16-bit mono
        self._max_bytes = int(window_s * self._sample_rate * 2)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            self._sample_rate = frame.sample_rate or self._sample_rate
            self._max_bytes = int(self._window_s * self._sample_rate * 2)
            self._buf.append(frame.audio)
            self._buf_bytes += len(frame.audio)
            while self._buf_bytes > self._max_bytes and len(self._buf) > 1:
                self._buf_bytes -= len(self._buf.popleft())
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            # Only gate when the feature is actually active + enrolled (cheap fast-path otherwise).
            if self._verifier.has_profile:
                audio = b"".join(self._buf)
                accept, score = self._verifier.verify(audio, self._sample_rate)
                if not accept:
                    logger.info(f"speaker gate: ignored ({score:.2f}) — not the owner's voice: "
                                f"{frame.text!r}")
                    return  # drop: brain never sees it
                # INFO (not DEBUG) so the owner's real accept-scores are visible in production — the
                # only way to calibrate the threshold against a live owner-vs-stranger separation.
                logger.info(f"speaker gate: accepted ({score:.2f}) — {frame.text!r}")
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)
