"""One-shot local rebuild for the Windows voice runtime.

This intentionally reuses the last known-good proactive.py from the repository history, then makes
only the small policy changes needed for the owner's requested UX. It also repairs the still-English
agent affirmation regex because some tests and non-edge callers use it directly.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "jarvis"
KNOWN_GOOD_PROACTIVE = "273770dc4558258aae818be9f227ccde83e5ffe3"


def run(*args: str) -> str:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def restore_proactive() -> None:
    # The immediately previous remote patch accidentally replaced the mature proactive engine with
    # a shortened policy-only file. Restore the complete known-good implementation from git history.
    run("git", "checkout", KNOWN_GOOD_PROACTIVE, "--", "src/jarvis/brain/proactive.py")
    p = SRC / "brain" / "proactive.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        '    "send_telegram", "send_email", "send_push",\n    "file_op", "process_op", "run_powershell", "browser",\n    "run_protocol", "ha_call",\n    "create_event",',
        '    "send_telegram", "send_email", "send_push",\n    "file_op", "run_powershell",\n    "run_protocol", "ha_call",',
    )
    text = text.replace(
        '    "notion_append", "notion_comment", "notion_create_page",',
        '    "notion_append", "notion_comment", "notion_create_page",',
    )
    text = text.replace(
        '    if name == "process_op":\n        return (args or {}).get("action") in {"kill", "start"}\n',
        '',
    )
    text = text.replace(
        '_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they"}',
        '_PRONOUN_ONLY = {"it", "that", "this", "them", "those", "these", "him", "her", "they", "это", "то", "его", "её", "ее", "их"}',
    )
    p.write_text(text, encoding="utf-8")


def patch_agent() -> None:
    p = SRC / "brain" / "agent.py"
    text = p.read_text(encoding="utf-8")
    old = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|разрешаю|"\n    r"делай|выполняй|продолжай|вперёд|вперед|давай|можно|согласен|согласна|"\n    r"yes|yeah|yep|sure|ok|okay|go ahead|do it|please do|confirm|confirmed|proceed)\\s*[.!?]*$",\n    re.IGNORECASE,\n)'''
    if old not in text:
        # Accept a previously repaired variant and replace the whole block conservatively.
        text, n = re.subn(r'_AFFIRM_RE = re\.compile\(.*?\n\)\n\n\ndef _is_affirmation', new + '\n\n\ndef _is_affirmation', text, count=1, flags=re.S)
        if n != 1:
            raise RuntimeError("Could not locate _AFFIRM_RE in agent.py")
    else:
        text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")


def patch_config() -> None:
    p = SRC / "config.py"
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^\s*ack_before_tools:\s*bool\s*=\s*True\s*$', '    ack_before_tools: bool = False', text)
    p.write_text(text, encoding="utf-8")


def validate() -> None:
    files = [
        SRC / "brain" / "agent.py",
        SRC / "brain" / "proactive.py",
        SRC / "brain" / "computer_direct.py",
        SRC / "brain" / "tools" / "computer_use.py",
        SRC / "edge" / "brain_bridge.py",
        SRC / "config.py",
    ]
    for p in files:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    from jarvis.brain.proactive import confirm_required
    assert confirm_required("process_op", {"action": "kill"}) is False
    assert confirm_required("process_op", {"action": "start"}) is False
    assert confirm_required("browser", {}) is False
    assert confirm_required("file_op", {"action": "delete_file"}) is True
    assert confirm_required("file_op", {"action": "create_file"}) is False
    print("AST + confirmation policy validation: OK")


def main() -> None:
    restore_proactive()
    patch_agent()
    patch_config()
    validate()
    print("JARVIS rebuild v3 applied.")
    print("Run: uv run pytest -q")
    print("Then: uv run python -m jarvis.edge.assistant")


if __name__ == "__main__":
    main()
