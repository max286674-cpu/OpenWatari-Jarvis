"""Music playback — free, music-tuned sources so Jarvis can actually start a song.

Spotify's Web API only controls playback on Premium accounts, so it is NOT the default. The
sources, in order of preference:

* ``ytmusic`` (DEFAULT) — **YouTube Music** via ytmusicapi: music-tuned search (songs, not random
  videos), free, no account. Resolves to a track and opens the YouTube Music web player (the
  browser is launched with autoplay allowed, so it plays with sound).
* ``telegram`` — your **personal Telegram playlist**: pulls a track from the configured chat and
  delivers it to your phone Telegram (see ``telegram.telegram_music``).
* ``youtube`` — plain YouTube search (kept as a fallback / for non-music clips).
* ``spotify`` — only if Vazghen has Spotify Premium.

The default source is ``settings.music_source``.
"""

from __future__ import annotations

import asyncio

from jarvis.brain.tools.base import not_configured, tool_error
from jarvis.config import settings


def _ytmusic_search(query: str) -> tuple[str | None, str | None]:
    """Return (videoId, 'Title — Artist') for the top SONG result, via ytmusicapi (no auth)."""
    from ytmusicapi import YTMusic  # type: ignore

    yt = YTMusic()  # unauthenticated: catalogue search works without login
    results = yt.search(query, filter="songs") or yt.search(query)
    if not results:
        return None, None
    top = results[0]
    vid = top.get("videoId")
    title = top.get("title")
    artists = ", ".join(a.get("name", "") for a in (top.get("artists") or []) if a.get("name"))
    label = f"{title} — {artists}".strip(" —") if title else None
    return vid, label


def _yt_search(query: str) -> tuple[str | None, str | None]:
    import yt_dlp  # type: ignore

    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=False)
    entries = (info or {}).get("entries") or []
    if not entries:
        return None, None
    return entries[0].get("id"), entries[0].get("title")


async def _open_in_browser(url: str) -> str | None:
    """Open `url` in Jarvis's autoplay browser. Returns an error string, or None on success."""
    if not settings.browser_tools_enabled:
        return "I need the browser enabled to play music, sir (JARVIS_BROWSER_TOOLS_ENABLED)."
    from jarvis.brain.tools.browser import browser as browser_tool

    r = await browser_tool({"action": "new_tab", "url": url})
    if "isn't configured" in r or "disabled" in r:
        return r
    return None


async def play_music(args: dict) -> str:
    query = (args.get("query") or "").strip()
    source = (args.get("source") or settings.music_source or "ytmusic").strip().lower()

    if source == "spotify":
        from jarvis.brain.tools.spotify import spotify as spotify_tool

        return await spotify_tool({"action": "search" if query else "play", "query": query})

    if source == "telegram":
        from jarvis.brain.tools.telegram import telegram_music

        return await telegram_music(
            {"action": "play", "query": query, "local": bool(args.get("local"))}
        )

    if not query:
        return "What should I play, sir?"

    # YouTube Music (default): music-tuned search → YouTube Music player.
    if source == "ytmusic":
        try:
            import ytmusicapi  # noqa: F401
        except ImportError:
            source = "youtube"  # gracefully fall back to plain YouTube
        else:
            try:
                vid, label = await asyncio.to_thread(_ytmusic_search, query)
                if vid:
                    err = await _open_in_browser(f"https://music.youtube.com/watch?v={vid}")
                    if err:
                        return err
                    return f"Playing {label or query} on YouTube Music, sir."
                source = "youtube"  # no song hit — try a plain search
            except Exception as e:  # noqa: BLE001
                return tool_error("music playback", e)

    # Plain YouTube (fallback / explicit).
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return not_configured("music playback", "yt-dlp (uv sync --extra brain)")
    try:
        vid, title = await asyncio.to_thread(_yt_search, query)
        if not vid:
            return f"I couldn't find '{query}', sir."
        err = await _open_in_browser(f"https://www.youtube.com/watch?v={vid}")
        if err:
            return err
        return f"Playing {title or query} on YouTube, sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("music playback", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": (
                "Play a song or artist. Default source 'ytmusic' (YouTube Music) is FREE and "
                "music-tuned — no account, plays with sound. 'telegram' plays from Vazghen's "
                "personal Telegram playlist (delivered to his phone). 'youtube' is plain search. "
                "Use 'spotify' only if he has Premium. Prefer this over the spotify tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Song / artist to play (optional for 'telegram')."},
                    "source": {
                        "type": "string",
                        "enum": ["ytmusic", "telegram", "youtube", "spotify"],
                        "description": "Default 'ytmusic' (free). 'telegram' = his saved playlist.",
                    },
                    "local": {"type": "boolean", "description": "For source 'telegram': true plays OUT LOUD on the desktop; false delivers to his phone."},
                },
                "required": [],
            },
        },
    },
]

HANDLERS = {"play_music": play_music}
