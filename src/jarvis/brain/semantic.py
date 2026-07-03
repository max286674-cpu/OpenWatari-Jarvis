"""L5 semantic recall — find facts by *meaning*, not just keywords. Strictly optional.

Keyword recall (``MemoryStore.recall``) misses "what do you know about my bunnies?" when the stored
fact says "rabbit farm". This layer closes that gap by ranking learned facts on embedding cosine
similarity and blending that into the keyword score.

It is **entirely graceful**: if no local embedder is installed it reports ``available == False`` and
recall silently stays keyword-only — no crash, no slow model download forced on anyone. When
``sentence-transformers`` *is* present, a small CPU model (``all-MiniLM-L6-v2`` by default) is loaded
lazily on first use. Per-fact embeddings are memoised by (path, mtime) so re-ranking is cheap and a
fact re-embeds only when its file changes.

The embedder is injectable (``SemanticIndex(embed_fn=...)``) so it can be unit-tested with a tiny
deterministic stub — no heavy dependency needed to verify the ranking maths.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from loguru import logger

from jarvis.config import settings

Vector = Sequence[float]
EmbedFn = Callable[[list[str]], list[Vector]]


def _cosine(a: Vector, b: Vector) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticIndex:
    """Lazy, optional embedding ranker. ``available`` is False until an embedder loads."""

    def __init__(self, embed_fn: EmbedFn | None = None, model_name: str | None = None) -> None:
        self._embed_fn = embed_fn          # injected (tests) — skips model loading entirely
        self._model = None                 # lazily-loaded sentence-transformers model
        self._model_name = model_name or settings.memory_semantic_model
        self._load_failed = False
        self._cache: dict[tuple[str, float], Vector] = {}  # (key, mtime) -> embedding

    # ---- embedder plumbing ------------------------------------------------------------
    def _ensure_embedder(self) -> EmbedFn | None:
        if self._embed_fn is not None:
            return self._embed_fn
        if self._model is not None:
            return self._model_embed
        if self._load_failed:
            return None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self._model_name)
            logger.info(f"L5 semantic recall: loaded embedder '{self._model_name}'")
            return self._model_embed
        except Exception as e:  # noqa: BLE001
            # No local model (~1GB torch) — fall back to the Jina embeddings API if its key is
            # already configured (it powers the web reader too). No key = honest keyword-only.
            if settings.jina_api_key:
                logger.info("L5 semantic recall: using Jina embeddings API (no local model)")
                return self._jina_embed
            self._load_failed = True
            logger.info(f"L5 semantic recall unavailable ({type(e).__name__}); keyword recall only")
            return None

    def _model_embed(self, texts: list[str]) -> list[Vector]:
        return [list(v) for v in self._model.encode(texts, normalize_embeddings=False)]

    def _jina_embed(self, texts: list[str]) -> list[Vector]:
        import httpx

        r = httpx.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.jina_api_key}"},
            json={"model": "jina-embeddings-v3", "task": "text-matching", "input": texts},
            timeout=10,
        )
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    @property
    def available(self) -> bool:
        return self._ensure_embedder() is not None

    # ---- ranking ----------------------------------------------------------------------
    def _embed_cached(self, embed: EmbedFn, items: list[tuple[str, float, str]]) -> dict[str, Vector]:
        """Embed each (cache_key, mtime, text), reusing cached vectors when unchanged."""
        out: dict[str, Vector] = {}
        to_compute: list[tuple[str, str]] = []  # (cache_key, text)
        for key, mtime, text in items:
            cached = self._cache.get((key, mtime))
            if cached is not None:
                out[key] = cached
            else:
                to_compute.append((key, text))
        if to_compute:
            vecs = embed([t for _, t in to_compute])
            for (key, _), vec in zip(to_compute, vecs):
                out[key] = vec
            # refresh cache with current mtimes (drop stale entries for these keys)
            mtime_by_key = {k: m for k, m, _ in items}
            for key, _ in to_compute:
                self._cache[(key, mtime_by_key[key])] = out[key]
        return out

    def scores(self, query: str, items: list[tuple[str, float, str]]) -> dict[str, float]:
        """Cosine similarity in [0,1]-ish per cache_key, or {} if no embedder is available.

        ``items`` are (cache_key, mtime, text). The cache_key identifies a fact for memoisation.
        """
        embed = self._ensure_embedder()
        if embed is None or not items:
            return {}
        try:
            qvec = embed([query])[0]
            vecs = self._embed_cached(embed, items)
            return {key: _cosine(qvec, vecs[key]) for key in vecs}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"semantic scoring failed ({type(e).__name__}); keyword-only this call")
            return {}


# Process-wide index (keyword-only until/unless an embedder is installed).
INDEX = SemanticIndex()
