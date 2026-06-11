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

    async def warmup(self) -> None:
        await self._agent.warmup()

    # ---- proactive (Phase 10): speak unprompted to listening devices, else ntfy --------
    @property
    def is_listening(self) -> bool:
        """A device is connected and could hear an unprompted interjection right now."""
        return bool(self._conns)

    async def proactive_emit(self, message: str, urgency: float, speak: bool) -> str:
        """Emitter for the proactive engine: voice to connected clients, or a phone push."""
        if speak and self._conns:
            sent = 0
            for sid, ws in list(self._conns.items()):
                try:
                    self._cancel(sid)  # interrupt any in-flight turn so he can speak now
                    await self._send(
                        ws,
                        StreamEvent(
                            session_id=sid, kind=StreamKind.assistant,
                            delta=message + " ", final=True,
                        ),
                    )
                    sent += 1
                except Exception:  # noqa: BLE001 — a dead socket shouldn't block the rest
                    continue
            if sent:
                return "voice"
        # Nobody listening (or send failed): fall back to a phone push.
        from jarvis.brain.tools.notify import push

        ok = await push(message, title="Jarvis")
        return "push" if ok else "suppressed"

    @staticmethod
    async def _send(ws, ev: StreamEvent) -> None:
        await ws.send(ev.model_dump_json())

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

            async with self._lock:
                reply = await self._agent.respond(utt.text, on_progress=progress)

            chunks = chunk_for_tts(reply)
            if not chunks:
                await self._send(
                    ws,
                    StreamEvent(session_id=sid, kind=StreamKind.assistant, delta="", final=True),
                )
                return
            for i, chunk in enumerate(chunks):
                await self._send(
                    ws,
                    StreamEvent(
                        session_id=sid,
                        kind=StreamKind.assistant,
                        delta=chunk + " ",
                        final=(i == len(chunks) - 1),
                    ),
                )
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

    async def handler(self, ws) -> None:
        if not self._authorized(ws):
            await ws.close(code=4401, reason="unauthorized")
            return
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
        try:
            auth = ws.request.headers.get("Authorization", "")
        except Exception:  # noqa: BLE001
            auth = ""
        return auth == f"Bearer {settings.api_auth_token}"


async def serve(host: str | None = None, port: int | None = None) -> None:
    """Run the brain WebSocket server until cancelled."""
    import websockets

    server = BrainServer()
    await server.warmup()
    host = host or settings.brain_host
    port = port or settings.brain_port
    path = urlparse(settings.brain_ws_url).path or "/voice"
    logger.info(f"jarvis-brain listening on ws://{host}:{port}{path}")

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

    async with websockets.serve(server.handler, host, port, max_size=4 * 1024 * 1024):
        await asyncio.Future()  # run forever


def _serve_client_http(host: str, port: int) -> None:
    """Serve the phone web client (clients/) over HTTP in a background thread."""
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "clients"
    if not root.exists():
        logger.warning(f"client dir not found at {root}; skipping HTTP client server")
        return
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = ThreadingHTTPServer((host, port), handler)
    logger.info(f"phone client served at http://{host}:{port}/iphone/")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


def main() -> None:
    host = settings.brain_host
    _serve_client_http(host, settings.client_http_port)
    try:
        asyncio.run(serve(host=host))
    except KeyboardInterrupt:
        logger.info("jarvis-brain stopped")


if __name__ == "__main__":
    main()
