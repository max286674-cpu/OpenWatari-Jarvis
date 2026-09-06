"""Idempotent runtime guard repair.

Repairs only the two named regex definitions in agent.py. No broad slicing,
no function-boundary heuristics, and the resulting source is AST-checked.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src" / "jarvis" / "brain" / "agent.py"

PURE_CHAT = r'''_PURE_CHAT_RE = re.compile(
    r"^\s*(привет|здравствуй|здрасьте|доброе\s+утро|добрый\s+день|добрый\s+вечер|"
    r"спасибо|пожалуйста|класс|отлично|понял|понятно|хорошо|ага|угу|да|нет|почему|зачем|"
    r"что\s+такое|как\s+дела|как\s+ты|всё\s+хорошо|все\s+хорошо|"
    r"hi|hey+|hello|hiya|yo|howdy|greetings|thanks|thank\s+you|good\s+job|nice|great|cool|"
    r"got\s+it|okay|ok|never\s+mind|nevermind|bye|goodbye)"
    r"[\s,.!?]*(джарвис|jarvis|сэр|sir)?[\s,.!?]*$",
    re.IGNORECASE,
)
'''

# Deliberately narrow: system-wide destruction only. Ordinary file/folder deletion
# must remain available through the normal confirmation/protection layer.
CATASTROPHIC = r'''_CATASTROPHIC_RE = re.compile(
    r"(?:\b(?:delete|remove|wipe|erase|destroy|format|nuke|del|rm)\b[^.?!]*\b(?:"
    r"system32|c:\\?\s*windows|windows\s+(?:folder|directory)|system\s+drive|c[:\s]+drive|"
    r"boot\s+(?:partition|sector)|registry|program\s+files|"
    r"everything\s+(?:on|in)\s+(?:my|the)\s+(?:pc|computer|laptop|c\s*drive|system|hard\s*drive))\b"
    r"|\brm\s+-rf\s+/(?:\s|$|\*)|\bformat\s+c:|\bdel\s+/[fsq]\b[^.?!]*\bc:\\?\s*windows"
    r"|\b(?:удали|удалить|сотри|стереть|очисти|очистить|уничтожь|уничтожить|"
    r"форматируй|форматировать|снеси|снести)\b[^.?!]*\b(?:всё|все|весь|всю|"
    r"систему|windows|виндовс|диск\s*c:?|диска\s*c:?|system32|реестр|program\s+files)\b",
    re.IGNORECASE,
)
'''


def replace_named_block(text: str, name: str, replacement: str) -> str:
    # A re.compile definition ends with either ')' or '),' depending on formatting.
    pattern = re.compile(
        rf"(?ms)^{re.escape(name)}\s*=\s*re\.compile\(.*?^\)\s*,?\s*$",
    )
    if not pattern.search(text):
        raise RuntimeError(f"cannot find {name} definition in agent.py")
    return pattern.sub(lambda _: replacement.rstrip() + "\n", text, count=1)


def main() -> None:
    source = AGENT.read_text(encoding="utf-8")
    source = replace_named_block(source, "_PURE_CHAT_RE", PURE_CHAT)
    source = replace_named_block(source, "_CATASTROPHIC_RE", CATASTROPHIC)
    ast.parse(source, filename=str(AGENT))
    AGENT.write_text(source, encoding="utf-8")
    print("runtime guards repaired: Russian pure-chat + catastrophic guard")


if __name__ == "__main__":
    main()
