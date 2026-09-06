"""Vision-first Windows computer agent.

Uses the owner's OpenRouter key and a multimodal model to observe the actual screen, choose one
small GUI action, execute it locally, then observe again. This is intentionally separate from the
text-only LLM so the brain cannot claim it "sees" a screen when it only received a screenshot path.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from io import BytesIO
from typing import Any

from jarvis.brain.tools.base import tool_error
from jarvis.config import settings

_ACTIONS = {"click", "double_click", "right_click", "type", "press", "hotkey", "scroll", "done"}


def _gui():
    if sys.platform != "win32":
        raise RuntimeError("computer vision control requires the Windows display host")
    import pyautogui
    pyautogui.PAUSE = 0.05
    pyautogui.FAILSAFE = True
    return pyautogui


def _image_data_url() -> tuple[str, int, int]:
    p = _gui()
    shot = p.screenshot()
    buf = BytesIO()
    shot.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), shot.width, shot.height


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


async def _vision_decision(task: str, image_url: str, width: int, height: int) -> dict[str, Any] | None:
    key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("JARVIS_OPENROUTER_API_KEY / OPENROUTER_API_KEY is not set")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=key,
        timeout=min(15.0, float(settings.llm_request_timeout_seconds)),
        max_retries=1,
    )
    prompt = f"""You are the visual computer-use controller for a Windows PC.
Task from the owner: {task}
Screen size: {width}x{height}.

Look at the screenshot and choose exactly ONE next action. Never invent coordinates: use visible UI.
Return ONLY JSON, no markdown, with this schema:
{{"action":"click|double_click|right_click|type|press|hotkey|scroll|done", "x":0, "y":0,
 "text":"", "key":"", "keys":["ctrl","s"], "amount":0, "reason":"brief"}}
For click actions give pixel coordinates. For typing use text. For keyboard shortcuts use keys.
If the task is complete, return action=done. Do not use shell commands. Do not delete files or send
messages/emails; stop with done if such a consequential action would be required.
"""
    r = await client.chat.completions.create(
        model=settings.computer_vision_model,
        messages=[
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]},
        ],
        temperature=0,
        max_tokens=220,
    )
    return _extract_json(r.choices[0].message.content or "")


def _execute(action: dict[str, Any]) -> str:
    p = _gui()
    name = str(action.get("action") or "").lower()
    if name not in _ACTIONS:
        return "Некорректное действие компьютерного агента."
    if name == "done":
        return "done"
    if name in {"click", "double_click", "right_click"}:
        x, y = int(action["x"]), int(action["y"])
        if name == "click": p.click(x, y)
        elif name == "double_click": p.doubleClick(x, y)
        else: p.rightClick(x, y)
    elif name == "type":
        import pyperclip
        text = str(action.get("text") or "")
        if len(text) > 12000:
            return "Слишком большой текст для одного ввода."
        pyperclip.copy(text)
        p.hotkey("ctrl", "v")
    elif name == "press":
        p.press(str(action.get("key") or "enter"))
    elif name == "hotkey":
        keys = action.get("keys") or []
        if isinstance(keys, str):
            keys = [x.strip() for x in keys.replace(",", "+").split("+") if x.strip()]
        p.hotkey(*keys)
    elif name == "scroll":
        p.scroll(max(-20, min(20, int(action.get("amount") or 0))))
    return f"executed:{name}"


async def computer_use(args: dict) -> str:
    """Observe, act, verify: a bounded vision loop for Windows GUI work."""
    task = str(args.get("task") or "").strip()
    if not task:
        return "Не указана задача для управления компьютером."
    if not settings.desktop_tools_enabled:
        return "Управление компьютером отключено в настройках."
    max_steps = max(1, min(10, int(args.get("max_steps") or settings.computer_max_steps)))
    try:
        import asyncio
        for step in range(max_steps):
            image, width, height = await asyncio.to_thread(_image_data_url)
            decision = await _vision_decision(task, image, width, height)
            if not decision:
                return "Не удалось получить корректное решение по экрану."
            action = str(decision.get("action") or "").lower()
            if action == "done":
                return f"Задача на компьютере завершена за {step + 1} шагов."
            result = await asyncio.to_thread(_execute, decision)
            if result.startswith("Слишком") or result.startswith("Некорректно"):
                return result
            await asyncio.sleep(0.18)
        return f"Остановился после {max_steps} шагов; задача не подтверждена как завершённая."
    except Exception as e:
        return tool_error("computer vision", e)


SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "computer_use",
        "description": "Управлять реальным экраном Windows через vision: посмотреть экран, нажать, ввести текст, использовать клавиши и проверить результат. Не требует подтверждения для обычной локальной работы.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Полная задача владельца на компьютере."},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["task"],
        },
    }
}]

HANDLERS = {"computer_use": computer_use}
