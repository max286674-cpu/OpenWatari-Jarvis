"""Local audio playback — make Jarvis actually PLAY a sound file out loud (not just deliver it).

This is what lets Jarvis play your personal Telegram tracks audibly on the desktop: the track is
downloaded and piped to **ffplay** (from ffmpeg, already on PATH), launched detached and windowless
so it plays in the background through your default output device. A single module-level handle holds
the current player so ``stop_music`` can stop it.

(For YouTube / YouTube Music, playback already happens in the autoplay browser — that path makes
real sound too; this module covers local files like the Telegram playlist.)
"""

from __future__ import annotations

import shutil
import subprocess

from loguru import logger

from jarvis.brain.tools.base import not_configured

# The currently-playing ffplay process + its label (module-level so stop_music can reach it).
_PROC: subprocess.Popen | None = None
_NOW: str | None = None


def play_file(path: str, label: str | None = None) -> str | None:
    """Play a local audio file out loud via ffplay (detached). Returns an error string, or None on success."""
    global _PROC, _NOW
    if not shutil.which("ffplay"):
        return not_configured("local audio playback", "ffplay (install ffmpeg — e.g. scoop install ffmpeg)")
    _stop()  # only one local track at a time
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        _PROC = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _NOW = label or path
        logger.info(f"local playback started: {_NOW}")
        return None
    except Exception as e:  # noqa: BLE001
        return f"I couldn't start playback, sir: {e}"


def _stop() -> str | None:
    """Stop the current local playback if any. Returns the label that was playing, or None."""
    global _PROC, _NOW
    was = _NOW
    if _PROC is not None and _PROC.poll() is None:
        try:
            _PROC.terminate()
        except Exception:  # noqa: BLE001
            pass
    _PROC = None
    _NOW = None
    return was


def now_playing() -> str | None:
    """The label currently playing locally, or None (also clears if the player has exited)."""
    global _PROC, _NOW
    if _PROC is not None and _PROC.poll() is not None:
        _PROC = None
        _NOW = None
    return _NOW


async def stop_music(_args: dict) -> str:
    was = _stop()
    if was:
        return f"Stopped '{was}', sir."
    return "Nothing was playing out loud, sir. (If it's a YouTube tab, I can close the browser.)"


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "stop_music",
            "description": (
                "Stop music that's playing OUT LOUD on the desktop (a local track, e.g. from the "
                "Telegram playlist). For YouTube/YouTube Music playing in the browser, close the "
                "browser tab instead."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

HANDLERS = {"stop_music": stop_music}
