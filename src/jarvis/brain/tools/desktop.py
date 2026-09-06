"""Windows desktop control: mouse, keyboard and GUI fallback actions."""
from __future__ import annotations
from jarvis.brain.tools.base import tool_error

def _enabled() -> bool:
    from jarvis.config import settings
    return bool(getattr(settings, "desktop_tools_enabled", False))

async def desktop_action(args: dict) -> str:
    if not _enabled(): return "Управление экраном отключено. Включи JARVIS_DESKTOP_TOOLS_ENABLED=true."
    try:
        import pyautogui
        action=str(args.get("action") or "").lower().strip()
        if action=="click": pyautogui.click(int(args["x"]),int(args["y"]))
        elif action=="double_click": pyautogui.doubleClick(int(args["x"]),int(args["y"]))
        elif action=="right_click": pyautogui.rightClick(int(args["x"]),int(args["y"]))
        elif action=="move": pyautogui.moveTo(int(args["x"]),int(args["y"]),duration=.12)
        elif action=="type": pyautogui.write(str(args.get("text") or ""),interval=.01)
        elif action=="hotkey":
            keys=args.get("keys") or []; keys=[k.strip() for k in keys.split(",")] if isinstance(keys,str) else keys; pyautogui.hotkey(*keys)
        elif action=="press": pyautogui.press(str(args.get("key") or "enter"))
        elif action=="scroll": pyautogui.scroll(int(args.get("amount") or 0))
        elif action=="drag":
            pyautogui.moveTo(int(args["x"]),int(args["y"]),duration=.1); pyautogui.dragTo(int(args["x2"]),int(args["y2"]),duration=.25,button="left")
        else: return f"Неизвестное действие на экране: {action}"
        return f"Выполнено действие на экране: {action}"
    except Exception as e: return tool_error("desktop control",e)

SCHEMAS=[{"type":"function","function":{"name":"desktop_action","description":"Управлять мышью и клавиатурой Windows. Для клика по объекту сначала используй vision/скриншот, затем передай координаты.","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["click","double_click","right_click","move","type","hotkey","press","scroll","drag"]},"x":{"type":"integer"},"y":{"type":"integer"},"x2":{"type":"integer"},"y2":{"type":"integer"},"text":{"type":"string"},"keys":{"type":"array","items":{"type":"string"}},"key":{"type":"string"},"amount":{"type":"integer"}},"required":["action"]}}}]
HANDLERS={"desktop_action":desktop_action}
