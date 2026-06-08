"""Find the non-deprecated ElevenLabs settings + runner APIs."""

import inspect

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

print("== ElevenLabsTTSService.Settings exists? ==", hasattr(ElevenLabsTTSService, "Settings"))
S = getattr(ElevenLabsTTSService, "Settings", None)
if S is not None:
    try:
        print("Settings fields:", list(S.model_fields.keys()))
    except Exception as e:
        print("sig:", inspect.signature(S))

# WorkerRunner replacement
try:
    from pipecat.workers.runner import WorkerRunner
    print("\nWorkerRunner.__init__:", str(inspect.signature(WorkerRunner.__init__)))
    print("WorkerRunner.run     :", str(inspect.signature(WorkerRunner.run)))
except Exception as e:
    print("WorkerRunner import failed:", type(e).__name__, e)
