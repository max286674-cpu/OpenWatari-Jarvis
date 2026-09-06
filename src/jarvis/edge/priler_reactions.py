"""Optional playback bridge for the current Priler/Jarvis reaction voice packs.

Important: these are prerecorded reaction clips, not a general-purpose TTS model. We keep the
assets out of this repository and fetch them on first use from the upstream Priler repository.
That lets OpenWatari use the exact current Jarvis reaction recordings while keeping arbitrary
LLM replies on the normal TTS path.
"""

from __future__ import annotations

import asyncio
import os
import random
import threading
import urllib.request
from pathlib import Path

from loguru import logger

_REPO = "https://raw.githubusercontent.com/Priler/jarvis/master/resources/sound/voices"
_CACHE = Path(__file__).resolve().parents[3] / ".priler-voices"
_LOCK = threading.Lock()

_ALLOWED_VOICES = {"jarvis-howdy", "jarvis-og", "jarvis-remaster"}
_ALLOWED_LANGS = {"ru", "ua", "en"}


def enabled() -> bool:
    return os.getenv("JARVIS_PRILER_REACTIONS", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def voice() -> str:
    value = os.getenv("JARVIS_PRILER_VOICE", "jarvis-remaster").strip()
    return value if value in _ALLOWED_VOICES else "jarvis-remaster"


def language() -> str:
    value = os.getenv("JARVIS_PRILER_LANGUAGE", "ru").strip().lower()
    return value if value in _ALLOWED_LANGS else "ru"


def _path(reaction: str) -> Path:
    if not reaction or "/" in reaction or "\\" in reaction or not reaction.endswith(".mp3"):
        raise ValueError(f"invalid Priler reaction name: {reaction!r}")
    return _CACHE / voice() / language() / reaction


def _download(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_REPO}/{voice()}/{language()}/{path.name}"
    tmp = path.with_suffix(".tmp")
    logger.info(f"Priler voice: downloading {url}")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(path)


def ensure_cached(reaction: str) -> Path:
    path = _path(reaction)
    if path.exists() and path.stat().st_size > 0:
        return path
    with _LOCK:
        if not path.exists() or path.stat().st_size == 0:
            _download(path)
    return path


def random_reply() -> str:
    # Current remaster/howdy/og packs expose reply1..reply6 depending on the selected voice.
    maximum = 6 if voice() == "jarvis-remaster" else 3
    return f"reply{random.randint(1, maximum)}.mp3"


def play_blocking(reaction: str) -> None:
    """Play one prerecorded reaction and return when it finishes."""
    path = ensure_cached(reaction)
    try:
        import pygame
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("Priler reactions require pygame; run: uv sync --extra local-voice") from exc

    with _LOCK:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(20)
        pygame.mixer.music.stop()


async def play(reaction: str) -> None:
    await asyncio.to_thread(play_blocking, reaction)


async def play_random_reply() -> None:
    await play(random_reply())
