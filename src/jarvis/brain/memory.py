"""Jarvis's persistent memory — the learned (L1) + journal (L2) layers.

The static `memory/*.md` files are who the owner *is*; this is what Jarvis *learns* as they talk:
one fact per note under `memory/learned/`, and a per-day journal under `memory/journal/` for
continuity ("what did we do yesterday?"). Plain Markdown so it stays the source of truth, editable
by hand, and later indexable by the Redis (L4) / vector (L5) accelerators without changing it.

Recall is a lightweight keyword + recency scorer — good enough for "what do you know about the
rabbit farm?" voice queries, and fast (no model, no network). Everything degrades gracefully: a
missing dir is created on first write; reading an absent store just returns nothing.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from jarvis.brain.tools.base import clip
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
    __slots__ = ("path", "text", "tags", "created", "mtime")

    def __init__(self, path: Path, text: str, tags: list[str], created: str,
                 mtime: float = 0.0) -> None:
        self.path = path
        self.text = text
        self.tags = tags
        self.created = created
        self.mtime = mtime   # cached at read time so hot-path callers needn't re-stat


class MemoryStore:
    """Filesystem-backed learned facts (L1) + daily journal (L2)."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base = Path(base_dir) if base_dir else DEFAULT_MEMORY_DIR
        self.learned_dir = self.base / "learned"
        self.journal_dir = self.base / "journal"
        # Parse cache: path -> (mtime, LearnedNote). recall()/digest() run on the hot path and were
        # re-reading + re-parsing every fact file on every call (~17ms for the corpus). We now read +
        # parse a file only when it's new or its mtime changed; an unchanged corpus is served from
        # memory (sub-millisecond). External edits/deletes are still picked up via the mtime/glob scan.
        self._note_cache: dict[str, tuple[float, LearnedNote]] = {}

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

    def _parse_note(self, p: Path, raw: str) -> LearnedNote:
        m = _FRONTMATTER_RE.match(raw)
        if m:
            meta, body = m.group(1), m.group(2).strip()
            tags: list[str] = []
            created = ""
            for line in meta.splitlines():
                if line.startswith("tags:"):
                    tags = [t.strip().lower() for t in line[5:].split(",") if t.strip()]
                elif line.startswith("created:"):
                    created = line[8:].strip()
        else:
            body, tags, created = raw.strip(), [], ""
        return LearnedNote(p, body, tags, created)

    def _iter_notes(self):
        if not self.learned_dir.is_dir():
            return
        seen: set[str] = set()
        # os.scandir hands back DirEntry objects whose .stat() is cached from the single directory
        # read (especially cheap on Windows, where a separate Path.stat() is a full extra syscall) —
        # so the freshness check costs ~one syscall for the whole directory, not one per file.
        try:
            entries = list(os.scandir(self.learned_dir))
        except OSError:
            return
        for entry in entries:
            if not entry.name.endswith(".md"):
                continue
            key = entry.path
            seen.add(key)
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            cached = self._note_cache.get(key)
            if cached and cached[0] == mtime:
                yield cached[1]
                continue
            try:
                raw = Path(entry.path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            note = self._parse_note(Path(entry.path), raw)
            note.mtime = mtime
            self._note_cache[key] = (mtime, note)
            yield note
        # Forget files that have since been deleted, so the cache can't grow unbounded or serve ghosts.
        if len(self._note_cache) > len(seen):
            for stale in [k for k in self._note_cache if k not in seen]:
                self._note_cache.pop(stale, None)

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
            mtime_by_key[key] = note.mtime   # cached at read time (no re-stat on the hot path)
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

    async def fused_recall(self, query: str, limit: int = 8, layers: tuple[str, ...] | None = None) -> list[dict]:
        """Cross-layer recall — returns ranked hits with layer tags so the LLM can cite them.

        Default layers: ("L1", "L2", "L3", "L5"). Each hit is a dict::

            {"layer": "L1", "text": "...", "score": 4.0, "source": "memory/learned/..."}

        L1 = learned facts (with optional L5 semantic blend).
        L2 = journal entries (most recent days only — journal grows fast; cap scan).
        L3 = vault notes (Obsidian) via search_vault tool.
        L5 = re-ranks L1 hits by cosine similarity when available (no separate layer; folds into L1).

        Falls back gracefully: any unavailable layer is silently skipped (no error, no crash).
        """
        query = (query or "").strip()
        if not query:
            return []
        layers = layers or ("L1", "L2", "L3", "L5")
        hits: list[dict] = []

        # L1 (+ L5 semantic re-rank of L1)
        if "L1" in layers:
            try:
                texts = self.recall(query, limit=limit, semantic=("L5" in layers))
                for i, t in enumerate(texts):
                    # `recall` is already sorted, so the first hit is the best.
                    score = max(0.0, float(limit - i))
                    hits.append({"layer": "L1", "text": t, "score": score, "source": "learned"})
            except Exception as e:  # noqa: BLE001
                logger.debug(f"fused_recall: L1 layer skipped ({e})")

        # L2 journal — scan the last 14 days' entries (each entry is one bullet).
        if "L2" in layers:
            try:
                terms = _terms(query)
                if terms and self.journal_dir.is_dir():
                    days = sorted(self.journal_dir.glob("*.md"), reverse=True)[:14]
                    for day in days:
                        try:
                            raw = day.read_text(encoding="utf-8", errors="ignore")
                        except OSError:
                            continue
                        # Entries are "- **HH:MM** — summary" — split on the dash lines.
                        for line in raw.splitlines():
                            if not line.startswith("- "):
                                continue
                            low = line.lower()
                            score = sum(low.count(t) for t in terms)
                            if score > 0:
                                hits.append({"layer": "L2", "text": line.lstrip("- ").strip(),
                                             "score": float(score), "source": str(day.name)})
            except Exception as e:  # noqa: BLE001
                logger.debug(f"fused_recall: L2 layer skipped ({e})")

        # L3 vault — delegate to the search_vault tool when available.
        if "L3" in layers:
            try:
                from jarvis.brain.tools.vault import search_vault
                res = await search_vault({"query": query, "limit": limit})
                if res and "couldn't" not in res.lower() and "no " not in res.lower()[:30]:
                    # search_vault returns a multi-line list; split into bullets for ranking.
                    for line in res.splitlines():
                        line = line.strip()
                        if not line or line.lower().startswith(("here", "nothing", "no ", "i ")):
                            continue
                        # Tiny length-weighted score so longer hits don't dominate the per-layer rank.
                        hits.append({"layer": "L3", "text": clip(line, 240),
                                     "score": 2.0 + min(2.0, len(line) / 200.0),
                                     "source": "vault"})
            except Exception as e:  # noqa: BLE001
                logger.debug(f"fused_recall: L3 layer skipped ({e})")

        # Rank: score desc, then L1 before L2 before L3 (slight tiebreak by layer priority).
        layer_priority = {"L1": 0, "L2": 1, "L3": 2}
        hits.sort(key=lambda h: (-h["score"], layer_priority.get(h["layer"], 9)))
        return hits[:limit]

    def recent_digest(self, limit: int = 20) -> list[str]:
        """The most recently learned facts, newest first — injected into the system prompt."""
        notes = sorted(self._iter_notes(), key=lambda n: n.mtime, reverse=True)
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
