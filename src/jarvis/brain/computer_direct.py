"""Deterministic Windows app control for simple Russian voice commands.

Uses several real Windows launch mechanisms instead of assuming an executable is on PATH:
1) direct executable for classic apps;
2) Start Menu / Get-StartApps AppUserModelID for packaged and installed desktop apps;
3) Start Menu .lnk shortcuts as a final fallback.

Routine local app control never requires confirmation.
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
    "калькулятор": ("calc.exe", "Calculator"), "калькулятор виндовс": ("calc.exe", "Calculator"), "calculator": ("calc.exe", "Calculator"),
    "блокнот": ("notepad.exe", "Notepad"), "notepad": ("notepad.exe", "Notepad"),
    "проводник": ("explorer.exe", "File Explorer"), "эксплорер": ("explorer.exe", "File Explorer"), "explorer": ("explorer.exe", "File Explorer"),
    "cmd": ("cmd.exe", "Command Prompt"), "командную строку": ("cmd.exe", "Command Prompt"),
    "powershell": ("powershell.exe", "PowerShell"), "пауэршелл": ("powershell.exe", "PowerShell"),
    "word": ("WINWORD.EXE", "Microsoft Word"), "ворд": ("WINWORD.EXE", "Microsoft Word"),
    "excel": ("EXCEL.EXE", "Microsoft Excel"), "эксель": ("EXCEL.EXE", "Microsoft Excel"),
}

_START_MENU_DIRS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()).strip(" \"'«»")


def _win(cmd: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _process_exists(exe: str) -> bool:
    if os.name != "nt":
        return False
    try:
        r = _win([os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "tasklist.exe"),
                  "/FI", f"IMAGENAME eq {exe}", "/NH"], 5)
        return exe.lower() in r.stdout.lower()
    except Exception:
        return False


def _title_process_exists(label: str) -> bool:
    """Fallback for apps whose process executable is not the public app name."""
    if os.name != "nt":
        return False
    try:
        ps = ("Get-Process | Where-Object { $_.MainWindowTitle -and "
              f"$_.MainWindowTitle -like '*{label.replace(chr(39), chr(96)+chr(39)}*' }} | "
              "Select-Object -First 1 -ExpandProperty Id")
        r = _win(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], 6)
        return bool((r.stdout or "").strip())
    except Exception:
        return False


def _taskkill(exe: str) -> tuple[bool, str]:
    taskkill = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "taskkill.exe")
    try:
        r = _win([taskkill, "/IM", exe, "/T", "/F"], 15)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _find_start_app(name: str) -> str | None:
    """Return the AppUserModelID of a Start Menu app using Microsoft's Get-StartApps."""
    if os.name != "nt":
        return None
    try:
        # Get-StartApps supports wildcard matching and returns Name + AppID for installed apps.
        escaped = name.replace("'", "''")
        ps = f"Get-StartApps -Name '*{escaped}*' | Select-Object -First 1 -ExpandProperty AppID"
        r = _win(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], 8)
        appid = (r.stdout or "").strip().splitlines()
        return appid[0].strip() if appid else None
    except Exception:
        return None


def _find_shortcut(name: str) -> Path | None:
    target = _norm(name)
    if not target:
        return None
    candidates: list[Path] = []
    for root in _START_MENU_DIRS:
        if not root.exists():
            continue
        try:
            candidates.extend(root.rglob("*.lnk"))
        except Exception:
            continue
    exact = [p for p in candidates if _norm(p.stem) == target]
    if exact:
        return exact[0]
    fuzzy = [p for p in candidates if target in _norm(p.stem) or _norm(p.stem) in target]
    return fuzzy[0] if fuzzy else None


def _launch_exe(exe: str) -> bool:
    try:
        subprocess.Popen([exe], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (FileNotFoundError, OSError):
        return False


def _open(target: str) -> tuple[bool, str]:
    target_n = _norm(target)

    if target_n in {"калькулятор", "калькулятор виндовс", "calculator", "calc"} and os.name == "nt":
        try:
            os.startfile("calc:")  # type: ignore[attr-defined]
            time.sleep(0.8)
            return True, "Открыл Калькулятор, сэр."
        except Exception:
            pass

    alias = _ALIASES.get(target_n)
    if alias and os.name == "nt":
        exe, label = alias
        if _launch_exe(exe):
            time.sleep(0.7)
            if _process_exists(exe) or _title_process_exists(label):
                return True, f"Открыл {label}, сэр."

        # Modern Windows apps and applications not present on PATH are often registered in StartApps.
        appid = _find_start_app(label) or _find_start_app(target_n)
        if appid:
            try:
                subprocess.Popen([os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "explorer.exe"),
                                  f"shell:AppsFolder\\{appid}"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                time.sleep(1.0)
                if _process_exists(exe) or _title_process_exists(label):
                    return True, f"Открыл {label}, сэр."
            except Exception:
                pass

        shortcut = _find_shortcut(label) or _find_shortcut(target_n)
        if shortcut:
            try:
                os.startfile(str(shortcut))  # type: ignore[attr-defined]
                time.sleep(1.0)
                if _process_exists(exe) or _title_process_exists(label):
                    return True, f"Открыл {label}, сэр."
            except Exception:
                pass
        return False, f"Не удалось запустить {label}. Проверьте, что приложение установлено."

    # User gave a real executable/path.
    p = Path(target.strip(' \"\'«»')).expanduser()
    if p.exists():
        try:
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return True, f"Открыл {p}, сэр."
        except Exception as e:
            return False, f"Не удалось открыть {p}: {type(e).__name__}."

    # Generic installed application: use StartApps before giving up.
    if os.name == "nt":
        appid = _find_start_app(target)
        if appid:
            try:
                subprocess.Popen([os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "explorer.exe"),
                                  f"shell:AppsFolder\\{appid}"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return True, f"Открыл {target}, сэр."
            except Exception:
                pass
        shortcut = _find_shortcut(target)
        if shortcut:
            try:
                os.startfile(str(shortcut))  # type: ignore[attr-defined]
                return True, f"Открыл {target}, сэр."
            except Exception:
                pass
    return False, f"Не нашёл приложение или путь «{target}», сэр."


def _close(target: str) -> tuple[bool, str]:
    target_n = _norm(target)
    alias = _ALIASES.get(target_n)
    if not alias and re.fullmatch(r"[\w.-]+\.exe", target_n):
        alias = (target_n, target_n)
    if not alias:
        # Try a title-based process lookup for an installed Start Menu app.
        if _title_process_exists(target):
            try:
                escaped = target.replace("'", "''")
                ps = ("Get-Process | Where-Object { $_.MainWindowTitle -and "
                      f"$_.MainWindowTitle -like '*{escaped}*' }} | Stop-Process -Force")
                r = _win(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], 12)
                if r.returncode == 0:
                    return True, f"Закрыл {target}, сэр."
            except Exception:
                pass
        return False, f"Не знаю, какой процесс закрывать для «{target}», сэр."

    exe, label = alias
    if not _process_exists(exe) and not _title_process_exists(label):
        return True, f"{label} уже закрыт, сэр."
    ok, _detail = _taskkill(exe)
    if not ok and _title_process_exists(label):
        try:
            escaped = label.replace("'", "''")
            ps = ("Get-Process | Where-Object { $_.MainWindowTitle -and "
                  f"$_.MainWindowTitle -like '*{escaped}*' }} | Stop-Process -Force")
            ok = _win(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], 12).returncode == 0
        except Exception:
            ok = False
    time.sleep(0.4)
    if _process_exists(exe) or _title_process_exists(label):
        return False, f"Не удалось полностью закрыть {label}, сэр."
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
