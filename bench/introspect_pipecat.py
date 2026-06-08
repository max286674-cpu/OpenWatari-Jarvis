"""One-off: verify the Pipecat 1.x import paths we rely on in Phase 0."""

import importlib

probes = [
    "pipecat.pipeline.pipeline:Pipeline",
    "pipecat.pipeline.task:PipelineTask",
    "pipecat.pipeline.runner:PipelineRunner",
    "pipecat.transports.local.audio:LocalAudioTransport",
    "pipecat.transports.local.audio:LocalAudioTransportParams",
    "pipecat.services.deepgram.stt:DeepgramSTTService",
    "pipecat.services.elevenlabs.tts:ElevenLabsTTSService",
    "pipecat.frames.frames:TranscriptionFrame",
    "pipecat.frames.frames:TTSSpeakFrame",
    "pipecat.processors.frame_processor:FrameProcessor",
    "pipecat.processors.frame_processor:FrameDirection",
]

import pipecat

print("pipecat version:", getattr(pipecat, "__version__", "?"))
for p in probes:
    mod, _, attr = p.partition(":")
    try:
        m = importlib.import_module(mod)
        print(("OK   " if hasattr(m, attr) else "NOATTR "), p)
    except Exception as e:
        print("FAIL  ", p, "->", type(e).__name__, str(e)[:100])
