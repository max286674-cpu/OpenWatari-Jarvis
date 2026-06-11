"""Build Jarvis's system prompt from his personality + markdown memory files.

Personality (`personality/jarvis.md`) is who he is; `memory/*.md` is what he knows about
Vazghen, his projects, environment, and the proactive-companion mandate. Both are plain
Markdown so they can be edited without touching code (and later synced from the vault).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from jarvis.config import settings

# repo root = .../src/jarvis/brain/context.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
PERSONALITY_PATH = _REPO_ROOT / "personality" / "jarvis.md"
MEMORY_DIR = _REPO_ROOT / "memory"

# Order matters: who he is, then who Vazghen is, then the rest. Missing files are skipped.
_MEMORY_ORDER = [
    "about-vazghen.md",
    "proactive-companion.md",
    "projects.md",
    "tools.md",
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


def _learned_digest() -> str:
    """Recent learned facts (L1) as a short bullet list for the system prompt."""
    if not settings.memory_enabled:
        return ""
    try:
        from jarvis.brain.memory import STORE

        facts = STORE.recent_digest(settings.memory_digest_max)
        return "\n".join(f"- {f}" for f in facts)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"learned-memory digest unavailable: {e}")
        return ""


def validate_vault() -> tuple[bool, str]:
    """L3 must always be readable. Returns (ok, message) and logs loudly if not."""
    if not settings.vault_path:
        msg = "Obsidian vault (L3) is NOT configured — set JARVIS_VAULT_PATH to the local mirror."
        logger.warning(msg)
        return False, msg
    p = Path(settings.vault_path)
    if not p.is_dir():
        msg = f"Obsidian vault path '{settings.vault_path}' is not a readable folder."
        logger.warning(msg)
        return False, msg
    n = sum(1 for _ in p.rglob("*.md"))
    logger.info(f"Obsidian vault (L3) ready: {n} notes at {p}")
    return True, f"vault ready ({n} notes)"


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
    digest = _learned_digest()
    if digest:
        parts.append(
            "# What you've learned about Vazghen (recent)\n\n"
            "Things you saved in past conversations. Use the `recall` tool for anything older.\n\n"
            + digest
        )
    parts.append(
        "# Acting proactively, clarifying, and confirming\n"
        "When a request is too thin to act on safely — a bare 'do it', an unclear target — ask one "
        "short clarifying question before guessing. Before anything outward-facing or hard to undo "
        "(sending an email or message, deleting files, killing processes, running PowerShell, "
        "creating a calendar event, operating a lock or device, running a protocol), state what "
        "you're about to do and get a yes first. Reads and lookups need no confirmation — just do "
        "them. If you ever speak unprompted, lead with why in a few words, then stop."
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
