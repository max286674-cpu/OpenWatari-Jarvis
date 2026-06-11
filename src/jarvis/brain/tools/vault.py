"""Obsidian vault tools — READ/SEARCH the canonical knowledge base.

Reads the LOCAL mirror at ``settings.vault_path`` (the VPS-authoritative one-way sync target,
e.g. ``C:\\Users\\iamva\\Documents\\Obsidian Vault``). Writes are deliberately NOT offered:
the vault is a one-way VPS->local sync that nukes-and-replaces each local dir, so any local
write would be clobbered. When Jarvis needs to change the vault he delegates that to the
fleet (ispir), which writes on the VPS.

Pure local filesystem — no credentials, works fully offline. Search is a lightweight
filename+content scorer (good enough for "find the rabbit-farm charter" voice queries).
"""

from __future__ import annotations

from pathlib import Path

from jarvis.brain.tools.base import clip, not_configured, tool_error
from jarvis.config import settings


def _vault_root() -> Path | None:
    if not settings.vault_path:
        return None
    p = Path(settings.vault_path)
    return p if p.is_dir() else None


def _score(query: str, name: str, body: str) -> int:
    q = query.lower()
    terms = [t for t in q.replace("-", " ").split() if t]
    score = 0
    nlow = name.lower()
    if q in nlow:
        score += 50
    for t in terms:
        if t in nlow:
            score += 10
        score += body.lower().count(t)
    return score


def _snippet(body: str, query: str, width: int = 200) -> str:
    low = body.lower()
    terms = [t for t in query.lower().replace("-", " ").split() if t]
    idx = next((low.find(t) for t in terms if low.find(t) >= 0), -1)
    if idx < 0:
        return clip(body, width)
    start = max(0, idx - width // 3)
    return clip(body[start : start + width], width)


async def search_vault(args: dict) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "I need something to search the vault for, sir."
    root = _vault_root()
    if root is None:
        return not_configured("the Obsidian vault", "JARVIS_VAULT_PATH set to the vault folder")
    try:
        hits: list[tuple[int, Path, str]] = []
        for p in root.rglob("*.md"):
            try:
                body = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            s = _score(query, p.stem, body)
            if s > 0:
                hits.append((s, p, body))
        hits.sort(key=lambda h: h[0], reverse=True)
        if not hits:
            return f"Nothing in the vault matched '{query}', sir."
        top = hits[: settings.vault_search_max_results]
        lines = []
        for _, p, body in top:
            rel = p.relative_to(root).as_posix()
            lines.append(f"[{rel}] {_snippet(body, query)}")
        return f"Found {len(hits)} vault note(s) matching '{query}'. Top results:\n" + "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return tool_error("vault search", e)


async def read_vault_note(args: dict) -> str:
    rel = (args.get("path") or "").strip()
    if not rel:
        return "Which note should I read, sir? Give me a path or search first."
    root = _vault_root()
    if root is None:
        return not_configured("the Obsidian vault", "JARVIS_VAULT_PATH set to the vault folder")
    try:
        target = (root / rel).resolve()
        # Stay inside the vault — no path traversal.
        if root.resolve() not in target.parents and target != root.resolve():
            return "That path is outside the vault, sir — I won't read it."
        if not target.is_file():
            return f"I couldn't find a note at '{rel}', sir."
        body = target.read_text(encoding="utf-8", errors="ignore")
        return f"{rel}:\n{clip(body, settings.vault_read_max_chars)}"
    except Exception as e:  # noqa: BLE001
        return tool_error("vault read", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": (
                "Search Vazghen's Obsidian knowledge vault (his notes, project charters, "
                "agent docs, decisions) for a topic and get the top matching notes with "
                "snippets. Use for 'search my vault/notes for X' or to ground an answer in "
                "his own documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search the vault for."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_vault_note",
            "description": (
                "Read the full text of a specific vault note by its relative path (as returned "
                "by search_vault, e.g. '30-Projects/lpstrak-rabbit-farm/CHARTER.md')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Vault-relative path to the note."}
                },
                "required": ["path"],
            },
        },
    },
]

HANDLERS = {"search_vault": search_vault, "read_vault_note": read_vault_note}
