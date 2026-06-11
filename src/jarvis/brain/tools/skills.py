"""Skills — on-demand know-how Jarvis can read when he needs it (Phase 13).

Skills are Markdown playbooks under ``skills/`` (coding discipline, his own architecture, the
self-improvement workflow, language notes…). They are **not** injected into the system prompt — that
would bloat every turn — so instead Jarvis pulls the relevant one with ``read_skill`` exactly when a
task calls for it, the way a developer opens the right doc. ``list_skills`` shows what's available.

Drop a new ``skills/<name>.md`` and it's instantly available — no code change.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.brain.tools.base import clip
from jarvis.config import settings

_SKILLS_DIR = Path(__file__).resolve().parents[4] / "skills"


def _skill_files() -> list[Path]:
    if not _SKILLS_DIR.is_dir():
        return []
    return sorted(_SKILLS_DIR.glob("*.md"))


def _title(p: Path) -> str:
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return p.stem


async def list_skills(args: dict) -> str:
    if not settings.skills_enabled:
        return "My skills library is switched off right now, sir."
    files = _skill_files()
    if not files:
        return "I don't have any skill playbooks yet, sir."
    items = [f"{p.stem} — {_title(p)}" for p in files]
    return f"I have {len(items)} skill playbook(s), sir: " + "; ".join(items)


async def read_skill(args: dict) -> str:
    if not settings.skills_enabled:
        return "My skills library is switched off right now, sir."
    name = (args.get("name") or "").strip().lower().removesuffix(".md")
    if not name:
        return "Which skill should I open, sir?"
    p = _SKILLS_DIR / f"{name}.md"
    if not p.is_file():
        # fuzzy: first skill whose stem contains the request
        match = next((f for f in _skill_files() if name in f.stem.lower()), None)
        if match is None:
            return f"I don't have a '{name}' skill, sir. Try list_skills."
        p = match
    try:
        return clip(p.read_text(encoding="utf-8", errors="ignore"), 6000)
    except OSError as e:
        return f"I couldn't open that skill, sir ({type(e).__name__})."


SCHEMAS = [
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "List your available skill playbooks (coding, self-improvement, your own "
                       "architecture, languages…). Use before a specialised task to see what guidance you have.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "Open one of your skill playbooks by name (e.g. 'self-improvement', 'python', "
                       "'jarvis-architecture'). Read the relevant one before editing your own code.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Skill name (filename stem)."}},
            "required": ["name"]}}},
]

HANDLERS = {"list_skills": list_skills, "read_skill": read_skill}
