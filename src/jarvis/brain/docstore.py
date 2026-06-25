"""Document RAG — "read this doc and answer" over a TEMPORARY local index (Phase 4.4).

Watari ingests one local document into an in-memory, chunked index, answers questions grounded in it,
and drops it on request. It reuses the same lightweight keyword scorer as L1 memory (plus the optional
L5 semantic blend when an embedder is installed), so there's no new heavy machinery and it works
offline. Text/Markdown/code/CSV/JSON are read directly; PDF is supported only if a PDF reader is
importable (pypdf / pdfminer / PyMuPDF), otherwise it returns a clear "install a PDF reader" note —
never a crash, and never a silent wrong answer.

The index is deliberately EPHEMERAL (one document at a time, in memory): loading a new doc replaces it,
`clear()` drops it, and nothing is persisted — a scratch pad, not a second memory.
"""

from __future__ import annotations

import re
from pathlib import Path

from jarvis.config import settings

_WORD_RE = re.compile(r"[^a-z0-9]+")
_TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".log",
              ".py", ".js", ".ts", ".html", ".xml", ".yaml", ".yml", ".ini", ".cfg"}


def _terms(text: str) -> list[str]:
    return [t for t in _WORD_RE.sub(" ", text.lower()).split() if len(t) > 1]


def _extract_pdf(path: Path) -> str | None:
    """Best-effort PDF text via whatever reader is installed; None if none is."""
    try:
        from pypdf import PdfReader  # type: ignore

        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except ImportError:
        pass
    try:
        import fitz  # type: ignore  # PyMuPDF

        with fitz.open(str(path)) as doc:
            return "\n".join(page.get_text() for page in doc)
    except ImportError:
        return None


def _chunk(text: str, size: int = 700) -> list[str]:
    """Split into ~size-char chunks on paragraph boundaries (keeps related lines together)."""
    chunks: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 > size and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


class DocStore:
    """A one-document, in-memory chunked index. Not persisted, replaced on each load."""

    def __init__(self) -> None:
        self.source: str | None = None
        self._chunks: list[str] = []

    def loaded(self) -> bool:
        return bool(self._chunks)

    def load(self, path: str) -> tuple[bool, str]:
        """Ingest a local document. Returns (ok, message). Message is a brief, speakable note."""
        p = Path(path).expanduser()
        if not p.is_file():
            return False, f"I can't find a file at '{path}', sir."
        try:
            if p.stat().st_size > 5_000_000:
                return False, f"'{p.name}' is too large to read in one go, sir (over 5 MB)."
        except OSError:
            pass
        suffix = p.suffix.lower()
        if suffix == ".pdf":
            text = _extract_pdf(p)
            if text is None:
                return False, ("That's a PDF, sir, and no PDF reader is installed. Run "
                               "`uv pip install pypdf` and I'll be able to read it.")
        elif suffix in _TEXT_EXTS or suffix == "":
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                return False, f"I couldn't read '{p.name}', sir: {type(e).__name__}."
        else:
            return False, f"I don't know how to read a '{suffix}' file, sir."
        chunks = _chunk(text)
        if not chunks:
            return False, f"'{p.name}' seems to be empty, sir."
        self.source, self._chunks = p.name, chunks
        words = sum(len(c.split()) for c in chunks)
        head = " ".join(text.split())[:600]
        return True, (f"Loaded '{p.name}', sir — {len(chunks)} sections, about {words} words. "
                      f"It opens: {head}")

    def ask(self, query: str, k: int = 4) -> list[str]:
        """Return the top-k most relevant chunks for a query (keyword + optional semantic)."""
        if not self._chunks:
            return []
        terms = _terms(query)
        kw = []
        for i, ch in enumerate(self._chunks):
            low = ch.lower()
            kw.append((sum(low.count(t) for t in terms), i))
        sem: dict[int, float] = {}
        if settings.memory_semantic_enabled:
            try:
                from jarvis.brain.semantic import INDEX

                items = [(str(i), 0.0, ch) for i, ch in enumerate(self._chunks)]
                raw = INDEX.scores(query, items)
                sem = {int(key): v for key, v in raw.items()}
            except Exception:  # noqa: BLE001 — semantic is optional; keyword still ranks
                sem = {}
        weight = settings.memory_semantic_weight
        scored = [(score + weight * sem.get(i, 0.0), i) for score, i in kw]
        scored = [(s, i) for s, i in scored if s > 0]
        scored.sort(reverse=True)
        return [self._chunks[i] for _, i in scored[:k]]

    def clear(self) -> str:
        had = self.source
        self.source, self._chunks = None, []
        return f"Closed '{had}', sir." if had else "There was no document open, sir."


STORE = DocStore()
