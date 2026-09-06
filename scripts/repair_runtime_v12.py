"""Idempotent runtime guard repair.

Unlike the old v11 patcher this script never slices agent.py by function boundaries.
It replaces only the two named regex definitions, preserving every other symbol.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src/jarvis/brain/agent.py"

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

CATASTROPHIC = r'''_CATASTROPHIC_RE = re.compile(
    r"(?:\b(?:delete|remove|wipe|erase|destroy|format|nuke|del|rm)\b[^.?!]*\b(?:"
    r"system32|c:\\?\s*windows|windows\s+(?:folder|directory)|system\s+drive|c[:\s]+drive|"
    r"boot\s+(?:partition|sector)|registry|program\s+files|"
    r"everything\s+(?:on|in)\s+(?:my|the)\s+(?:pc|computer|laptop|c\s*drive|system|hard\s*drive))\b)"
    r"|\brm\s+-rf\s+/(?:\s|$|\*)|\bformat\s+c:|\bdel\s+/[fsq]\b[^.?!]*\bc:\\?\s*windows"
    r"|(?:удали|удалить|сотри|стереть|очисти|очистить|уничтожь|уничтожить|форматируй|форматировать|"
    r"снеси|снести)\b[^.?!]*(?:всё|все|весь|всю|систему|windows|виндовс|диск\s*c|диска\s*c|"
    r"диск\s*c:|диска\s*c:|system32|реестр|program\s+files)\b)",
    re.IGNORECASE,
)
'''


def replace_named_block(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?ms)^{re.escape(name)}\s*=\s*re\.compile\(.*?^\)\n",
    )
    if not pattern.search(text):
        raise RuntimeError(f"cannot find {name} definition in agent.py")
    return pattern.sub(lambda _: replacement + "\n", text, count=1)


def main() -> None:
    s = AGENT.read_text(encoding="utf-8")
    s = replace_named_block(s, "_PURE_CHAT_RE", PURE_CHAT)
    s = replace_named_block(s, "_CATASTROPHIC_RE", CATASTROPHIC)
    ast.parse(s, filename=str(AGENT))
    AGENT.write_text(s, encoding="utf-8")
    print("runtime guards repaired: Russian pure-chat + catastrophic guard")


if __name__ == "__main__":
    main()
