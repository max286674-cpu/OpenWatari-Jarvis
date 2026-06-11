"""Jarvis's persistent memory — the learned (L1) + journal (L2) layers.

The static `memory/*.md` files are who Vazghen *is*; this is what Jarvis *learns* as they talk:
one fact per note under `memory/learned/`, and a per-day journal under `memory/journal/` for
continuity ("what did we do yesterday?"). Plain Markdown so it stays the source of truth, editable
by hand, and later indexable by the Redis (L4) / vector (L5) accelerators without changing it.

Recall is a lightweight keyword + recency scorer — good enough for "what do you know about the
rabbit farm?" voice queries, and fast (no model, no network). Everything degrades gracefully: a
missing dir is created on first write; reading an absent store just returns nothing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from jarvis.config import settings

# repo root = .../src/jarvis/brain/memory.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_DIR = _REPO_ROOT / "memory"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _slug(text: str, max_words: int = 6) -> str:
    words = _SLUG_RE.sub("-", text.lower()).strip("-").split("-")
    return "-".join(w for w in words if w)[:60] or "note"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _terms(query: str) -> list[str]:
    return [t for t in _SLUG_RE.sub(" ", query.lower()).split() if len(t) > 1]


class LearnedNote:
    __slots__ = ("path", "text", "tags", "created")

    def __init__(self, path: Path, text: str, tags: list[str], created: str) -> None:
        self.path = path
        self.text = text
        self.tags = tags
        self.created = created


class MemoryStore:
    """Filesystem-backed learned facts (L1) + daily journal (L2)."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base = Path(base_dir) if base_dir else DEFAULT_MEMORY_DIR
        self.learned_dir = self.base / "learned"
        self.journal_dir = self.base / "journal"

    # ---- L1: learned facts ------------------------------------------------------------
    def remember(self, text: str, tags: list[str] | None = None) -> Path | None:
        text = (text or "").strip()
        if not text:
            return None
        tags = [t.strip().lower() for t in (tags or []) if t.strip()]
        # Dedup: identical normalised fact already stored -> return it, don't duplicate.
        for note in self._iter_notes():
            if _norm(note.text) == _norm(text):
                logger.info(f"memory: already knew {text[:50]!r}")
                return note.path
        self.learned_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc)
        fname = f"{ts:%Y%m%d-%H%M%S}-{_slug(text)}.md"
        path = self.learned_dir / fname
        tagline = ", ".join(tags)
        path.write_text(
            f"---\ncreated: {ts.isoformat()}\ntags: {tagline}\n---\n{text}\n",
            encoding="utf-8",
        )
        logger.info(f"memory: learned {text[:60]!r}" + (f" [{tagline}]" if tags else ""))
        return path

    def _iter_notes(self):
        if not self.learned_dir.is_dir():
            return
        for p in self.learned_dir.glob("*.md"):
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = _FRONTMATTER_RE.match(raw)
            if m:
                meta, body = m.group(1), m.group(2).strip()
                tags = []
                created = ""
                for line in meta.splitlines():
                    if line.startswith("tags:"):
                        tags = [t.strip().lower() for t in line[5:].split(",") if t.strip()]
                    elif line.startswith("created:"):
                        created = line[8:].strip()
            else:
                body, tags, created = raw.strip(), [], ""
            yield LearnedNote(p, body, tags, created)

    def recall(self, query: str, limit: int = 5, semantic=None) -> list[str]:
        """Best matching learned facts for ``query``.

        Always runs the fast keyword scorer (count + tag boost). When an L5 semantic index is
        available (an embedder is installed), it *also* blends in cosine similarity so facts that
        match by meaning — "bunnies" → "rabbit farm" — surface even with zero literal overlap.
        Pass ``semantic=False`` to force keyword-only; ``semantic`` may be an injected index (tests).
        """
        query = (query or "").strip()
        if not query:
            return []
        terms = _terms(query)

        notes = list(self._iter_notes())
        # Keyword score per note (by file path, used as a stable key).
        kw: dict[str, float] = {}
        text_by_key: dict[str, str] = {}
        mtime_by_key: dict[str, float] = {}
        for note in notes:
            key = str(note.path)
            text_by_key[key] = note.text
            try:
                mtime_by_key[key] = note.path.stat().st_mtime
            except OSError:
                mtime_by_key[key] = 0.0
            low = note.text.lower()
            score = 0.0
            for t in terms:
                score += low.count(t)
                if t in note.tags:
                    score += 5
            kw[key] = score

        # Optional semantic blend.
        sem: dict[str, float] = {}
        use_sem = semantic if semantic is not None else settings.memory_semantic_enabled
        if use_sem:
            index = semantic if hasattr(semantic, "scores") else None
            if index is None:
                from jarvis.brain.semantic import INDEX as index  # type: ignore
            items = [(k, mtime_by_key[k], text_by_key[k]) for k in text_by_key]
            sem = index.scores(query, items)

        weight = settings.memory_semantic_weight
        combined: list[tuple[float, float, str]] = []
        for key in text_by_key:
            total = kw.get(key, 0.0) + weight * sem.get(key, 0.0)
            if total > 0:
                combined.append((total, mtime_by_key[key], text_by_key[key]))
        combined.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [text for _, _, text in combined[:limit]]

    def recent_digest(self, limit: int = 20) -> list[str]:
        """The most recently learned facts, newest first — injected into the system prompt."""
        notes = sorted(self._iter_notes(), key=lambda n: n.path.stat().st_mtime, reverse=True)
        return [n.text for n in notes[:limit]]

    def forget(self, query: str) -> str | None:
        """Delete the single best-matching learned fact; return its text, or None."""
        terms = _terms(query)
        if not terms:
            return None
        best: tuple[int, Path, str] | None = None
        for note in self._iter_notes():
            low = note.text.lower()
            score = sum(low.count(t) for t in terms)
            if score > 0 and (best is None or score > best[0]):
                best = (score, note.path, note.text)
        if best is None:
            return None
        try:
            best[1].unlink()
            logger.info(f"memory: forgot {best[2][:50]!r}")
            return best[2]
        except OSError:
            return None

    def count(self) -> int:
        return sum(1 for _ in self._iter_notes())

    # ---- L2: daily journal ------------------------------------------------------------
    def journal_append(self, summary: str, when: datetime | None = None) -> Path | None:
        summary = (summary or "").strip()
        if not summary:
            return None
        when = when or datetime.now(timezone.utc)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        path = self.journal_dir / f"{when:%Y-%m-%d}.md"
        header = "" if path.exists() else f"# Journal — {when:%Y-%m-%d}\n\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{header}- **{when:%H:%M}** — {summary}\n")
        logger.info(f"memory: journalled {summary[:60]!r}")
        return path

    def read_journal(self, when: datetime | None = None) -> str:
        """Read a day's journal (default today); fall back to the most recent day."""
        if when is not None:
            p = self.journal_dir / f"{when:%Y-%m-%d}.md"
            return p.read_text(encoding="utf-8", errors="ignore").strip() if p.is_file() else ""
        if not self.journal_dir.is_dir():
            return ""
        days = sorted(self.journal_dir.glob("*.md"))
        return days[-1].read_text(encoding="utf-8", errors="ignore").strip() if days else ""


# A process-wide default store (the repo's memory/ dir).
STORE = MemoryStore()
