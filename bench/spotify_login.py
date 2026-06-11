"""One-time Spotify OAuth — produces JARVIS_SPOTIFY_REFRESH_TOKEN.

Prereqs (do these once):
  1. Create an app at https://developer.spotify.com/dashboard
  2. In the app settings, add this Redirect URI EXACTLY:  http://127.0.0.1:8888/callback
     (or whatever you set JARVIS_SPOTIFY_REDIRECT_URI to)
  3. Put the app's Client ID + Client Secret in .env:
        JARVIS_SPOTIFY_CLIENT_ID=...
        JARVIS_SPOTIFY_CLIENT_SECRET=...
  4. Run:  uv run python bench/spotify_login.py

It opens your browser, you click "Agree", and it prints the refresh token. Paste that into
.env as JARVIS_SPOTIFY_REFRESH_TOKEN and Jarvis can control playback.
"""

from __future__ import annotations

import base64
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

sys.path.insert(0, "src")
from jarvis.config import settings  # noqa: E402

SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
_code: dict[str, str] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _code["code"] = (params.get("code") or [""])[0]
        _code["error"] = (params.get("error") or [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = "Spotify authorized — you can close this tab and return to the terminal."
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

    def log_message(self, *_):  # silence the server logs
        pass


def main() -> None:
    if not (settings.spotify_client_id and settings.spotify_client_secret):
        print("Set JARVIS_SPOTIFY_CLIENT_ID and JARVIS_SPOTIFY_CLIENT_SECRET in .env first.")
        sys.exit(1)

    redirect = settings.spotify_redirect_uri
    parsed = urllib.parse.urlparse(redirect)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8888

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": SCOPES,
    })

    server = HTTPServer((host, port), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print(f"Opening your browser to authorize… (listening on {redirect})")
    webbrowser.open(auth_url)

    # Wait for the callback thread to capture the code.
    import time
    for _ in range(120):
        if _code.get("code") or _code.get("error"):
            break
        time.sleep(1)

    if _code.get("error"):
        print(f"Authorization failed: {_code['error']}")
        sys.exit(1)
    if not _code.get("code"):
        print("Timed out waiting for authorization.")
        sys.exit(1)

    auth = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()
    r = httpx.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": _code["code"],
            "redirect_uri": redirect,
        },
        timeout=20,
    )
    r.raise_for_status()
    token = r.json().get("refresh_token")
    if not token:
        print(f"No refresh token returned: {r.text}")
        sys.exit(1)
    print("\n" + "=" * 60)
    print("SUCCESS — paste this line into your .env:\n")
    print(f"JARVIS_SPOTIFY_REFRESH_TOKEN={token}")
    print("=" * 60)


if __name__ == "__main__":
    main()
