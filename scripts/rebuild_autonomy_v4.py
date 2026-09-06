"""One-shot autonomy repair for Windows JARVIS."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f"Pattern not found in {path}: {old[:100]!r}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")

# Russian commands must reach the native tool path rather than being answered as fake prose.
agent = ROOT / "src/jarvis/brain/agent.py"
patch(agent, [
    (
        'r"\\bremind me\\b", r"\\bset (a |an )?reminder\\b", r"\\bremember (that|to|my)\\b",',
        'r"\\bremind me\\b", r"\\bset (a |an )?reminder\\b", r"\\bremember (that|to|my)\\b",\n'
        '    r"\\b(открой|открыть|запусти|запустить|включи|включить|закрой|закрыть|выключи|выключить|останови|остановить)\\b",\n'
        '    r"\\b(нажми|кликни|кликнуть|введи|введите|напиши|напечатай|перейди|переключи|выбери|выбрать)\\b",\n'
        '    r"\\b(посмотри|покажи|сделай|выполни|сделать|выполнить)\\b.{0,80}\\b(экран|окно|компьютер|програм|файл|папк|браузер|сайт|телеграм|хром|ворд|эксель)\\b",'
    ),
    ('"delegate_to_fleet": "Right away, sir — putting that to the team lead",', '"delegate_to_fleet": "Сейчас сделаю, сэр — передаю задачу команде",'),
    ('"open_app": "Opening that",', '"open_app": "Открываю приложение",'),
    ('"process_op": "On it",', '"process_op": "Выполняю",'),
    ('"browser": "In the browser",', '"browser": "Работаю в браузере",'),
])

# Keep the mature proactive engine, but make local computer work frictionless.
proactive = ROOT / "src/jarvis/brain/proactive.py"
text = proactive.read_text(encoding="utf-8")
if "_AUTONOMY_CONFIRM_OVERRIDE" not in text:
    text += '''\n\n# AUTONOMY POLICY v4: only consequential/external/destructive actions confirm.\n_AUTONOMY_CONFIRM_OVERRIDE = {"process_op", "browser", "create_event"}\n_ORIGINAL_CONFIRM_REQUIRED_V4 = confirm_required\ndef confirm_required(tool_name: str, args: dict | None = None) -> bool:\n    name = (tool_name or "").strip()\n    if name in _AUTONOMY_CONFIRM_OVERRIDE:\n        return False\n    if name == "file_op":\n        action = str((args or {}).get("action", "")).lower()\n        return action.startswith("delete") or action in {"remove", "unlink", "rmdir"}\n    return _ORIGINAL_CONFIRM_REQUIRED_V4(name, args)\n'''
    proactive.write_text(text, encoding="utf-8")

# Russian screen verbs must load the screen/computer-use tool group.
tools = ROOT / "src/jarvis/brain/tools/__init__.py"
patch(tools, [
    (
        '"screen": ("screen","screenshot","display","look at my","on my screen","what am i looking",',
        '"screen": ("screen","screenshot","display","look at my","on my screen","what am i looking",'
        '"открой","открыть","запусти","запустить","нажми","кликни","введи","посмотри на экран",',
    ),
])

# Extend vision actions to include movement and drag, while keeping destructive/external actions out.
computer = ROOT / "src/jarvis/brain/tools/computer_use.py"
patch(computer, [
    ('_ACTIONS = {"click", "double_click", "right_click", "type", "press", "hotkey", "scroll", "done"}',
     '_ACTIONS = {"move", "click", "double_click", "right_click", "drag", "type", "press", "hotkey", "scroll", "done"}'),
    ('Return ONLY JSON, no markdown, with this schema:\n{"action":"click|double_click|right_click|type|press|hotkey|scroll|done", "x":0, "y":0,',
     'Return ONLY JSON, no markdown, with this schema:\n{"action":"move|click|double_click|right_click|drag|type|press|hotkey|scroll|done", "x":0, "y":0,'),
    (' "text":"", "key":"", "keys":["ctrl","s"], "amount":0, "reason":"brief"}',
     ' "x2":0, "y2":0, "text":"", "key":"", "keys":["ctrl","s"], "amount":0, "reason":"brief"}'),
    ('For click actions give pixel coordinates. For typing use text. For keyboard shortcuts use keys.',
     'For move/click actions give visible pixel coordinates. For drag give x,y and destination x2,y2. For typing use text. For keyboard shortcuts use keys.'),
    ('if name in {"click", "double_click", "right_click"}:',
     'if name == "move":\n        p.moveTo(int(action["x"]), int(action["y"]))\n    elif name in {"click", "double_click", "right_click"}:'),
    ('elif name == "type":',
     'elif name == "drag":\n        p.moveTo(int(action["x"]), int(action["y"]))\n        p.dragTo(int(action["x2"]), int(action["y2"]), duration=0.25, button="left")\n    elif name == "type":'),
])

for p in (agent, proactive, tools, computer):
    ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

print("JARVIS autonomy v4 applied.")
print("NO confirmation: normal local apps, browser navigation, calendar creation, file create/edit, GUI control.")
print("CONFIRMATION: external sends, destructive deletes, PowerShell, external writes and security-sensitive actions.")
print("Next: uv sync && uv run python scripts/rebuild_autonomy_v4.py && uv run pytest -q")
print("Then: uv run python -m jarvis.edge.assistant")
