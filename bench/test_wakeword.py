"""De-risk Phase 1: openWakeWord 'hey_jarvis' loads + runs on Windows CPU."""

import time

import numpy as np
import openwakeword
from openwakeword.model import Model

print("downloading openWakeWord models (first run only)…", flush=True)
openwakeword.utils.download_models()

m = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
print("models:", list(m.models.keys()))

# 80ms frames of 16kHz int16 audio (1280 samples) — openWakeWord's expected chunk.
frame = np.zeros(1280, dtype=np.int16)
# warm up
for _ in range(5):
    m.predict(frame)
t0 = time.perf_counter()
N = 50
for _ in range(N):
    pred = m.predict(frame)
per_ms = (time.perf_counter() - t0) / N * 1000
print(f"per-frame inference: {per_ms:.2f} ms  (frame = 80ms of audio)")
print("realtime factor:", round(80 / per_ms, 1), "x faster than realtime")
print("silence score:", round(pred["hey_jarvis"], 4))
print("OK — wake word ready" if per_ms < 80 else "WARN — slower than realtime")
