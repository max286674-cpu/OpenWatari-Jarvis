"""Deterministic local computer command layer for the voice edge.

This runs before the LLM for unambiguous Russian open/close application commands. It prevents a
weak/fallback model from saying "Включаю" without actually doing anything. Routine local app
control needs no confirmation; consequential/destructive actions remain in the normal safety path.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

_OPEN_RE = re.compile(r"^\s*(?:пожалуйста\s+)?(?:открой|открыть|запусти|запустить|включи|включить)\s+(.+?)\s*[.!?]*\s*$", re.I)
_CLOSE_RE = re.compile(r"^\s*(?:пожалуйста\s+)?(?:закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\s+(.+?)\s*[.!?]*\s*$", re.I)

_ALIASES = {
    "телеграм": ("Telegram.exe", "Telegram"), "telegram": ("Telegram.exe", "Telegram"), "телеграмм": ("Telegram.exe", "Telegram"),
    "хром": ("chrome.exe", "Google Chrome"), "chrome": ("chrome.exe", "Google Chrome"), "гугл хром": ("chrome.exe", "Google Chrome"),
    "файрфокс": ("firefox.exe", "Mozilla Firefox"), "firefox": ("firefox.exe", "Mozilla Firefox"),
    "дискорд": ("Discord.exe", "Discord"), "discord": ("Discord.exe", "Discord"),
    "спотифай": ("Spotify.exe", "Spotify"), "spotify": ("Spotify.exe", "Spotify"),
    "стим": ("steam.exe", "Steam"), "steam": ("steam.exe", "Steam"),
    "калькулятор": ("calc.exe", "Calculator"), "калькулятор виндовс": ("calc.exe", "Calculator"),
    "блокнот": ("notepad.exe", "Notepad"), "notepad": ("notepad.exe", "Notepad"),
    "проводник": ("explorer.exe", "File Explorer"), "эксплорер": ("explorer.exe", "File Explorer"), "explorer": ("explorer.exe", "File Explorer"),
    "cmd": ("cmd.exe", "Command Prompt"), "командную строку": ("cmd.exe", "Command Prompt"),
    "powershell": ("powershell.exe", "PowerShell"), "пауэршелл": ("powershell.exe", "PowerShell"),
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()).strip(" \"'«»")


def _process_exists(exe: str) -> bool:
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(
            [os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "tasklist.exe"), "/FI", f"IMAGENAME eq {exe}", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return exe.lower() in r.stdout.lower()
    except Exception:
        return False


def _taskkill(exe: str) -> tuple[bool, str]:
    taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "taskkill.exe")
    try:
        r = subprocess.run([taskkill, "/IM", exe, "/T", "/F"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _open(target: str) -> tuple[bool, str]:
    target_n = _norm(target)
    if target_n in {"калькулятор", "калькулятор виндовс", "calculator", "calc"} and os.name == "nt":
        try:
            os.startfile("calc:")  # type: ignore[attr-defined]
            return True, "Открыл Калькулятор, сэр."
        except Exception as e:
            return False, f"Не удалось открыть Калькулятор: {type(e).__name__}."

    alias = _ALIASES.get(target_n)
    if alias:
        exe, label = alias
        if os.name == "nt":
            try:
                subprocess.Popen([exe], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                time.sleep(0.35)
                if _process_exists(exe):
                    return True, f"Открыл {label}, сэр."
                return False, f"Windows не запустила {label} ({exe})."
            except FileNotFoundError:
                return False, f"Приложение {label} не найдено в системе."
            except Exception as e:
                return False, f"Не удалось открыть {label}: {type(e).__name__}."
        return False, "Прямое управление приложениями доступно на Windows."

    p = Path(target.strip(' \"\'«»')).expanduser()
    if p.exists():
        try:
            if os.name == "nt": os.startfile(str(p))  # type: ignore[attr-defined]
            else: subprocess.Popen(["xdg-open", str(p)])
            return True, f"Открыл {p}, сэр."
        except Exception as e:
            return False, f"Не удалось открыть {p}: {type(e).__name__}."
    return False, f"Не нашёл приложение или путь «{target}», сэр."


def _close(target: str) -> tuple[bool, str]:
    target_n = _norm(target)
    alias = _ALIASES.get(target_n)
    if not alias and re.fullmatch(r"[\w.-]+\.exe", target_n):
        alias = (target_n, target_n)
    if not alias:
        return False, f"Не знаю, какой процесс закрывать для «{target}», сэр."
    exe, label = alias
    if not _process_exists(exe):
        return True, f"{label} уже закрыт, сэр."
    ok, _detail = _taskkill(exe)
    if not ok:
        return False, f"Не удалось закрыть {label}, сэр."
    time.sleep(0.25)
    if _process_exists(exe):
        return False, f"Команда закрытия {label} выполнена, но процесс всё ещё работает, сэр."
    return True, f"Закрыл {label}, сэр."


def direct_computer_command(text: str) -> str | None:
    if sys.platform != "win32":
        return None
    t = (text or "").strip()
    if not t:
        return None
    m = _OPEN_RE.match(t)
    if m:
        _ok, result = _open(m.group(1))
        return result
    m = _CLOSE_RE.match(t)
    if m:
        _ok, result = _close(m.group(1))
        return result
    return None
