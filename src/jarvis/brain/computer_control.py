"""Deterministic local computer control for common owner commands.

This module deliberately bypasses the LLM for high-confidence open/find/close commands.
The LLM is still used for complex computer work, but it must not be allowed to claim that
an elementary Windows action happened when no action was executed.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_OPEN_RE = re.compile(r"^\s*(?:джарвис[,:]?\s*)?(?:открой|открыть|запусти|запустить|включи|включить)\s+(.+?)\s*$", re.I)
_CLOSE_RE = re.compile(r"^\s*(?:джарвис[,:]?\s*)?(?:закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\s+(.+?)\s*$", re.I)
_FIND_RE = re.compile(r"^\s*(?:джарвис[,:]?\s*)?(?:найди|найти|поищи|поиск)\s+(.+?)\s*$", re.I)

# Common Russian names -> executable names. Arbitrary installed apps are resolved through StartApps.
_ALIASES = {
    "телеграм": "Telegram.exe", "telegram": "Telegram.exe",
    "телеграмм": "Telegram.exe", "хром": "chrome.exe", "chrome": "chrome.exe",
    "гугл хром": "chrome.exe", "файрфокс": "firefox.exe", "firefox": "firefox.exe",
    "дискорд": "Discord.exe", "discord": "Discord.exe", "спотифай": "Spotify.exe", "spotify": "Spotify.exe",
    "стим": "steam.exe", "steam": "steam.exe", "калькулятор": "calc.exe", "calculator": "calc.exe",
    "блокнот": "notepad.exe", "notepad": "notepad.exe", "проводник": "explorer.exe", "explorer": "explorer.exe",
    "ворд": "winword.exe", "word": "winword.exe", "эксель": "excel.exe", "excel": "excel.exe",
    "паинт": "mspaint.exe", "paint": "mspaint.exe",
}


def _enabled() -> bool:
    try:
        from jarvis.config import settings
        return bool(settings.system_tools_enabled)
    except Exception:
        return True


def _ps() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _hidden_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"creationflags": 0x08000000, "startupinfo": si}


def _clean_target(target: str) -> str:
    target = target.strip().strip('"').strip("'")
    target = re.sub(r"\s+(пожалуйста|сэр|срочно)\s*$", "", target, flags=re.I)
    return target.strip()


def _start_apps() -> list[tuple[str, str]]:
    if sys.platform != "win32":
        return []
    try:
        r = subprocess.run(
            [_ps(), "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL, **_hidden_kwargs())
        if r.returncode != 0 or not r.stdout.strip():
            return []
        import json
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]
        return [(str(x.get("Name", "")), str(x.get("AppID", ""))) for x in data if x.get("Name")]
    except Exception:
        return []


def _resolve_app(target: str) -> tuple[str, str]:
    """Return ('exe', command) or ('appx', AppID). Never executes the target here."""
    target = _clean_target(target)
    low = target.casefold()
    if low in _ALIASES:
        return "exe", _ALIASES[low]

    # Explicit existing path/file: Windows knows how to open it with its associated application.
    p = Path(os.path.expandvars(os.path.expanduser(target)))
    if p.exists():
        return "path", str(p)

    # Exact/contains match against PATH executables.
    if shutil.which(target):
        return "exe", target
    if not target.lower().endswith(".exe") and shutil.which(target + ".exe"):
        return "exe", target + ".exe"

    apps = _start_apps()
    low = target.casefold()
    exact = [(n, i) for n, i in apps if n.casefold() == low]
    if exact:
        return "appx", exact[0][1]
    partial = [(n, i) for n, i in apps if low in n.casefold() or n.casefold() in low]
    if partial:
        return "appx", partial[0][1]

    # Last resort: let Windows shell resolve a registered app/file association.
    return "shell", target


async def open_target(target: str) -> str:
    if not _enabled():
        return "Не могу открыть: системные инструменты отключены."
    target = _clean_target(target)
    if not target:
        return "Не указано, что открыть."
    try:
        kind, value = await asyncio.to_thread(_resolve_app, target)
        if sys.platform == "win32":
            if kind == "path":
                os.startfile(value)  # type: ignore[attr-defined]
            elif kind == "appx":
                subprocess.Popen([_ps(), "-NoProfile", "-NonInteractive", "-Command", f"Start-Process 'shell:AppsFolder\\{value}'"], **_hidden_kwargs())
            else:
                subprocess.Popen(["cmd.exe", "/c", "start", "", value], **_hidden_kwargs())
        else:
            subprocess.Popen([value])
        # Verify an application/path request did not immediately fail at process creation.
        await asyncio.sleep(0.15)
        return f"Открыл: {target}."
    except Exception as exc:
        return f"Не удалось открыть «{target}»: {type(exc).__name__}: {exc}"


async def close_target(target: str) -> str:
    if not _enabled():
        return "Не могу закрыть: системные инструменты отключены."
    target = _clean_target(target)
    if not target:
        return "Не указано, что закрыть."
    try:
        kind, value = await asyncio.to_thread(_resolve_app, target)
        if kind == "path":
            name = Path(value).name
        elif kind == "exe":
            name = Path(value).name
        else:
            # StartApps may expose an AppID but process name is unknown; use tasklist name matching target.
            name = target if target.lower().endswith(".exe") else target + ".exe"
        cmd = [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe"), "/IM", name, "/T", "/F"]
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=20, **_hidden_kwargs())
        if r.returncode == 0:
            return f"Закрыл: {target}."
        # For aliases resolved to a known executable, never claim success when taskkill failed.
        detail = (r.stderr or r.stdout or "процесс не найден").strip().splitlines()[-1]
        return f"Не удалось закрыть «{target}»: {detail}"
    except Exception as exc:
        return f"Не удалось закрыть «{target}»: {type(exc).__name__}: {exc}"


def _search_roots() -> list[Path]:
    home = Path.home()
    roots = [home / "Desktop", home / "Documents", home / "Downloads", home / "Pictures", home / "Videos", home / "Music"]
    if sys.platform == "win32":
        roots += [Path(r"C:\AI"), Path(r"C:\Projects"), Path(r"C:\Users")]
    return [p for p in roots if p.exists()]


def _find_sync(query: str, limit: int = 30) -> list[str]:
    query = _clean_target(query).casefold()
    # Full filesystem search is intentionally bounded to avoid hanging the voice turn.
    roots = _search_roots()
    matches: list[str] = []
    for root in roots:
        try:
            for p in root.rglob("*"):
                if query in p.name.casefold():
                    matches.append(str(p))
                    if len(matches) >= limit:
                        return matches
        except (OSError, PermissionError):
            continue
    return matches


async def find_on_computer(query: str) -> str:
    if not _enabled():
        return "Поиск по компьютеру отключён."
    query = _clean_target(query)
    if not query:
        return "Не указано, что искать."
    try:
        matches = await asyncio.to_thread(_find_sync, query)
        if not matches:
            return f"На доступных папках компьютера ничего не найдено по запросу «{query}»."
        return "Нашёл:\n" + "\n".join(matches[:30])
    except Exception as exc:
        return f"Ошибка поиска «{query}»: {type(exc).__name__}: {exc}"


async def direct_command(user_text: str) -> str | None:
    """Execute only high-confidence open/close/find commands. Return None for all other turns."""
    text = user_text or ""
    m = _OPEN_RE.match(text)
    if m:
        return await open_target(m.group(1))
    m = _CLOSE_RE.match(text)
    if m:
        return await close_target(m.group(1))
    m = _FIND_RE.match(text)
    if m:
        return await find_on_computer(m.group(1))
    return None
