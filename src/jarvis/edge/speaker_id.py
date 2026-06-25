"""Speaker biometrics — "respond only to the owner's voice" (Phase 5).

Identity gate for the voice loop: after enrolling the owner's voice once, Jarvis compares each
spoken utterance's voiceprint to the enrolled one and **ignores commands from other voices**
(the TV, a guest). This is layered on top of the wake word + half-duplex gate as a final check.

Design
------
- **Backend = SpeechBrain ECAPA-TDNN** (``speechbrain/spkrec-ecapa-voxceleb``): a 192-dim speaker
  embedding, CPU-runnable on short clips. It's heavy (pulls torch), so it lives in the optional
  ``identity`` extra and is imported **lazily**. If it isn't installed (or no profile is enrolled,
  or the feature is off), the verifier **degrades to "accept everything"** — the pipeline never
  breaks, matching the rest of Jarvis's graceful-degradation contract.
- Enrollment (``bench/enroll_voice.py``) records a few seconds of the owner, averages the embeddings,
  L2-normalises, and saves a small JSON voiceprint to ``JARVIS_SPEAKER_PROFILE``.
- At runtime, ``SpeakerGate`` (a Pipecat processor) buffers recent mic audio and, when a transcript
  is produced, embeds that audio and accepts the turn only if cosine-similarity ≥ threshold.

The gate **decision** is a pure function (``should_accept``) so it's unit-testable without torch.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from loguru import logger

from jarvis.config import settings


def _default_profile_path() -> Path:
    return Path(settings.speaker_profile_path or
                str(Path(__file__).resolve().parents[3] / "voiceprint.json"))


def should_accept(score: float, threshold: float, has_profile: bool, enabled: bool) -> bool:
    """Pure gate decision. Accept (don't gate) unless the feature is fully active AND we have a
    profile to compare against. Only then does the similarity score decide."""
    if not enabled or not has_profile:
        return True
    return score >= threshold


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SpeakerVerifier:
    """Loads the enrolled voiceprint + (lazily) the ECAPA encoder; verifies utterance audio.

    ``embedder`` can be injected (tests pass a stub); otherwise SpeechBrain is loaded on first use.
    """

    def __init__(self, embedder=None) -> None:
        self._embedder = embedder           # callable(pcm_float32_mono_16k) -> np.ndarray | None
        self._tried_load = embedder is not None
        self._profile: np.ndarray | None = None
        self._load_profile()

    # ---- profile ----------------------------------------------------------------------
    def _load_profile(self) -> None:
        path = _default_profile_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._profile = np.asarray(data["embedding"], dtype=np.float32)
                logger.info(f"speaker profile loaded ({self._profile.shape[0]}-dim) from {path.name}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"speaker profile load failed: {e}")

    @property
    def has_profile(self) -> bool:
        return self._profile is not None

    @staticmethod
    def save_profile(embedding: np.ndarray) -> Path:
        path = _default_profile_path()
        emb = np.asarray(embedding, dtype=np.float32)
        emb = emb / (np.linalg.norm(emb) or 1.0)
        path.write_text(json.dumps({"embedding": emb.tolist()}), encoding="utf-8")
        return path

    # ---- embedding backend ------------------------------------------------------------
    def _ensure_embedder(self):
        if self._embedder is not None or self._tried_load:
            return self._embedder
        self._tried_load = True
        try:
            import torch  # noqa: F401
            from speechbrain.inference.speaker import EncoderClassifier

            savedir = str(Path(__file__).resolve().parents[3] / ".speechbrain-ecapa")
            clf = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb", savedir=savedir
            )

            def _embed(wav: np.ndarray) -> np.ndarray:
                import torch as _t

                t = _t.tensor(wav).unsqueeze(0)
                with _t.no_grad():
                    emb = clf.encode_batch(t).squeeze().cpu().numpy()
                return emb.astype(np.float32)

            self._embedder = _embed
            logger.info("speaker verifier: SpeechBrain ECAPA loaded")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"speaker verifier disabled (backend unavailable: {type(e).__name__}). "
                "Install the 'identity' extra to enable: uv sync --extra identity"
            )
        return self._embedder

    def embed(self, pcm16: bytes, sample_rate: int = 16000) -> np.ndarray | None:
        """Embed int16 mono PCM. Returns None if the backend isn't available."""
        emb_fn = self._ensure_embedder()
        if emb_fn is None:
            return None
        wav = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if wav.size < sample_rate // 2:  # <0.5s is too short to be reliable
            return None
        try:
            return emb_fn(wav)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"speaker embed failed: {e}")
            return None

    def verify(self, pcm16: bytes, sample_rate: int = 16000) -> tuple[bool, float]:
        """Return (accept, score). Degrades to (True, 1.0) when unavailable/unenrolled/off."""
        if not settings.speaker_id_enabled or not self.has_profile:
            return True, 1.0
        emb = self.embed(pcm16, sample_rate)
        if emb is None:
            return True, 1.0  # backend missing -> don't lock the owner out
        score = cosine(emb, self._profile)
        accept = should_accept(score, settings.speaker_threshold, self.has_profile, True)
        return accept, score
