"""Repair only the catastrophic regex in agent.py.

This version avoids regex-based source replacement entirely: it locates the named
assignment by plain text and replaces it up to _CATASTROPHIC_REFUSAL.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src" / "jarvis" / "brain" / "agent.py"

BLOCK = '''_CATASTROPHIC_RE = re.compile(
    r"(?:"
    r"\\b(?:delete|remove|wipe|erase|destroy|format|nuke|del|rm)\\b[^.?!]*\\b(?:"
    r"system32|c:\\\\?\\s*windows|windows\\s+(?:folder|directory)|system\\s+drive|"
    r"c[:\\s]+drive|boot\\s+(?:partition|sector)|registry|program\\s+files|"
    r"everything\\s+(?:on|in)\\s+(?:my|the)\\s+(?:pc|computer|laptop|c\\s*drive|system|hard\\s*drive)"
    r")\\b"
    r"|\\brm\\s+-rf\\s+/(?:\\s|$|\\*)"
    r"|\\bformat\\s+c:"
    r"|\\bdel\\s+/[fsq]\\b[^.?!]*\\bc:\\\\?\\s*windows"
    r"|(?:удали|удалить|сотри|стереть|очисти|очистить|уничтожь|уничтожить|форматируй|форматировать|снеси|снести)\\b"
    r"[^.?!]*(?:всё|все|весь|всю|систему|windows|виндовс|диск\\s*c:?|диска\\s*c:?|system32|реестр|program\\s+files)\\b"
    r")",
    re.IGNORECASE,
)
'''


def main() -> None:
    s = AGENT.read_text(encoding="utf-8")
    start = s.find("_CATASTROPHIC_RE = re.compile(")
    marker = "_CATASTROPHIC_REFUSAL ="
    end = s.find(marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("Could not locate catastrophic guard block")
    s = s[:start] + BLOCK + "\n" + s[end:]
    ast.parse(s, filename=str(AGENT))
    AGENT.write_text(s, encoding="utf-8")
    print("catastrophic guard repaired and syntax-checked")


if __name__ == "__main__":
    main()
