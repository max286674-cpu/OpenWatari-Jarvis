"""Build the assistant's system prompt from its personality + markdown memory files.

The persona file (``personality/<JARVIS_PERSONA_FILE>``, default jarvis.md) is a TEMPLATE for who it
is — identity tokens are filled from config (see ``_apply_identity``). ``memory/*.md`` is the user's
profile (who they are, projects, environment) + the proactive mandate; personal profile files are
gitignored and fall back to shipped ``*.example.md`` templates. All plain Markdown, editable without
touching code.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from jarvis.config import settings

# repo root = .../src/jarvis/brain/context.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
PERSONALITY_DIR = _REPO_ROOT / "personality"
MEMORY_DIR = _REPO_ROOT / "memory"


def _persona_path() -> Path:
    """The persona template file (configurable via JARVIS_PERSONA_FILE)."""
    return PERSONALITY_DIR / (settings.persona_file or "jarvis.md")


def _identity_tokens() -> dict[str, str]:
    """Fill-ins that turn the generic persona TEMPLATE into THIS user's assistant (framework layer).

    The persona file uses ``{assistant_name}``, ``{owner_possessive}``, ``{address_line}`` and
    ``{language_line}``; everything personal comes from config (.env / the setup wizard), so the
    same shipped persona becomes anyone's assistant without editing prompts or code.
    """
    s = settings
    name = (s.user_name or "").strip()
    addr = (s.user_address or "").strip()
    ref = name or addr or "you"
    owner_possessive = f"{name}'s" if name else "your"
    if addr and name:
        address_line = f'Address {name} as "{addr}".'
    elif addr:
        address_line = f'Address them as "{addr}".'
    elif name:
        address_line = f"Address them as {name}."
    else:
        address_line = "Address them naturally, without honorifics."
    understood = (s.understood_languages or "English").strip()
    reply = (s.reply_language or "English").strip()
    if understood.lower() != reply.lower():
        language_line = (f"They may speak {understood} — understand any of them, but **always reply "
                         f"in {reply}**. Never switch languages even if they do.")
    else:
        language_line = f"Speak and understand {reply}."
    return {
        "{assistant_name}": s.assistant_name or "Watari",
        "{owner_possessive}": owner_possessive,
        "{address_line}": address_line,
        "{language_line}": language_line,
        "{user_ref}": ref,
    }


def _apply_identity(text: str) -> str:
    for token, value in _identity_tokens().items():
        text = text.replace(token, value)
    return text

# Always-on context: injected into EVERY turn, so it is kept deliberately lean (see
# fine-tuning.md, Item 1). Order matters: who Vazghen is, the proactive mandate, his ventures,
# then the environment. Two files are intentionally NOT here:
#   * tools.md       — duplicated the tool schemas the model already receives every turn.
#   * openclaw-fleet.md — its actionable rule (delegate to ispir only) is already in the persona.
# Both stay on disk as on-demand reference (readable via read_source / the vault), they're just
# not paid for on every turn. Files are loaded ONLY if listed here (no glob) to keep the prompt
# disciplined — a new memory file must be added explicitly and weighed against the token budget.
_ALWAYS_ON = [
    "about-you.md",
    "proactive-companion.md",
    "projects.md",
]
# Demoted to on-demand reference (kept on disk, not injected every turn): environment.md (ports/
# paths the brain reads from config, not the prompt), plus tools.md and openclaw-fleet.md.


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning(f"brain context: missing {p.name}")
        return ""


def _resolve_memory(name: str) -> Path | None:
    """Prefer the user's private profile file; fall back to the shipped ``.example`` template.

    Personal profile files (about-you.md, projects.md, …) are gitignored — a fresh clone only has
    the ``*.example.md`` templates, so the assistant still boots with generic context until the user
    fills in (or the setup wizard copies) their own.
    """
    real = MEMORY_DIR / name
    if real.exists():
        return real
    example = MEMORY_DIR / name.replace(".md", ".example.md")
    return example if example.exists() else None


def load_memory_files() -> list[tuple[str, str]]:
    """Return (filename, content) for each ALWAYS-ON memory file, in order, missing ones skipped.

    Only files in ``_ALWAYS_ON`` are loaded — other ``memory/*.md`` are on-demand reference and
    deliberately excluded from the per-turn prompt (see ``_ALWAYS_ON`` note above). Each resolves to
    the user's private file if present, else the shipped ``.example`` template.
    """
    out: list[tuple[str, str]] = []
    for name in _ALWAYS_ON:
        p = _resolve_memory(name)
        if p is not None:
            out.append((name, _read(p)))
    return out


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


def _vault_reachable(p: Path) -> bool:
    """True only if the path is a directory we can actually list (not a cloud placeholder)."""
    try:
        if not p.is_dir():
            return False
        next(p.iterdir(), None)  # touch it — proves read access, not just existence
        return True
    except OSError:
        return False


def validate_vault(retries: int = 3, grace: float = 0.4) -> tuple[bool, str]:
    """L3 must always be readable. Returns (ok, message) and logs loudly if not.

    A momentary blip — the 15-min vault sync's delete→move window, an antivirus lock, or a
    OneDrive 'online-only' placeholder rehydrating — must NOT fire the 'I've lost your vault'
    alarm. So we retry with a short grace; only a *sustained* failure is reported as lost access.
    """
    import time

    if not settings.vault_path:
        msg = "Obsidian vault (L3) is NOT configured — set JARVIS_VAULT_PATH to the local mirror."
        logger.warning(msg)
        return False, msg
    p = Path(settings.vault_path)
    for attempt in range(retries):
        if _vault_reachable(p):
            n = sum(1 for _ in p.rglob("*.md"))
            logger.info(f"Obsidian vault (L3) ready: {n} notes at {p}")
            return True, f"vault ready ({n} notes)"
        if attempt < retries - 1:
            time.sleep(grace)  # transient? give the sync/placeholder a moment to settle
    msg = f"Obsidian vault path '{settings.vault_path}' is not a readable folder."
    logger.warning(msg)
    return False, msg


def build_system_prompt() -> str:
    """Assemble the full system prompt: persona + memory, with clear section headers."""
    persona = _apply_identity(_read(_persona_path()))
    parts: list[str] = []
    if persona:
        parts.append(persona)
    mem_blocks = [f"## {name}\n{content}" for name, content in load_memory_files() if content]
    if mem_blocks:
        parts.append(
            "# Context you carry (draw on it naturally; don't recite it)\n\n"
            + "\n\n".join(mem_blocks)
        )
    digest = _learned_digest()
    if digest:
        who = (settings.user_name or "the user").strip()
        parts.append(
            f"# Recently learned about {who} (use `recall` for older)\n" + digest
        )
    # Operating rules (persona covers the rest — kept terse to spare per-turn tokens).
    parts.append(
        "# Clarify, confirm, speak\n"
        "If a request is too thin to act on safely (a bare 'do it', an unclear target), ask one "
        "short clarifying question first. Confirm before anything outward-facing or hard to undo "
        "(send/delete/kill/PowerShell/calendar write/lock/protocol); reads and lookups need none. "
        "Output is spoken: no markdown or emoji, one or two sentences unless asked for more, numbers "
        "and dates said the way you'd speak them. If you ever speak unprompted, lead with why."
    )
    return "\n\n".join(parts)


if __name__ == "__main__":
    sp = build_system_prompt()
    print(sp)
    print(f"\n--- system prompt: {len(sp)} chars, ~{len(sp)//4} tokens ---")
