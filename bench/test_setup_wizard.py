"""Setup wizard — the pure, non-interactive bits that turn a clone into someone's own assistant.

Covers: identity keys render into .env, secret values are masked (never shown), and profile/persona
seeding copies a template only when the user's private file is absent (never clobbers).

    uv run python bench/test_setup_wizard.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  XX  {name}  {detail}")


def main() -> None:
    from jarvis import setup_wizard as w

    # render_env swaps only the keys we collected, preserving every other template line + comment.
    template = (
        "# header comment\n"
        "JARVIS_ASSISTANT_NAME=Watari\n"
        "JARVIS_USER_NAME=\n"
        "JARVIS_USER_ADDRESS=\n"
        "JARVIS_UNTOUCHED=keepme   # inline comment\n"
    )
    out = w.render_env(template, {
        "JARVIS_ASSISTANT_NAME": "Aria",
        "JARVIS_USER_NAME": "Dana",
        "JARVIS_USER_ADDRESS": "ma'am",
    })
    check("identity name rendered", "JARVIS_ASSISTANT_NAME=Aria" in out)
    check("identity user rendered", "JARVIS_USER_NAME=Dana" in out)
    check("identity address rendered", "JARVIS_USER_ADDRESS=ma'am" in out)
    check("untouched line preserved verbatim", "JARVIS_UNTOUCHED=keepme   # inline comment" in out)
    check("header comment preserved", "# header comment" in out)

    # mask never reveals a secret in full.
    m = w.mask("supersecrettoken12345")
    check("mask hides the middle of a secret", "supersecrettoken12345" not in m and "..." in m)
    check("blank masks to (blank)", w.mask("") == "(blank)")

    # seed_if_missing copies a template only when the target is absent, and never clobbers.
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "about.example.md"
        dst = Path(d) / "about.md"
        src.write_text("TEMPLATE BODY", encoding="utf-8")
        check("seeds when target missing", w.seed_if_missing(src, dst) is True)
        check("seeded content copied", dst.read_text(encoding="utf-8") == "TEMPLATE BODY")
        dst.write_text("USER EDITED", encoding="utf-8")
        check("does NOT clobber an existing file", w.seed_if_missing(src, dst) is False)
        check("user content preserved", dst.read_text(encoding="utf-8") == "USER EDITED")
        missing = Path(d) / "nope.example.md"
        check("no-op when source missing", w.seed_if_missing(missing, Path(d) / "x.md") is False)

    # The shipped templates the wizard seeds from actually exist.
    check("persona.example.md ships", w.PERSONA_EXAMPLE.exists())
    for src, _ in w.PROFILE_SEEDS:
        check(f"{src} ships", (w.MEMORY_DIR / src).exists())

    print(f"\n=== {PASS}/{PASS + FAIL} checks passed ===")
    raise SystemExit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
