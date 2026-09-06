from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new, 1)


def patch_llm() -> None:
    p = "src/jarvis/brain/llm.py"
    s = read(p)
    if '("openrouter:", settings.openrouter_base_url' not in s:
        anchor = '            ("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),\n'
        s = replace_once(s, anchor, anchor + '            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n', "llm OpenRouter resolver")
    write(p, s)


def patch_config() -> None:
    p = "src/jarvis/config.py"
    s = read(p)
    if "openrouter_api_key:" not in s:
        anchor = '    minimax_base_url: str = "https://api.minimax.io/v1"\n'
        ins = anchor + '    # OpenRouter direct provider.\n    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n'
        s = replace_once(s, anchor, ins, "config OpenRouter")
    s = re.sub(r'llm_first_token_timeout_seconds:\s*float\s*=\s*[^\n]+', 'llm_first_token_timeout_seconds: float = 6.0', s, count=1)
    write(p, s)


def patch_system() -> None:
    p = "src/jarvis/brain/tools/system.py"
    s = read(p)
    old = '''async def _open_app_local(args: dict) -> str:\n    if not _enabled():\n        return "System tools are disabled, sir."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Which app should I open, sir?"\n    try:\n        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Launched {clip(app, 80)}, sir."\n    except Exception as e:\n        return tool_error("open app", e)\n'''
    new = '''async def _open_app_local(args: dict) -> str:\n    """Launch a desktop application reliably on the actual Windows desktop.\n\n    Windows ``os.startfile`` is preferred because it uses the user's shell/file\n    associations and does not depend on ``cmd /c start`` parsing.  A direct\n    executable path is handled by CreateProcess as a fallback.\n    """\n    if not _enabled():\n        return "Системное управление отключено."\n    app = (args.get("app") or "").strip()\n    if not app:\n        return "Какое приложение открыть?"\n    try:\n        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, app)\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen([app]))\n        return f"Открыл {clip(app, 80)}."\n    except Exception:\n        try:\n            if sys.platform == "win32":\n                await asyncio.to_thread(subprocess.Popen, [app], creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo())\n            else:\n                await asyncio.to_thread(lambda: subprocess.Popen([app]))\n            return f"Открыл {clip(app, 80)}."\n        except Exception as e:\n            return tool_error("open app", e)\n'''
    if old in s:
        s = s.replace(old, new, 1)
    elif 'Windows ``os.startfile`` is preferred' not in s:
        raise RuntimeError("system open_app anchor not found")

    old_url = '''        if sys.platform == "win32":\n            flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP\n            await asyncio.to_thread(\n                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", url], creationflags=flags))\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen(["xdg-open", url]))\n'''
    new_url = '''        if sys.platform == "win32":\n            import os\n            await asyncio.to_thread(os.startfile, url)\n        else:\n            await asyncio.to_thread(lambda: subprocess.Popen(["xdg-open", url]))\n'''
    if old_url in s:
        s = s.replace(old_url, new_url, 1)
    write(p, s)


def patch_bridge() -> None:
    p = "src/jarvis/edge/brain_bridge.py"
    s = read(p)
    # Never speak filler while an LLM/tool is working. This removes the repeated\n    # "Переключаюсь/Одну секунду/Занимаюсь" feedback and makes barge-in silent.\n    s = re.sub(r'\n\s*await self\.push_frame\(TTSSpeakFrame\("Переключаюсь, сэр\."\)\)\n', '\n', s)
    s = re.sub(r'\n\s*await self\.push_frame\(TTSSpeakFrame\("Одну секунду, сэр\."\)\)\n', '\n', s)
    s = re.sub(r'\n\s*def progress\(note: str\) -> None:\n\s*asyncio\.create_task\(self\.push_frame\(TTSSpeakFrame\(note\)\)\)\n', '\n        def progress(note: str) -> None:\n            return\n', s)
    write(p, s)


def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)
    # Disable model-generated filler at the source. Keep callbacks for compatibility, but never call them.\n    s = re.sub(r'(?ms)^\s*def _immediate_ack\(self, user_text: str, on_progress: Callable \| None\) -> None:\n.*?(?=^    async def respond_stream)', '''    def _immediate_ack(self, user_text: str, on_progress: Callable | None) -> None:\n        # Voice UX: the exact Priler wake acknowledgement is the only acknowledgement.\n        # Never add a second spoken filler before the model/tool response.\n        return\n\n''', s, count=1)
    # Tool watchdog must cancel stalled work instead of spawning repeated spoken updates.\n    s = re.sub(r'(?ms)^    async def _await_with_progress\(self, coro, on_progress: Callable \| None, name: str = ""\):\n.*?(?=^    def _immediate_ack)', '''    async def _await_with_progress(self, coro, on_progress: Callable | None, name: str = ""):\n        task = asyncio.ensure_future(coro)\n        try:\n            return await asyncio.wait_for(task, timeout=max(1.0, settings.llm_request_timeout_seconds))\n        except Exception:\n            if not task.done():\n                task.cancel()\n            raise\n\n''', s, count=1)
    # Don't emit huge traceback blocks for an expected tool failure.\n    s = s.replace('                logger.exception(f"tool {name} raised")\n', '                logger.error(f"tool {name} failed: {type(e).__name__}")\n', 1)

    # Deterministic desktop commands: bypass the LLM for common Windows actions.\n    marker = '\n\nclass JarvisAgent:'
    if '_direct_pc_command' not in s:
        helper = '''\n\ndef _direct_pc_command(text: str) -> str | None:\n    """Handle common desktop commands without an LLM round-trip."""\n    import os\n    import sys\n    import webbrowser\n    if sys.platform != "win32":\n        return None\n    t = text.lower().strip()\n    apps = {\n        "блокнот": "notepad.exe", "notepad": "notepad.exe",\n        "калькулятор": "calc.exe", "calculator": "calc.exe",\n        "проводник": "explorer.exe", "explorer": "explorer.exe",\n        "диспетчер задач": "taskmgr.exe", "task manager": "taskmgr.exe",\n        "chrome": "chrome.exe", "гугл хром": "chrome.exe",\n        "firefox": "firefox.exe", "фаерфокс": "firefox.exe",\n        "дискорд": "discord.exe", "discord": "discord.exe",\n        "телеграм": "telegram.exe", "telegram": "telegram.exe",\n        "spotify": "spotify.exe", "спотифай": "spotify.exe",\n        "steam": "steam.exe", "стим": "steam.exe",\n        "vs code": "code.exe", "visual studio code": "code.exe",\n    }\n    if any(k in t for k in ("открой ютуб", "открой youtube", "запусти ютуб", "включи ютуб")):\n        webbrowser.open("https://www.youtube.com")\n        return "Открыл YouTube."\n    for key, exe in apps.items():\n        if re.search(rf"\\b(?:открой|запусти|открывай|включи)\\s+{re.escape(key)}\\b", t) or t in {key, f"открой {key}", f"запусти {key}"}:\n            try:\n                os.startfile(exe)\n                return f"Открыл {key}."\n            except OSError:\n                try:\n                    subprocess.Popen([exe], creationflags=0x08000000)\n                    return f"Открыл {key}."\n                except OSError:\n                    return f"Не удалось открыть {key}."\n    return None\n'''
        s = s.replace(marker, helper + marker, 1)
    # Insert deterministic command before memory/LLM work.\n    anchor = '        self._history.append({"role": "user", "content": user_text})\n'
    if 'pc_reply = _direct_pc_command(user_text)' not in s:
        ins = anchor + '''        pc_reply = _direct_pc_command(user_text)\n        if pc_reply is not None:\n            self._history.append({"role": "assistant", "content": pc_reply})\n            self._trim()\n            self._stream_done = True\n            yield pc_reply\n            return\n'''
        s = replace_once(s, anchor, ins, "agent direct PC dispatch")
    write(p, s)


def patch_env_example() -> None:
    p = ".env.example"
    if not (ROOT / p).exists():
        return
    s = read(p)
    def put(key: str, value: str) -> None:
        nonlocal s
        if re.search(rf'(?m)^{re.escape(key)}=', s):
            s = re.sub(rf'(?m)^{re.escape(key)}=.*$', f'{key}={value}', s)
        else:
            s += f'\n{key}={value}\n'
    put("JARVIS_LLM_PRIMARY_MODEL", "openrouter:qwen/qwen3-30b-a3b-instruct-2507")
    put("JARVIS_LLM_FALLBACK_MODELS", "openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-30b-a3b-instruct-2507")
    put("JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS", "6")
    put("JARVIS_SYSTEM_TOOLS_ENABLED", "true")
    write(p, s)


def main() -> None:
    patch_config(); patch_llm(); patch_system(); patch_bridge(); patch_agent(); patch_env_example()
    # Syntax validation without importing the runtime.\n    import py_compile
    for rel in ("src/jarvis/config.py", "src/jarvis/brain/llm.py", "src/jarvis/brain/agent.py", "src/jarvis/brain/tools/system.py", "src/jarvis/edge/brain_bridge.py"):
        py_compile.compile(str(ROOT / rel), doraise=True)
    print("Runtime v7 applied and Python syntax validation passed.")
    print("Restart JARVIS, then run: uv run pytest -q")


if __name__ == "__main__":
    main()
