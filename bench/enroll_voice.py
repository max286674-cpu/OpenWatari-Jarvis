"""Enroll Vazghen's voice for speaker biometrics (Phase 5).

Records a few short clips from the mic, averages their ECAPA embeddings into one voiceprint, and
saves it to JARVIS_SPEAKER_PROFILE (default <repo>/voiceprint.json). After this, set
JARVIS_SPEAKER_ID_ENABLED=true and Jarvis will obey only your voice.

Needs the 'identity' extra:  uv sync --extra identity
Run:  uv run python bench/enroll_voice.py
"""

from __future__ import annotations

import sys
import time

import numpy as np

from jarvis.edge.speaker_id import SpeakerVerifier

SR = 16000
CLIP_S = 4
N_CLIPS = 3
PROMPTS = [
    "Say: 'Hey Jarvis, this is Vazghen.'",
    "Say any sentence in your normal voice.",
    "Say one more sentence, a little longer.",
]


def _record(seconds: int) -> bytes:
    import pyaudio

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SR, input=True,
                     frames_per_buffer=1024)
    frames = []
    for _ in range(int(SR / 1024 * seconds)):
        frames.append(stream.read(1024, exception_on_overflow=False))
    stream.stop_stream()
    stream.close()
    pa.terminate()
    return b"".join(frames)


def main() -> None:
    verifier = SpeakerVerifier()
    if verifier._ensure_embedder() is None:  # noqa: SLF001
        print("ECAPA backend not available. Install it:  uv sync --extra identity")
        sys.exit(1)

    embeddings = []
    for i in range(N_CLIPS):
        print(f"\n[{i + 1}/{N_CLIPS}] {PROMPTS[i % len(PROMPTS)]}")
        for c in (3, 2, 1):
            print(f"  recording in {c}…", end="\r", flush=True)
            time.sleep(1)
        print(f"  ● recording {CLIP_S}s — speak now")
        pcm = _record(CLIP_S)
        emb = verifier.embed(pcm, SR)
        if emb is None:
            print("  (clip too short / failed, retrying)")
            continue
        embeddings.append(emb / (np.linalg.norm(emb) or 1.0))
        print("  captured ✓")

    if not embeddings:
        print("No usable clips captured.")
        sys.exit(1)

    mean = np.mean(np.stack(embeddings), axis=0)
    path = SpeakerVerifier.save_profile(mean)
    print(f"\nVoiceprint saved to {path} ({mean.shape[0]}-dim, {len(embeddings)} clips).")
    print("Now set JARVIS_SPEAKER_ID_ENABLED=true in .env to gate commands to your voice.")


if __name__ == "__main__":
    main()
