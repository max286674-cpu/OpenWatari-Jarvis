"""Inspect constructor signatures we need for the Phase 0 pipeline."""

import inspect

from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.frames import frames as F

print("== LocalAudioTransportParams fields ==")
try:
    print(list(LocalAudioTransportParams.model_fields.keys()))
except Exception as e:
    print("err", e)

for cls in (LocalAudioTransport, DeepgramSTTService, ElevenLabsTTSService):
    try:
        print(f"\n== {cls.__name__}.__init__ ==")
        print(str(inspect.signature(cls.__init__)))
    except Exception as e:
        print("err", e)

print("\n== TranscriptionFrame fields ==")
print([f for f in dir(F.TranscriptionFrame) if not f.startswith("_")][:20])
print("\n== has InputAudioRawFrame/TTSAudioRawFrame? ==")
for name in ("TTSSpeakFrame", "TextFrame", "LLMMessagesFrame", "EndFrame", "TranscriptionFrame"):
    print(name, hasattr(F, name))
