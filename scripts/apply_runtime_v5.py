from pathlib import Path
import re
import py_compile

ROOT = Path(__file__).resolve().parents[1]

def edit(path, transforms):
    p = ROOT / path
    s = p.read_text(encoding='utf-8')
    original = s
    for old, new in transforms:
        if old not in s:
            raise SystemExit(f'ANCHOR NOT FOUND in {path}: {old[:100]!r}')
        s = s.replace(old, new, 1)
    if s == original:
        raise SystemExit(f'NO CHANGE: {path}')
    p.write_text(s, encoding='utf-8')
    print(f'UPDATED {path}')

# 1. Kill the artificial spoken progress/ack layer. The model should speak only the useful result.
edit('src/jarvis/brain/agent.py', [
    (
'''            # ACKNOWLEDGEMENT: announce what we're about to do BEFORE running the tool, always — so
            # Watari is never silently "working" (the Jarvis "Right away, sir — getting the time"
            # beat). Deterministic + instant (no LLM), and contextual from the args.
            if on_progress:
                on_progress(_ack_for(name, args))
            runnable.append((idx, name, args))''',
'''            # Do not speak progress/filler. Voice turns must contain useful speech only; progress
            # phrases such as "Занимаюсь", "Одну секунду" and "Переключаюсь" make the assistant feel
            # slow and broken and also steal time from the microphone.
            runnable.append((idx, name, args))'''
    ),
    (
'''        if not (on_progress and settings.ack_before_tools):
            return''',
'''        # Disabled deliberately: a fast voice assistant should not consume the turn with filler.'''
    ),
    (
'''        from jarvis.brain.intent_router import forced_tools
        fn = forced_tools(user_text)''',
'''        from jarvis.brain.intent_router import forced_tools
        fn = forced_tools(user_text)'''
    ),
])

# Replace the whole immediate-ack body by an early return, preserving the method for compatibility.
p = ROOT / 'src/jarvis/brain/agent.py'
s = p.read_text(encoding='utf-8')
start = s.index('    def _immediate_ack(')
end = s.index('\n    async def respond_stream(', start)
method = '''    def _immediate_ack(self, user_text: str, on_progress: Callable | None) -> None:
        """No-op by design. Never speak synthetic progress before a real answer."""
        return
'''
s = s[:start] + method + s[end:]
p.write_text(s, encoding='utf-8')
print('UPDATED agent.py (ack layer disabled)')

# 2. Long-running tools get a hard timeout instead of periodic speech. This prevents silent hangs.
edit('src/jarvis/brain/agent.py', [
    (
'''        task = asyncio.ensure_future(coro)
        interval = max(0.05, settings.tool_slow_warn_seconds)
        every = max(0.05, settings.tool_long_update_seconds)
        # Name the work in the updates ("the browser is taking longer…"), not just "it".
        label = _TOOL_LABELS.get(name, "that task")
        msgs = [
            f"{label.capitalize()} is taking a little longer than expected, sir — still on it.",
            f"Still working on {label}, sir.",
            f"Bear with me, sir — {label} is almost there.",
        ]
        i = 0
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if task in done:
                return task.result()          # re-raises any tool exception to the caller
            if on_progress:
                on_progress(msgs[min(i, len(msgs) - 1)])
            i += 1
            interval = every''',
'''        task = asyncio.ensure_future(coro)
        # A tool is allowed to be useful, but it is never allowed to freeze the voice turn forever.
        # Browser/system operations get a bounded window; cancellation propagates into the coroutine.
        timeout = max(8.0, min(30.0, float(settings.tool_slow_warn_seconds) * 3.0))
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise TimeoutError(f"tool {name} exceeded {timeout:.0f}s timeout")'''
    )
])

# 3. Deterministic Russian PC commands: no LLM tool-call lottery for common actions.
p = ROOT / 'src/jarvis/brain/agent.py'
s = p.read_text(encoding='utf-8')
anchor = '    async def _respond_stream_impl(self, user_text: str, on_progress: Callable | None = None):\n'
if anchor not in s:
    raise SystemExit('agent stream anchor missing')
helper = r'''    async def _direct_pc_command(self, text: str):
        """Deterministic fast path for common Russian desktop commands.

        These commands do not need an LLM decision. They call the same protected system tools used by
        the normal agent, but avoid model latency and prevent a weak model from merely saying that it
        opened something without actually doing it.
        """
        t = (text or "").strip().lower()
        from jarvis.brain.tools.system import open_app, open_url, media_pause

        app_aliases = {
            "блокнот": "notepad.exe", "нотпад": "notepad.exe", "калькулятор": "calc.exe",
            "проводник": "explorer.exe", "explorer": "explorer.exe", "хром": "chrome.exe",
            "chrome": "chrome.exe", "гугл хром": "chrome.exe", "firefox": "firefox.exe",
            "фаерфокс": "firefox.exe", "дискорд": "discord.exe", "телеграм": "telegram.exe",
            "telegram": "telegram.exe", "спотифай": "spotify.exe", "spotify": "spotify.exe",
            "стим": "steam.exe", "steam": "steam.exe", "код": "code.exe",
            "vs code": "code.exe", "вс код": "code.exe",
        }
        # open/start app
        m = re.match(r"^(?:джарвис[,.]?\s*)?(?:открой|запусти|запуск|включи)\s+(.+?)\s*$", t)
        if m:
            target = m.group(1).strip().strip('"')
            if target in ("ютуб", "youtube", "ютаб"):
                out = await open_url({"url": "https://www.youtube.com"})
                return out
            if target in app_aliases:
                out = await open_app({"app": app_aliases[target]})
                return out
            if target.startswith(("http://", "https://", "www.")) or ".com" in target or ".ru" in target:
                out = await open_url({"url": target})
                return out
        # explicit pause/resume media
        if re.match(r"^(?:джарвис[,.]?\s*)?(?:поставь|поставь на) паузу(?: видео| музыку)?$", t) or \
           re.match(r"^(?:джарвис[,.]?\s*)?(?:пауза|поставь видео на паузу)$", t):
            return await media_pause({})
        if re.match(r"^(?:джарвис[,.]?\s*)?(?:продолжи|возобнови)(?: видео| музыку)?$", t):
            return await media_pause({})
        return None

'''
s = s.replace(anchor, helper + anchor, 1)
needle = '        self._immediate_ack(user_text, on_progress)\n        self._history.append({"role": "user", "content": user_text})'
replacement = '''        self._immediate_ack(user_text, on_progress)
        direct = await self._direct_pc_command(user_text)
        if direct is not None:
            clean = _clean_reply(direct) or "Готово, сэр."
            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": clean})
            self._trim()
            self._stream_done = True
            yield clean
            return
        self._history.append({"role": "user", "content": user_text})'''
if needle not in s:
    raise SystemExit('stream insertion anchor missing')
s = s.replace(needle, replacement, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED agent.py (deterministic PC fast path)')

# 4. Make Windows app launching use the OS shell directly first, with a safe fallback.
edit('src/jarvis/brain/tools/system.py', [
    (
'''async def _open_app_local(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    app = (args.get("app") or "").strip()
    if not app:
        return "Which app should I open, sir?"
    try:
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200
            await asyncio.to_thread(
                lambda: subprocess.Popen([_win_exe("cmd"), "/c", "start", "", app], shell=False, creationflags=flags))
        else:
            await asyncio.to_thread(lambda: subprocess.Popen([app]))
        return f"Launched {clip(app, 80)}, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("open app", e)
''',
'''async def _open_app_local(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled."
    app = (args.get("app") or "").strip().strip('"')
    if not app:
        return "Не указано приложение."
    try:
        if sys.platform == "win32":
            import os
            # os.startfile uses Windows ShellExecute/App Paths and is much more reliable for installed
            # GUI applications than `cmd /c start`. It also avoids a shell command interpreter.
            await asyncio.to_thread(os.startfile, app)
        else:
            await asyncio.to_thread(lambda: subprocess.Popen([app]))
        return f"Запустил {clip(app, 80)}."
    except Exception:
        # Fallback: Start-Process resolves many Start-menu/App Paths entries.
        if sys.platform == "win32":
            try:
                await asyncio.to_thread(
                    subprocess.Popen,
                    [_win_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command",
                     "Start-Process -FilePath " + _ps_quote(app)],
                    creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo())
                return f"Запустил {clip(app, 80)}."
            except Exception as e:
                return tool_error("open app", e)
        return tool_error("open app", Exception("unsupported platform"))
'''
    )
])

# 5. The Russian voice configuration should remain hot and responsive.
edit('src/jarvis/config.py', [
    ('    hot_mic_after_wake: bool = False', '    hot_mic_after_wake: bool = True'),
    ('    wake_word_threshold: float = 0.5', '    wake_word_threshold: float = 0.35'),
    ('    deepgram_endpointing_ms: int = 700', '    deepgram_endpointing_ms: int = 350'),
    ('    llm_first_token_timeout_seconds: float = 4.0', '    llm_first_token_timeout_seconds: float = 2.5'),
])

# 6. Validate all edited Python modules before the user runs them.
for rel in [
    'src/jarvis/config.py', 'src/jarvis/brain/agent.py',
    'src/jarvis/brain/tools/system.py', 'src/jarvis/edge/brain_bridge.py',
]:
    py_compile.compile(str(ROOT / rel), doraise=True)
print('PY_COMPILE_OK')
print('Runtime v5 applied.')
print('Run: uv run pytest -q')
print('Then: uv run python -m jarvis.edge.assistant')
