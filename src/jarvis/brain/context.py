"""Build Jarvis's system prompt from his personality + markdown memory files.

Personality (`personality/jarvis.md`) is who he is; `memory/*.md` is what he knows about
Vazghen, his projects, environment, and the proactive-companion mandate. Both are plain
Markdown so they can be edited without touching code (and later synced from the vault).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

# repo root = .../src/jarvis/brain/context.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
PERSONALITY_PATH = _REPO_ROOT / "personality" / "jarvis.md"
MEMORY_DIR = _REPO_ROOT / "memory"

# Order matters: who he is, then who Vazghen is, then the rest. Missing files are skipped.
_MEMORY_ORDER = [
    "about-vazghen.md",
    "proactive-companion.md",
    "projects.md",
    "openclaw-fleet.md",
    "environment.md",
]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning(f"brain context: missing {p.name}")
        return ""


def load_memory_files() -> list[tuple[str, str]]:
    """Return (filename, content) for each memory file, ordered, missing ones skipped."""
    seen: set[str] = set()
    files: list[Path] = []
    for name in _MEMORY_ORDER:
        p = MEMORY_DIR / name
        if p.exists():
            files.append(p)
            seen.add(name)
    # include any other .md not in the explicit order (future additions)
    for p in sorted(MEMORY_DIR.glob("*.md")):
        if p.name not in seen:
            files.append(p)
    return [(p.name, _read(p)) for p in files]


def build_system_prompt() -> str:
    """Assemble the full system prompt: persona + memory, with clear section headers."""
    persona = _read(PERSONALITY_PATH)
    parts: list[str] = []
    if persona:
        parts.append(persona)
    mem_blocks = [f"## Memory — {name}\n\n{content}" for name, content in load_memory_files() if content]
    if mem_blocks:
        parts.append(
            "# Context you carry (long-term memory)\n\n"
            "Use this to ground your answers. Don't recite it; draw on it naturally.\n\n"
            + "\n\n".join(mem_blocks)
        )
    parts.append(
        "# Voice-output rules\n"
        "You are heard, not read. No markdown, no bullet points, no emoji, no code blocks. "
        "Keep replies to one or two spoken sentences unless asked for more. Numbers and dates "
        "spelled the way you'd say them aloud."
    )
    return "\n\n".join(parts)


if __name__ == "__main__":
    sp = build_system_prompt()
    print(sp)
    print(f"\n--- system prompt: {len(sp)} chars, ~{len(sp)//4} tokens ---")
