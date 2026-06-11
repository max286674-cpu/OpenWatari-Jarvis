"""Spotify tool — control playback by voice via the Spotify Web API.

Auth is the standard user OAuth: a one-time authorization yields a long-lived refresh token
(``settings.spotify_refresh_token``); each call exchanges it for a short-lived access token.
Controlling playback requires an ACTIVE Spotify device (the desktop/phone app open somewhere).

One ``spotify`` tool with an ``action`` so the LLM has a single clear verb:
  now_playing · play · pause · next · previous · search (search also starts playback of the top hit).
"""

from __future__ import annotations

import base64

from jarvis.brain.tools.base import http_post, not_configured, tool_error
from jarvis.config import settings

_API = "https://api.spotify.com/v1"


def _api_error(r) -> str | None:
    """Map a non-2xx Spotify response to a speakable note, or None if it's fine."""
    if r.status_code < 400:
        return None
    if r.status_code == 403 and "premium" in (r.text or "").lower():
        return "Spotify playback control needs a Spotify Premium account, sir."
    if r.status_code == 404:
        return "No active Spotify device, sir — open Spotify on a device and try again."
    if r.status_code == 401:
        return "Spotify rejected the token, sir — the login may need refreshing."
    return f"Spotify returned an error ({r.status_code}), sir."


async def _access_token() -> str:
    auth = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()
    r = await http_post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": settings.spotify_refresh_token},
    )
    return r.json()["access_token"]


async def _pick_device(c) -> str | None:
    """Return a usable device id (prefer the active one), transferring if needed."""
    r = await c.get(f"{_API}/me/player/devices")
    if r.status_code >= 400 or not r.text:
        return None
    devices = r.json().get("devices", [])
    if not devices:
        return None
    active = next((d for d in devices if d.get("is_active")), devices[0])
    return active.get("id")


async def spotify(args: dict) -> str:
    action = (args.get("action") or "now_playing").strip().lower()
    query = (args.get("query") or "").strip()
    if not (settings.spotify_client_id and settings.spotify_client_secret and settings.spotify_refresh_token):
        return not_configured(
            "Spotify",
            "a client id, secret, and a one-time user refresh token "
            "(JARVIS_SPOTIFY_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN)",
        )
    try:
        token = await _access_token()
        h = {"Authorization": f"Bearer {token}"}
        from jarvis.brain.tools.base import _client  # reuse configured client

        async with _client(headers=h) as c:
            if action == "now_playing":
                r = await c.get(f"{_API}/me/player/currently-playing")
                if r.status_code == 204 or not r.text:
                    return "Nothing is playing on Spotify right now, sir."
                err = _api_error(r)
                if err:
                    return err
                item = r.json().get("item") or {}
                name = item.get("name", "")
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                return f"Now playing: {name} by {artists}." if name else "Spotify is open but idle, sir."
            if action == "pause":
                r = await c.put(f"{_API}/me/player/pause")
                return _api_error(r) or "Paused, sir."
            if action == "play" and not query:
                dev = await _pick_device(c)
                params = {"device_id": dev} if dev else None
                r = await c.put(f"{_API}/me/player/play", params=params)
                return _api_error(r) or "Resumed playback, sir."
            if action in ("next",):
                r = await c.post(f"{_API}/me/player/next")
                return _api_error(r) or "Skipping ahead, sir."
            if action in ("previous", "prev", "back"):
                r = await c.post(f"{_API}/me/player/previous")
                return _api_error(r) or "Going back, sir."
            if action == "search" or (action == "play" and query):
                if not query:
                    return "What should I search for on Spotify, sir?"
                sr = await c.get(f"{_API}/search", params={"q": query, "type": "track", "limit": 1})
                err = _api_error(sr)
                if err:
                    return err
                items = sr.json().get("tracks", {}).get("items", [])
                if not items:
                    return f"I couldn't find '{query}' on Spotify, sir."
                track = items[0]
                dev = await _pick_device(c)
                params = {"device_id": dev} if dev else None
                pr = await c.put(f"{_API}/me/player/play", params=params, json={"uris": [track["uri"]]})
                perr = _api_error(pr)
                artists = ", ".join(a["name"] for a in track.get("artists", []))
                if perr:
                    return f"I found {track['name']} by {artists}, but {perr.lower()}"
                return f"Playing {track['name']} by {artists}, sir."
            return f"I don't know the Spotify action '{action}', sir."
    except Exception as e:  # noqa: BLE001
        return tool_error("Spotify control", e)


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "spotify",
            "description": (
                "Control Spotify playback: see what's playing, play/pause, skip, or search for "
                "a song/artist and play it. Needs an active Spotify device open somewhere."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["now_playing", "play", "pause", "next", "previous", "search"],
                        "description": "What to do.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Song/artist to search for (with action 'search' or 'play').",
                    },
                },
                "required": ["action"],
            },
        },
    },
]

HANDLERS = {"spotify": spotify}
