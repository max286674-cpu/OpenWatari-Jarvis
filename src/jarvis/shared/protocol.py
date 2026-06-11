"""The edge <-> brain WebSocket protocol.

Deliberately mirrors OpenClaw's stream event shape (`assistant` / `tool` / `lifecycle`)
so the brain can relay fleet events straight to the edge for spoken progress.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


# ---- edge -> brain --------------------------------------------------------------------
class Hello(BaseModel):
    """A client (laptop / iPhone / Mentra glasses) registering its session + device (Phase 6).

    ``device_id`` is one of the supported devices (laptop|iphone|airpods|mentra, or an alias).
    ``headphones_connected`` lets a phone/laptop say AirPods are connected, so the brain routes
    everything to the headphones (private → barge-in on)."""

    type: Literal["hello"] = "hello"
    session_id: str
    device_id: str = "laptop"
    headphones_connected: bool = False


class Utterance(BaseModel):
    """A finished, transcribed user turn sent from edge to brain."""

    type: Literal["utterance"] = "utterance"
    session_id: str
    text: str
    speaker_verified: bool = False   # set by Phase-5 voice biometrics
    ts_user_stop_ms: int             # for TTFW measurement
    device_id: str = "laptop"        # which of the four devices this turn came from (Phase 6)


class Barge(BaseModel):
    """User started talking over Jarvis — cancel in-flight generation."""

    type: Literal["barge"] = "barge"
    session_id: str


# ---- brain -> edge --------------------------------------------------------------------
class StreamKind(str, Enum):
    assistant = "assistant"   # spoken token deltas
    tool = "tool"             # tool/agent activity -> optional spoken progress
    lifecycle = "lifecycle"   # start / end / error


class StreamEvent(BaseModel):
    """A streamed reply chunk from brain to edge (drives incremental TTS)."""

    type: Literal["stream"] = "stream"
    session_id: str
    kind: StreamKind
    delta: str = ""           # text to speak (assistant) or status note (tool/lifecycle)
    final: bool = False       # last chunk of this turn


EdgeToBrain = Hello | Utterance | Barge
BrainToEdge = StreamEvent
