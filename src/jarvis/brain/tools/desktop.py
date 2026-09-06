"""Windows desktop control for the Computer Agent.

All GUI operations are local to the Windows display host. Imports are lazy so a headless VPS brain can
still start. The agent is expected to observe the screen, act, then verify with another observation.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from jarvis.brain.tools.base import clip, tool_error


def _enabled() -> bool:
    from jarvis.config import settings
    return bool(getattr(settings, "desktop_tools_enabled", True))


def _gui():
    if sys.platform != "win32":
        raise RuntimeError("desktop control requires the Windows display host")
    import pyautogui
    pyautogui.PAUSE = 0.03
    pyautogui.FAILSAFE = True
    return pyautogui


async def desktop_action(args: dict) -> str:
    if not _enabled():
        return "Управление экраном отключено."
    try:
        p = _gui()
        action = str(args.get("action") or "").lower().strip()
        if action == "click":
            p.click(int(args["x"]), int(args["y"]))
        elif action == "double_click":
            p.doubleClick(int(args["x"]), int(args["y"]))
        elif action == "right_click":
            p.rightClick(int(args["x"]), int(args["y"]))
        elif action == "move":
            p.moveTo(int(args["x"]), int(args["y"]), duration=.12)
        elif action == "type":
            text = str(args.get("text") or "")
            if len(text) > 10000:
                return "Текст слишком длинный для одного ввода."
            # pyautogui.write cannot reliably type Cyrillic. Clipboard paste handles Unicode on Windows.
            if sys.platform == "win32":
                import pyperclip
                pyperclip.copy(text)
                p.hotkey("ctrl", "v")
            else:
                p.write(text, interval=.01)
        elif action == "hotkey":
            keys = args.get("keys") or []
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.replace(",", "+").split("+") if k.strip()]
            if not 1 <= len(keys) <= 6:
                return "Некорректная комбинация клавиш."
            p.hotkey(*keys)
        elif action == "press":
            p.press(str(args.get("key") or "enter"))
        elif action == "scroll":
            p.scroll(max(-20, min(20, int(args.get("amount") or 0))))
        elif action == "drag":
            p.moveTo(int(args["x"]), int(args["y"]), duration=.1)
            p.dragTo(int(args["x2"]), int(args["y2"]), duration=.25, button="left")
        else:
            return f"Неизвестное действие на экране: {action}"
        return f"Выполнено действие на экране: {action}."
    except Exception as e:
        return tool_error("desktop control", e)


async def desktop_screenshot(_: dict) -> str:
    if not _enabled():
        return "Управление экраном отключено."
    try:
        p = _gui()
        shot = await asyncio.to_thread(p.screenshot)
        path = os.path.join(__import__("tempfile").gettempdir(), "jarvis_desktop.png")
        await asyncio.to_thread(shot.save, path)
        return json.dumps({"path": path, "width": shot.width, "height": shot.height})
    except Exception as e:
        return tool_error("screenshot", e)


async def active_window(_: dict) -> str:
    try:
        p = _gui()
        title = await asyncio.to_thread(p.getActiveWindowTitle)
        return f"Активное окно: {clip(title or 'без заголовка', 240)}."
    except Exception as e:
        return tool_error("active window", e)


SCHEMAS = [
    {"type":"function","function":{"name":"desktop_action","description":"Управлять мышью и клавиатурой Windows. Используй после наблюдения за экраном; действие не требует подтверждения.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["click","double_click","right_click","move","type","hotkey","press","scroll","drag"]},"x":{"type":"integer"},"y":{"type":"integer"},"x2":{"type":"integer"},"y2":{"type":"integer"},"text":{"type":"string"},"keys":{"type":"array","items":{"type":"string"}},"key":{"type":"string"},"amount":{"type":"integer"}},"required":["action"]}}},
    {"type":"function","function":{"name":"desktop_screenshot","description":"Capture the current Windows desktop for visual inspection and verification.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"active_window","description":"Return the current foreground window title.","parameters":{"type":"object","properties":{},"required":[]}}},
]

HANDLERS = {"desktop_action": desktop_action, "desktop_screenshot": desktop_screenshot, "active_window": active_window}
