from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src" / "jarvis" / "brain" / "agent.py"
SYSTEM = ROOT / "src" / "jarvis" / "brain" / "tools" / "system.py"

DIRECT_BLOCK = r'''

# Deterministic local computer commands. These must not depend on an LLM emitting a tool call.
_DIRECT_OPEN_RE = re.compile(
    r"^\s*(?:пожалуйста\s+)?(?:открой|открыть|запусти|запустить|включи|включить)\s+(?P<app>.+?)\s*$",
    re.IGNORECASE,
)
_DIRECT_CLOSE_RE = re.compile(
    r"^\s*(?:пожалуйста\s+)?(?:закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\s+(?P<app>.+?)\s*$",
    re.IGNORECASE,
)


def _direct_app_name(text: str) -> str | None:
    m = _DIRECT_OPEN_RE.match(text or "")
    if not m:
        return None
    return m.group("app").strip().strip(".,!? ") or None


def _direct_close_name(text: str) -> str | None:
    m = _DIRECT_CLOSE_RE.match(text or "")
    if not m:
        return None
    return m.group("app").strip().strip(".,!? ") or None


def _normalise_app_name(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip().lower())
    aliases = {
        "телеграм": "Telegram", "телеграмм": "Telegram", "telegram": "Telegram",
        "хром": "Chrome", "гугл хром": "Chrome", "google chrome": "Chrome", "chrome": "Chrome",
        "файрфокс": "Firefox", "мозилла": "Firefox", "mozilla firefox": "Firefox", "firefox": "Firefox",
        "дискорд": "Discord", "discord": "Discord",
        "спотифай": "Spotify", "spotify": "Spotify",
        "стим": "Steam", "steam": "Steam",
        "калькулятор": "Calculator", "calculator": "Calculator",
        "блокнот": "Notepad", "notepad": "Notepad",
        "проводник": "File Explorer", "проводник windows": "File Explorer", "explorer": "File Explorer",
        "ворд": "Word", "microsoft word": "Word", "word": "Word",
        "эксель": "Excel", "excel": "Excel", "microsoft excel": "Excel",
        "visual studio code": "Visual Studio Code", "vs code": "Visual Studio Code", "код": "Visual Studio Code",
    }
    return aliases.get(s, name.strip())


async def _direct_computer_command(self, user_text: str) -> str | None:
    """Execute unambiguous local open/close commands before the LLM.

    This is intentionally narrow: only explicit Russian imperative open/close commands are
    intercepted. Ordinary conversation still uses the normal agent/tool pipeline.
    """
    from jarvis.brain.tools import tool_handlers

    app = _direct_app_name(user_text)
    if app:
        app = _normalise_app_name(app)
        handler = self._registry.get("open_app") or tool_handlers().get("open_app")
        if handler is None:
            return "Не могу открыть приложение: инструмент управления приложениями не зарегистрирован, сэр."
        result = await handler({"app": app})
        logger.info(f"DIRECT COMPUTER: open_app app={app!r} result={result!r}")
        return result

    app = _direct_close_name(user_text)
    if app:
        app = _normalise_app_name(app)
        handler = self._registry.get("process_op") or tool_handlers().get("process_op")
        if handler is None:
            return "Не могу закрыть приложение: инструмент управления процессами не зарегистрирован, сэр."
        process_aliases = {
            "Telegram": "Telegram.exe", "Chrome": "chrome.exe", "Firefox": "firefox.exe",
            "Discord": "Discord.exe", "Spotify": "Spotify.exe", "Steam": "steam.exe",
            "Calculator": "CalculatorApp.exe", "Notepad": "notepad.exe", "File Explorer": "explorer.exe",
            "Word": "WINWORD.EXE", "Excel": "EXCEL.EXE", "Visual Studio Code": "Code.exe",
        }
        result = await handler({"action": "kill", "name": process_aliases.get(app, app)})
        logger.info(f"DIRECT COMPUTER: process_op kill app={app!r} result={result!r}")
        return result
    return None
'''

CALL_MARKER = '        self._begin_turn(user_text)\n'
CALL_CODE = '''        direct_computer = await self._direct_computer_command(user_text)\n        if direct_computer is not None:\n            self._history.append({"role": "user", "content": user_text})\n            self._history.append({"role": "assistant", "content": direct_computer})\n            self._trim()\n            self._spawn_review()\n            return direct_computer\n'''


def insert_once(s: str, marker: str, block: str) -> str:
    if block.strip() in s:
        return s
    idx = s.find(marker)
    if idx < 0:
        raise SystemExit(f"marker not found: {marker!r}")
    return s[:idx] + block.strip() + "\n\n" + s[idx:]

s = AGENT.read_text(encoding="utf-8")
if "_DIRECT_OPEN_RE = re.compile(" not in s:
    marker = "# The owner's local timezone (configurable via JARVIS_USER_TZ). Used for time/greeting/scheduling.\n"
    idx = s.find(marker)
    if idx < 0:
        raise SystemExit("agent insertion marker not found")
    s = s[:idx] + DIRECT_BLOCK.strip() + "\n\n" + s[idx:]

# Bind the helper as a class method without restructuring the class.
if "JarvisAgent._direct_computer_command = _direct_computer_command" not in s:
    # The helper needs to be callable as self._direct_computer_command.
    bind_marker = "# The owner's local timezone (configurable via JARVIS_USER_TZ). Used for time/greeting/scheduling.\n"
    idx = s.find(bind_marker)
    if idx < 0:
        raise SystemExit("agent bind marker not found")
    s = s[:idx] + "JarvisAgent._direct_computer_command = _direct_computer_command\n\n" + s[idx:]

# The binding above cannot work before the class exists. Replace it with a class-local method by
# removing the premature binding and inserting the function body inside the class after __init__.
s = s.replace("JarvisAgent._direct_computer_command = _direct_computer_command\n\n", "")
method = DIRECT_BLOCK.split("async def _direct_computer_command", 1)[1]
method = "async def _direct_computer_command" + method
method = "\n".join("    " + line if line else line for line in method.splitlines())
class_marker = "    def _tools_for_turn(self, user_text: str) -> list[dict[str, Any]]:\n"
if "    async def _direct_computer_command(self, user_text: str)" not in s:
    idx = s.find(class_marker)
    if idx < 0:
        raise SystemExit("class insertion marker not found")
    s = s[:idx] + method.rstrip() + "\n\n" + s[idx:]

s = insert_once(s, CALL_MARKER, CALL_CODE)
ast.parse(s, filename=str(AGENT))
AGENT.write_text(s, encoding="utf-8")

# Make open_app robust on Windows: first try a normal executable/path, then Windows Start Apps
# (important for Microsoft Store Telegram/Calculator/Discord installs), then common install paths.
ss = SYSTEM.read_text(encoding="utf-8")
old_start = '''async def _open_app_local(args: dict) -> str:\n'''
start = ss.find(old_start)
if start < 0:
    raise SystemExit("_open_app_local not found")
end = ss.find("\n\nasync def _screenshot_local", start)
if end < 0:
    raise SystemExit("_open_app_local end marker not found")
new_open = r'''async def _open_app_local(args: dict) -> str:
    if not _enabled():
        return "System tools are disabled, sir."
    app = (args.get("app") or "").strip()
    if not app:
        return "Which app should I open, sir?"
    try:
        if sys.platform != "win32":
            proc = await asyncio.to_thread(subprocess.Popen, [app])
            return f"Launched {clip(app, 80)}, sir."

        import os
        import shlex
        import time as _time

        aliases = {
            "telegram": ["Telegram.exe", "telegram"],
            "chrome": ["chrome.exe", "chrome"],
            "firefox": ["firefox.exe", "firefox"],
            "discord": ["Discord.exe", "discord"],
            "spotify": ["Spotify.exe", "spotify"],
            "steam": ["steam.exe", "steam"],
            "calculator": ["calc.exe", "CalculatorApp.exe", "calculator"],
            "notepad": ["notepad.exe", "notepad"],
            "file explorer": ["explorer.exe"],
            "explorer": ["explorer.exe"],
            "word": ["WINWORD.EXE"],
            "excel": ["EXCEL.EXE"],
            "visual studio code": ["Code.exe", "code"],
            "vs code": ["Code.exe", "code"],
        }
        key = app.lower().strip()
        candidates = aliases.get(key, [app])

        # 1) Direct executable/path through cmd/start. This handles PATH aliases and full paths.
        for candidate in candidates:
            if os.path.isabs(candidate) and os.path.isfile(candidate):
                await asyncio.to_thread(subprocess.Popen, [candidate], creationflags=_NO_WINDOW,
                                         startupinfo=_hidden_startupinfo())
                return f"Launched {clip(candidate, 80)}, sir."
            try:
                await asyncio.to_thread(
                    subprocess.Popen,
                    [_win_exe("cmd"), "/c", "start", "", candidate],
                    shell=False, creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo())
                await asyncio.sleep(0.35)
                return f"Launched {clip(candidate, 80)}, sir."
            except Exception:
                pass

        # 2) Windows Start Apps. This is the reliable path for Store/MSIX applications.
        ps_name = app.replace("'", "''")
        ps = (
            "$ErrorActionPreference='Stop';"
            f"$x=Get-StartApps | Where-Object {{$_.Name -like '*{ps_name}*'}} | Select-Object -First 1;"
            "if($null -eq $x){exit 3}; Write-Output ($x.Name + '|' + $x.AppID)"
        )
        r = await asyncio.to_thread(
            subprocess.run,
            [_win_exe("powershell"), "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
            startupinfo=_hidden_startupinfo(),
        )
        line = (r.stdout or "").strip().splitlines()[-1:] or []
        if r.returncode == 0 and line and "|" in line[0]:
            _, appid = line[0].split("|", 1)
            await asyncio.to_thread(
                subprocess.Popen,
                [_win_exe("explorer"), f"shell:AppsFolder\\{appid}"],
                creationflags=_NO_WINDOW, startupinfo=_hidden_startupinfo())
            return f"Launched {clip(app, 80)}, sir."

        # 3) Common install locations for desktop apps.
        roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", ""),
                 os.environ.get("PROGRAMFILES(X86)", "")]
        exe_map = {
            "chrome": [r"Google\Chrome\Application\chrome.exe"],
            "firefox": [r"Mozilla Firefox\firefox.exe"],
            "spotify": [r"Spotify\Spotify.exe"],
            "discord": [r"Discord\Update.exe"],
            "steam": [r"Steam\Steam.exe"],
            "visual studio code": [r"Programs\Microsoft VS Code\Code.exe", r"Programs\Microsoft VS Code\bin\code.cmd"],
            "vs code": [r"Programs\Microsoft VS Code\Code.exe", r"Programs\Microsoft VS Code\bin\code.cmd"],
        }
        for root in roots:
            for rel in exe_map.get(key, []):
                p = os.path.join(root, rel)
                if os.path.isfile(p):
                    await asyncio.to_thread(subprocess.Popen, [p], creationflags=_NO_WINDOW,
                                             startupinfo=_hidden_startupinfo())
                    return f"Launched {clip(app, 80)}, sir."

        return f"Не удалось найти приложение «{app}» в Windows, сэр."
    except Exception as e:  # noqa: BLE001
        return tool_error("open app", e)
'''
ss = ss[:start] + new_open + ss[end:]
ast.parse(ss, filename=str(SYSTEM))
SYSTEM.write_text(ss, encoding="utf-8")
print("computer direct repair applied")
