"""Compatibility loader for the mature proactive engine.

The complete implementation is restored by scripts/rebuild_jarvis_v3.py from the known-good git
revision. This loader prevents the accidental shortened policy patch from breaking imports between
git pull and the rebuild command.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_KNOWN_GOOD = "273770dc4558258aae818be9f227ccde83e5ffe3"
_ROOT = Path(__file__).resolve().parents[3]
_PATH = "src/jarvis/brain/proactive.py"

try:
    _source = subprocess.check_output(
        ["git", "show", f"{_KNOWN_GOOD}:{_PATH}"], cwd=_ROOT, text=True, encoding="utf-8"
    )
except Exception as exc:
    raise RuntimeError(
        "Jarvis proactive engine could not load its known-good implementation. "
        "Run scripts/rebuild_jarvis_v3.py from the repository root."
    ) from exc

exec(compile(_source, str(_ROOT / _PATH), "exec"), globals(), globals())

# Routine local actions do not need a confirmation prompt. Keep only consequential/external/destructive
# actions behind the gate. The rebuild script writes this policy into the real source permanently.
_ORIGINAL_CONFIRM_REQUIRED = confirm_required

def confirm_required(tool_name: str, args: dict | None = None) -> bool:
    name = (tool_name or "").strip()
    if name in {"process_op", "browser", "create_event"}:
        return False
    return _ORIGINAL_CONFIRM_REQUIRED(name, args)
