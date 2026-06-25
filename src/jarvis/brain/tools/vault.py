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

import re
from datetime import datetime
from pathlib import Path

from jarvis.brain.tools.base import clip, not_configured, tool_error
from jarvis.config import settings

# Filenames/folders are sanitised to a safe set so a voice-dictated note title can't escape the
# vault or create odd paths.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.\-]+")


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


async def write_vault(args: dict) -> str:
    """Save a note INTO the vault (append by default, or create). Only on the authoritative host.

    This is how Watari keeps the knowledge base alive himself — capturing a decision, a fact worth
    keeping, or a session note. It's a no-op with a spoken explanation when the host isn't the vault
    owner (JARVIS_VAULT_WRITABLE), so it can never clobber the laptop's one-way-synced mirror.
    """
    if not settings.vault_writable:
        return ("Vault writing is off here, sir — it's only enabled on the host that owns the "
                "vault. Set JARVIS_VAULT_WRITABLE=true there and I can save notes into it.")
    root = _vault_root()
    if root is None:
        return not_configured("the Obsidian vault", "JARVIS_VAULT_PATH set to the vault folder")
    content = (args.get("content") or "").strip()
    if not content:
        return "There's nothing to write, sir — give me the note content."
    note = (args.get("note") or args.get("title") or "").strip()
    folder = _SAFE_NAME.sub("", (args.get("folder") or "Watari").replace("/", " ")).strip() or "Watari"
    mode = (args.get("mode") or "append").strip().lower()
    stem = _SAFE_NAME.sub("", note).strip() or datetime.now().strftime("%Y-%m-%d note")
    if not stem.lower().endswith(".md"):
        stem += ".md"
    try:
        rootr = root.resolve()
        target = (rootr / folder / stem).resolve()
        # Stay inside the vault — no path traversal out of it.
        if rootr != target and rootr not in target.parents:
            return "That path is outside the vault, sir — I won't write it."
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        if mode == "create" or not target.exists():
            target.write_text(f"# {note or stem[:-3]}\n\n{content}\n", encoding="utf-8")
            action = "created"
        else:
            with target.open("a", encoding="utf-8") as f:
                f.write(f"\n\n## {stamp}\n{content}\n")
            action = "added to"
        return f"Done, sir — {action} the vault note {target.relative_to(rootr).as_posix()}."
    except Exception as e:  # noqa: BLE001
        return tool_error("vault write", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": (
                "Search the owner's Obsidian knowledge vault (his notes, project charters, "
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
    {
        "type": "function",
        "function": {
            "name": "write_vault",
            "description": (
                "Save a note INTO the owner's Obsidian vault — append to (default) or create a note. "
                "Use to record a decision, a durable fact, or a session summary worth keeping in "
                "the knowledge base. Only works on the host that owns the vault."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string",
                             "description": "Note title / filename (without .md)."},
                    "content": {"type": "string", "description": "The text to write."},
                    "mode": {"type": "string", "enum": ["append", "create"],
                             "description": "append (default) or create a fresh note."},
                    "folder": {"type": "string",
                               "description": "Vault subfolder (default 'Watari')."},
                },
                "required": ["content"],
            },
        },
    },
]

HANDLERS = {"search_vault": search_vault, "read_vault_note": read_vault_note,
            "write_vault": write_vault}
