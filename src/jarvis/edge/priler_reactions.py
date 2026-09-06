"""Bridge to the current Priler/Jarvis prerecorded reaction packs.

The upstream project defines the available reaction clips in ``voice.toml``. We mirror that
metadata at runtime instead of guessing filenames/counts, and download only the selected clips.
These are prerecorded reactions, not a general-purpose TTS model.
"""

from __future__ import annotations

import asyncio
import os
import random
import threading
import urllib.request
from pathlib import Path
from typing import Any
import tomllib

from loguru import logger

_REPO = "https://raw.githubusercontent.com/Priler/jarvis/master/resources/sound/voices"
_CACHE = Path(__file__).resolve().parents[3] / ".priler-voices"
_LOCK = threading.Lock()
_ALLOWED_VOICES = {"jarvis-howdy", "jarvis-og", "jarvis-remaster"}
_ALLOWED_LANGS = {"ru", "ua", "en"}
_METADATA_NAME = "voice.toml"


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
    if not reaction or "/" in reaction or "\\" in reaction or reaction.startswith("."):
        raise ValueError(f"invalid Priler reaction name: {reaction!r}")
    return _CACHE / voice() / language() / reaction


def _download_bytes(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    logger.info("Priler voice: downloading {}", url)
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(destination)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _metadata_path() -> Path:
    return _CACHE / voice() / _METADATA_NAME


def _load_metadata() -> dict[str, Any]:
    path = _metadata_path()
    if not path.exists() or path.stat().st_size == 0:
        _download_bytes(f"{_REPO}/{voice()}/{_METADATA_NAME}", path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def available_reactions(category: str, lang: str | None = None) -> list[str]:
    """Return exact clip names declared by the selected upstream voice pack."""
    lang = (lang or language()).lower()
    reactions = _load_metadata().get("reactions", {}).get(lang, {})
    names = reactions.get(category, [])
    if not isinstance(names, list):
        return []
    return [f"{name}.mp3" for name in names if isinstance(name, str) and name]


def ensure_cached(reaction: str) -> Path:
    path = _path(reaction)
    if path.exists() and path.stat().st_size > 0:
        return path
    with _LOCK:
        if not path.exists() or path.stat().st_size == 0:
            url = f"{_REPO}/{voice()}/{language()}/{path.name}"
            _download_bytes(url, path)
    return path


def random_reaction(category: str = "reply") -> str:
    choices = available_reactions(category)
    if not choices:
        raise RuntimeError(
            f"Priler voice pack '{voice()}' has no '{category}' reaction for '{language()}'"
        )
    return random.choice(choices)


def random_reply() -> str:
    return random_reaction("reply")


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


async def play_random(category: str = "reply") -> None:
    await play(random_reaction(category))


async def play_random_reply() -> None:
    await play_random("reply")
