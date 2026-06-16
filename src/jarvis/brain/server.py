"""jarvis-brain WebSocket server — hosts ``JarvisAgent`` over ``shared/protocol.py``.

This is the brain endpoint the ``BrainBridge`` comment promises: a remote client (the
iPhone web client in ``clients/iphone/``, the Mentra glasses bridge, or the laptop edge)
connects over WebSocket, sends ``Hello`` + ``Utterance``, and receives streamed
``StreamEvent`` reply chunks for incremental TTS.

ONE shared ``JarvisAgent`` backs every connection, so all four devices talk to the SAME
brain + memory (the "same brain/session from phone and glasses" acceptance criterion).
Turns are serialised with a lock so a phone turn and a glasses turn can't interleave the
agent's history. A new utterance (or an explicit ``Barge``) cancels the session's in-flight
turn so Jarvis stops talking and listens.

Run it (also serves the phone client over HTTP)::

    uv run python -m jarvis.brain.server

For a phone on the same Wi-Fi, bind to all interfaces: ``JARVIS_BRAIN_HOST=0.0.0.0``.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Union
from urllib.parse import urlparse

from loguru import logger

from jarvis.brain.agent import JarvisAgent
from jarvis.config import settings
from jarvis.shared.protocol import Barge, Hello, StreamEvent, StreamKind, Utterance

ClientMessage = Union[Hello, Utterance, Barge]

# Split a reply into sentence-ish chunks so the client speaks incrementally instead of
# waiting for the whole paragraph (lower perceived latency).
_SENTENCE_RE = re.compile(r".*?[.!?](?:\s|$)|.+$", re.DOTALL)


def chunk_for_tts(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [m.group(0).strip() for m in _SENTENCE_RE.finditer(text) if m.group(0).strip()]


def parse_client_message(raw: str | bytes) -> ClientMessage | None:
    """Parse one inbound frame into a typed protocol message (or None to ignore it)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    kind = data.get("type")
    try:
        if kind == "hello":
            return Hello(**data)
        if kind == "utterance":
            return Utterance(**data)
        if kind == "barge":
            return Barge(**data)
    except Exception:  # noqa: BLE001 — a malformed frame must never kill the connection
        return None
    return None


class BrainServer:
    """Hosts a single shared ``JarvisAgent`` and drives the protocol for every client."""

    def __init__(self, agent: JarvisAgent | None = None) -> None:
        self._agent = agent or JarvisAgent()
        self._lock = asyncio.Lock()                    # serialise turns over the shared brain
        self._turns: dict[str, asyncio.Task] = {}      # session_id -> in-flight turn task
        self._sessions: dict[str, dict] = {}           # session_id -> device/headphones info
        self._conns: dict[str, object] = {}            # session_id -> live websocket (for push)
        self._tg_bridge = None                         # set in serve(): proactive VOICE to the phone

    async def warmup(self) -> None:
        await self._agent.warmup()

    # ---- proactive (Phase 10): speak unprompted to listening devices, else ntfy --------
    @property
    def is_listening(self) -> bool:
        """A device is connected and could hear an unprompted interjection right now."""
        return bool(self._conns)

    async def _broadcast_assistant(self, message: str) -> int:
        """Speak ``message`` to every connected client (no push fallback). Returns clients reached.

        Interrupts any in-flight turn first so an unprompted line (proactive nudge or a fired
        reminder) can be heard immediately.
        """
        # Record what Watari says unprompted into the shared history, so when Vazghen replies to a
        # proactive nudge or a fired reminder the brain knows what he's responding to.
        try:
            self._agent.note_proactive(message)
        except Exception:  # noqa: BLE001
            pass
        sent = 0
        for sid, ws in list(self._conns.items()):
            try:
                self._cancel(sid)  # interrupt any in-flight turn so he can speak now
                await self._send(
                    ws,
                    StreamEvent(
                        session_id=sid, kind=StreamKind.assistant, delta=message + " ", final=True
                    ),
                )
                sent += 1
            except Exception:  # noqa: BLE001 — a dead socket shouldn't block the rest
                continue
        return sent

    async def proactive_emit(self, message: str, urgency: float, speak: bool) -> str:
        """Emitter for the proactive engine: voice to connected clients, or a phone push."""
        if speak and await self._broadcast_assistant(message):
            return "voice"
        # Nobody listening (or send failed): prefer a Telegram VOICE NOTE to the phone (proactive
        # voice, 24/7, laptop-independent), then fall back to an ntfy text push.
        if self._tg_bridge is not None:
            try:
                if await self._tg_bridge.send_proactive(message):
                    return "voice-note"
            except Exception:  # noqa: BLE001
                pass
        from jarvis.brain.tools.notify import push

        ok = await push(message, title="Watari")
        return "push" if ok else "suppressed"

    def speak_reminder(self, message: str) -> None:
        """``on_speak`` hook for the scheduler: speak a fired reminder to connected clients.

        Sync (the scheduler calls it inside ``_fire`` on this loop); schedules the async broadcast.
        Phone push is NOT done here — ``scheduler._fire`` owns that via ``push_phone`` so a reminder
        isn't pushed twice. If no client is connected this is a no-op and ntfy still delivers.
        """
        try:
            asyncio.get_running_loop().create_task(
                self._broadcast_assistant(f"Reminder, sir: {message}")
            )
        except Exception:  # noqa: BLE001
            logger.warning("speak_reminder: no running loop to schedule the broadcast")

    @staticmethod
    async def _send(ws, ev: StreamEvent) -> None:
        await ws.send(ev.model_dump_json())

    async def handle_voice_request(
        self, body: bytes, content_type: str
    ) -> tuple[bytes | None, str, str]:
        """One-shot voice turn for the iPhone Siri Shortcut (no page, no WebSocket).

        Accepts EITHER a JSON body ``{"text": "..."}`` (iOS on-device dictation — fast, the
        default the Shortcut uses) OR a raw audio clip (``audio/*`` — recorded audio, transcribed
        here with Deepgram). Runs one turn through the SHARED agent under the same lock as voice and
        Telegram, then returns Watari's reply as **MP3 audio** (``audio/mpeg``) which the Shortcut
        plays. Returns ``(audio_bytes_or_None, reply_text, transcript)``; on synth failure the caller
        sends the text so Siri can read it aloud.
        """
        from jarvis.brain.voice_io import synthesize, transcribe_audio

        ct = (content_type or "").split(";")[0].strip().lower()
        text = ""
        if ct == "application/json":
            try:
                text = (json.loads(body or b"{}").get("text") or "").strip()
            except (json.JSONDecodeError, TypeError, AttributeError):
                text = ""
        elif ct.startswith("audio/") or ct == "application/octet-stream":
            text = await transcribe_audio(body, content_type=ct or "audio/m4a")
        if not text:
            return None, "I didn't catch anything, sir.", ""

        async with self._lock:
            reply = await self._agent.respond(text)
        audio = await synthesize(reply)
        return audio, reply, text

    async def handle_message(self, ws, msg: ClientMessage) -> None:
        if isinstance(msg, Hello):
            self._sessions[msg.session_id] = {
                "device_id": msg.device_id,
                "headphones_connected": msg.headphones_connected,
            }
            self._conns[msg.session_id] = ws   # track the socket for unprompted interjections
            logger.info(
                f"hello session={msg.session_id} device={msg.device_id} "
                f"headphones={msg.headphones_connected}"
            )
            await self._send(
                ws, StreamEvent(session_id=msg.session_id, kind=StreamKind.lifecycle, delta="ready")
            )
            return

        if isinstance(msg, Barge):
            self._cancel(msg.session_id)
            await self._send(
                ws,
                StreamEvent(session_id=msg.session_id, kind=StreamKind.lifecycle, delta="cancelled"),
            )
            return

        if isinstance(msg, Utterance):
            self._cancel(msg.session_id)  # a new utterance supersedes the previous turn
            self._turns[msg.session_id] = asyncio.create_task(self._run_turn(ws, msg))
            return

    def _cancel(self, session_id: str) -> None:
        task = self._turns.get(session_id)
        if task and not task.done():
            task.cancel()

    async def _run_turn(self, ws, utt: Utterance) -> None:
        sid = utt.session_id
        try:
            await self._send(
                ws, StreamEvent(session_id=sid, kind=StreamKind.lifecycle, delta="thinking")
            )
            loop = asyncio.get_running_loop()

            def progress(note: str) -> None:  # tool fillers -> spoken progress
                loop.create_task(
                    self._send(ws, StreamEvent(session_id=sid, kind=StreamKind.tool, delta=note))
                )

            # Stream sentence-by-sentence as the agent generates them, so a remote client (phone,
            # glasses, or the unified laptop edge) starts speaking sentence 1 while the rest is still
            # being written — same low-latency behaviour as the in-process edge path. We send the
            # PREVIOUS sentence as non-final and only mark the last one final=True, so the client
            # knows when the turn is complete.
            async with self._lock:
                pending: str | None = None
                async for sentence in self._agent.respond_stream(utt.text, on_progress=progress):
                    if pending is not None:
                        await self._send(ws, StreamEvent(
                            session_id=sid, kind=StreamKind.assistant, delta=pending + " ", final=False))
                    pending = sentence
                await self._send(ws, StreamEvent(
                    session_id=sid, kind=StreamKind.assistant,
                    delta=((pending + " ") if pending else ""), final=True))
        except asyncio.CancelledError:
            # Barge-in or a superseding utterance: tell the client to stop speaking.
            try:
                await self._send(
                    ws,
                    StreamEvent(
                        session_id=sid, kind=StreamKind.lifecycle, delta="cancelled", final=True
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
            raise
        except Exception:  # noqa: BLE001
            logger.exception("brain turn failed")
            await self._send(
                ws,
                StreamEvent(session_id=sid, kind=StreamKind.lifecycle, delta="error", final=True),
            )

    async def _control_handler(self, ws) -> None:
        """The laptop's PC-control executor (edge/pc_agent.py) connects here so the brain can run
        commands on the laptop. One executor at a time; results come back as pc_result frames."""
        from jarvis.brain.pc_link import PC_LINK

        PC_LINK.register(ws)
        logger.info("pc-control: laptop executor connected")
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if data.get("type") == "pc_hello":
                    PC_LINK.register(ws, data.get("host"))
                    logger.info(f"pc-control: laptop '{data.get('host')}' ready (executor {data.get('ver', '?')})")
                elif data.get("type") == "pc_result":
                    PC_LINK.resolve(data.get("id", ""), bool(data.get("ok")), str(data.get("output", "")))
        except Exception:  # noqa: BLE001
            pass
        finally:
            PC_LINK.unregister(ws)
            logger.info("pc-control: laptop executor disconnected")

    async def handler(self, ws) -> None:
        if not self._authorized(ws):
            await ws.close(code=4401, reason="unauthorized")
            return
        # Route the laptop PC-control executor to its own handler (path /control).
        try:
            from urllib.parse import urlparse as _u
            if _u(getattr(ws.request, "path", "")).path.rstrip("/").endswith("/control"):
                await self._control_handler(ws)
                return
        except Exception:  # noqa: BLE001
            pass
        logger.info("client connected")
        try:
            async for raw in ws:
                msg = parse_client_message(raw)
                if msg is not None:
                    await self.handle_message(ws, msg)
        except Exception:  # noqa: BLE001
            pass
        finally:
            # Drop any sessions bound to this socket so we don't push into a dead connection.
            for sid in [s for s, w in self._conns.items() if w is ws]:
                self._conns.pop(sid, None)
            logger.info("client disconnected")

    @staticmethod
    def _authorized(ws) -> bool:
        # Loopback dev: leave api_auth_token blank = no auth. Set it when binding to 0.0.0.0.
        if not settings.api_auth_token:
            return True
        expected = settings.api_auth_token
        # 1) Header (native/edge clients send `Authorization: Bearer <token>`).
        try:
            if ws.request.headers.get("Authorization", "") == f"Bearer {expected}":
                return True
        except Exception:  # noqa: BLE001
            pass
        # 2) Query string (BROWSERS cannot set a WS Authorization header, so the phone client
        #    connects to ws://host:8765/voice?token=<token>). Same secret, different channel.
        try:
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(getattr(ws.request, "path", "")).query)
            if (q.get("token") or [""])[0] == expected:
                return True
        except Exception:  # noqa: BLE001
            pass
        return False


async def serve(host: str | None = None, port: int | None = None) -> None:
    """Run the brain WebSocket server until cancelled."""
    import websockets

    server = BrainServer()
    await server.warmup()
    host = host or settings.brain_host
    port = port or settings.brain_port
    path = urlparse(settings.brain_ws_url).path or "/voice"
    logger.info(f"jarvis-brain listening on ws://{host}:{port}{path}")

    # HTTP sidecar (health + phone web client + the iPhone Siri-Shortcut /talk endpoint). Started
    # here, INSIDE the running loop, so the threaded HTTP handler can drive the shared async agent.
    _serve_client_http(host, settings.client_http_port, server, asyncio.get_running_loop())

    # Phase 4 — reminder scheduler. In brain-server (24/7) mode the BRAIN owns the SQLite jobstore,
    # so reminders fire even with no laptop edge connected: a fired reminder is spoken to any
    # connected client (server.speak_reminder), and scheduler._fire independently pushes it to the
    # phone via ntfy. Exactly one process must own the jobstore — run the brain server OR the
    # fully-local edge (which starts its own scheduler), not both against the same DB.
    from jarvis.brain.scheduler import SCHEDULER

    SCHEDULER.start(on_speak=server.speak_reminder)
    logger.info("reminder scheduler started (brain owns the jobstore)")

    # P1 #6 — memory hygiene. A daily job dedups near-identical learned facts, caps the active set,
    # and rotates old journals so 24/7 accumulation doesn't dull recall or re-bloat the prompt.
    try:
        from jarvis.brain.maintenance import schedule_maintenance

        schedule_maintenance(SCHEDULER)
    except Exception as e:  # noqa: BLE001 — hygiene is best-effort, never blocks startup
        logger.warning(f"memory hygiene not scheduled: {e}")

    # Phase 10 — proactive companion. Off unless JARVIS_PROACTIVE_ENABLED=true; when on, a
    # background tick may speak to listening clients (or push) within its budget + quiet hours.
    engine = None
    if settings.proactive_enabled:
        from jarvis.brain.proactive import ProactiveEngine, default_signal_sources

        engine = ProactiveEngine(
            emit=server.proactive_emit,
            sources=default_signal_sources(),
            is_listening=lambda: server.is_listening,
        )
        engine.start()

    # 24/7 reachability — inbound Telegram. DM the bot from any device (even with the laptop off);
    # the shared agent answers, so Telegram and voice share one memory + conversation context.
    from jarvis.brain.telegram_bridge import TelegramBridge

    async def _telegram_respond(text: str) -> str:
        async with server._lock:                      # serialise with voice turns over the shared brain
            return await server._agent.respond(text)

    tg_bridge = TelegramBridge(_telegram_respond, settings.telegram_default_chat)
    server._tg_bridge = tg_bridge   # proactive VOICE to the phone (proactive_emit phone fallback)
    if tg_bridge.enabled:
        asyncio.create_task(tg_bridge.run())
        logger.info("telegram bridge started — message the bot to reach Watari anywhere, 24/7")

    async with websockets.serve(server.handler, host, port, max_size=4 * 1024 * 1024):
        await asyncio.Future()  # run forever


def _serve_client_http(
    host: str, port: int, server: "BrainServer | None" = None, loop=None
) -> None:
    """Serve a liveness route + the phone web client (clients/) over HTTP in a background thread.

    ``GET /healthz`` returns 200 ``ok`` so systemd / a load balancer / a cron can check the brain
    is alive without opening a WebSocket (see deploy/vps/jarvis-brain.service). Always started even
    if the clients/ dir is missing, because the health check must work on a headless VPS.

    ``POST /talk`` is the iPhone Siri-Shortcut endpoint (no page, no WebSocket): an authenticated
    POST of JSON ``{"text": ...}`` (on-device dictation) or a raw audio clip returns Watari's reply
    as MP3 the Shortcut plays. ``server`` and ``loop`` are the running brain + its event loop, so
    the (threaded) HTTP handler can drive the shared async agent via ``run_coroutine_threadsafe``.
    """
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "clients"
    serve_dir = str(root) if root.exists() else None
    if serve_dir is None:
        logger.warning(f"client dir not found at {root}; serving /healthz only")

    def _post_authorized(handler) -> bool:
        expected = settings.api_auth_token
        if not expected:
            return True
        if handler.headers.get("Authorization", "") == f"Bearer {expected}":
            return True
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(handler.path).query)
        return (q.get("token") or [""])[0] == expected

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=serve_dir or str(Path.cwd()), **kw)

        def _route(self):
            # Path without the query string, no trailing slash — so '/iphone/?v=2' still routes.
            from urllib.parse import urlparse

            return urlparse(self.path).path.rstrip("/")

        def do_POST(self):  # noqa: N802 (http.server API) — the Siri Shortcut voice turn
            if self._route() != "/talk":
                self.send_error(404, "not found")
                return
            if server is None or loop is None:
                self.send_error(503, "brain not ready")
                return
            if not _post_authorized(self):
                self.send_error(401, "unauthorized")
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            ct = self.headers.get("Content-Type", "application/json")
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    server.handle_voice_request(body, ct), loop
                )
                audio, reply, transcript = fut.result(timeout=180)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"/talk failed: {type(e).__name__}: {e}")
                self.send_error(500, "turn failed")
                return
            # Headers carry the text too, so the Shortcut can show/read it if audio is unavailable.
            def _h(s: str) -> str:
                return (s or "").replace("\n", " ").encode("ascii", "ignore").decode()[:900]

            from urllib.parse import parse_qs, urlparse as _u

            want_text = (parse_qs(_u(self.path).query).get("format") or [""])[0] == "text"
            if want_text or not audio:
                # Bulletproof path: return JSON {reply} for a Shortcut that uses "Speak Text"
                # (Siri's own voice) — works on every iOS version, no audio-file playback needed.
                body_out = json.dumps({"reply": reply, "transcript": transcript}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body_out)))
                self.end_headers()
                self.wfile.write(body_out)
                return
            if audio:
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("X-Watari-Reply", _h(reply))
                self.send_header("X-Watari-Transcript", _h(transcript))
                self.end_headers()
                self.wfile.write(audio)
            else:
                body_out = json.dumps({"reply": reply, "transcript": transcript}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body_out)))
                self.end_headers()
                self.wfile.write(body_out)

        def do_GET(self):  # noqa: N802 (http.server API)
            if self._route() in ("/healthz", "/health"):
                body = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if serve_dir is None:
                self.send_error(404, "no client dir on this host")
                return
            # Serve the phone client with the auth token injected, so a browser (which can't set a
            # WS Authorization header) connects with no manual token paste. The HTTP port is only
            # reachable on the trusted tailnet/localhost, so embedding the token here is acceptable.
            if self._route() in ("/iphone", "/iphone/index.html"):
                idx = Path(serve_dir) / "iphone" / "index.html"
                if idx.exists():
                    html = idx.read_text(encoding="utf-8")
                    tok = (settings.api_auth_token or "").replace("</", "<\\/")
                    inject = f'<script>window.JARVIS_TOKEN="{tok}";</script>'
                    html = html.replace("</head>", inject + "</head>", 1)
                    body = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()  # end_headers() below adds the no-cache headers
                    self.wfile.write(body)
                    return
            super().do_GET()

        def end_headers(self):
            # Never let Safari serve a stale cached copy of the client — a stale page silently hides
            # new UI (e.g. the mic button) until a manual hard refresh.
            if self._route().startswith("/iphone"):
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            super().end_headers()

        def log_message(self, *args):  # keep the brain log clean
            return

    httpd = ThreadingHTTPServer((host, port), _Handler)
    where = f"http://{host}:{port}"
    logger.info(f"brain health at {where}/healthz"
                + (f"; phone client at {where}/iphone/" if serve_dir else ""))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


def main() -> None:
    host = settings.brain_host
    try:
        asyncio.run(serve(host=host))
    except KeyboardInterrupt:
        logger.info("jarvis-brain stopped")


if __name__ == "__main__":
    main()
