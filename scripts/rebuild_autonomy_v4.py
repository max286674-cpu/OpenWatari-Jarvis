"""One-shot autonomy repair for Windows JARVIS.

Repairs the two failure modes that make the assistant feel like it ignores commands:
- Russian imperative commands are forced into the tool path instead of being answered as prose.
- Routine local computer/browser/calendar/file-create work is never confirmation-gated.
Only consequential external/destructive actions remain gated.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f"Pattern not found in {path}: {old[:100]!r}")
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding="utf-8")


# Agent: force unambiguous Russian commands into native tool calling. Also make tool progress speech
# Russian so English filler is never sent to Russian TTS.
agent = ROOT / "src/jarvis/brain/agent.py"
patch(agent, [
    (
        'r"\\bremind me\\b", r"\\bset (a |an )?reminder\\b", r"\\bremember (that|to|my)\\b",',
        'r"\\bremind me\\b", r"\\bset (a |an )?reminder\\b", r"\\bremember (that|to|my)\\b",\n'
        '    r"\\b(открой|открыть|запусти|запустить|включи|включить|закрой|закрыть|выключи|выключить|останови|остановить)\\b",\n'
        '    r"\\b(нажми|кликни|кликнуть|введи|введите|напиши|напечатай|перейди|переключи|выбери|выбрать)\\b",\n'
        '    r"\\b(посмотри|покажи|сделай|выполни|сделать|выполнить)\\b.{0,80}\\b(экран|окно|компьютер|програм|файл|папк|браузер|сайт|телеграм|хром|ворд|эксель)\\b",'
    ),
    (
        '"delegate_to_fleet": "Right away, sir — putting that to the team lead",',
        '"delegate_to_fleet": "Сейчас сделаю, сэр — передаю задачу команде",',
    ),
    (
        '"open_app": "Opening that",',
        '"open_app": "Открываю приложение",',
    ),
    (
        '"process_op": "On it",',
        '"process_op": "Выполняю",',
    ),
    (
        '"browser": "In the browser",',
        '"browser": "Работаю в браузере",',
    ),
])

# The mature proactive module is loaded from the known-good revision. Keep that implementation but
# explicitly narrow confirmation to consequential actions. Routine local actions are frictionless.
proactive = ROOT / "src/jarvis/brain/proactive.py"
text = proactive.read_text(encoding="utf-8")
if "_AUTONOMY_CONFIRM_OVERRIDE" not in text:
    text += '''\n\n# AUTONOMY POLICY v4: confirmations are reserved for consequential actions.\n# Local computer control is intentionally frictionless: starting/stopping apps, browser navigation,\n# calendar creation, file creation/editing, screenshots, typing and UI actions do not ask.\n_AUTONOMY_CONFIRM_OVERRIDE = {\n    "process_op", "browser", "create_event",\n}\n_ORIGINAL_CONFIRM_REQUIRED_V4 = confirm_required\ndef confirm_required(tool_name: str, args: dict | None = None) -> bool:\n    name = (tool_name or "").strip()\n    if name in _AUTONOMY_CONFIRM_OVERRIDE:\n        return False\n    if name == "file_op":\n        action = str((args or {}).get("action", "")).lower()\n        # create/read/list/write/edit/move/copy are routine; deletion remains gated.\n        return action.startswith("delete") or action in {"remove", "unlink", "rmdir"}\n    return _ORIGINAL_CONFIRM_REQUIRED_V4(name, args)\n'''
    proactive.write_text(text, encoding="utf-8")

# Add a direct Russian screen trigger to the lazy screen group; this prevents the router from omitting
# computer_use when the owner gives a short Russian GUI command.
tools = ROOT / "src/jarvis/brain/tools/__init__.py"
patch(tools, [
    (
        '"screen": ("screen","screenshot","display","look at my","on my screen","what am i looking",',
        '"screen": ("screen","screenshot","display","look at my","on my screen","what am i looking",'
        '"открой","открыть","запусти","запустить","нажми","кликни","введи","посмотри на экран",',
    ),
])

# Static syntax validation; no network/API calls.
import ast
for p in (agent, proactive, tools, ROOT / "src/jarvis/brain/tools/computer_use.py"):
    ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

print("JARVIS autonomy v4 applied.")
print("Routine local computer/browser/calendar/file work: NO confirmation.")
print("Consequential sends, destructive deletes, PowerShell, external writes: confirmation retained.")
print("Next: uv sync && uv run pytest -q")
print("Then: uv run python -m jarvis.edge.assistant")
