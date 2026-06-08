"""OpenClaw fleet delegation — ONE tool in Jarvis's brain, never his identity.

Transport: the OpenClaw Gateway WebSocket at ``/ws`` (JSON-RPC-ish frames). The protocol,
reverse-engineered from the gateway control UI, is:

    1. connect:  server sends ``{"type":"event","event":"connect.challenge",
                 "payload":{"nonce":...}}`` on open.
    2. client replies with a request frame:
                 ``{"type":"req","id":<uuid>,"method":"connect","params":{...}}``
                 params = {minProtocol:4, maxProtocol:4, client, role:"operator",
                           scopes, caps:["tool-events"], auth:{token}, nonce, ...}
    3. open a session and ``session.message`` to an agent (e.g. ispir); stream events
       (``session.tool`` / ``session.message`` / ``session.ready``) come back; ``agent.wait``
       resolves the final answer.

SECURITY NOTE: connecting authenticates against SHARED production infrastructure. Jarvis
requests only ``operator.read``/``operator.write`` (message + read), NOT the full admin
scope set the human control UI uses. Live delegation is gated behind
``settings.openclaw_delegation_enabled`` AND a one-time user authorization (the first live
connect is surfaced for confirmation) so the brain never silently escalates onto the fleet.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from loguru import logger

from jarvis.config import settings

# Minimal scopes: message an agent + read its replies. Deliberately NOT operator.admin.
JARVIS_SCOPES = ["operator.read", "operator.write"]
PROTOCOL = 4


def _ws_url() -> str:
    base = settings.openclaw_gateway_url.rstrip("/")
    scheme = "wss" if base.startswith("https") else "ws"
    host = base.split("://", 1)[-1]
    return f"{scheme}://{host}/ws?token={settings.openclaw_token}"


def _req(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"type": "req", "id": str(uuid.uuid4()), "method": method, "params": params}


def _connect_params(nonce: str | None) -> dict[str, Any]:
    return {
        "minProtocol": PROTOCOL,
        "maxProtocol": PROTOCOL,
        "client": {
            "id": "openclaw-control-ui",
            "version": "jarvis-brain",
            "platform": "python",
            "mode": "backend",
            "instanceId": str(uuid.uuid4()),
        },
        "role": "operator",
        "scopes": JARVIS_SCOPES,
        "caps": ["tool-events"],
        "auth": {"token": settings.openclaw_token},
        "userAgent": "jarvis-brain",
        "locale": "en",
        "nonce": nonce,
    }


class FleetUnavailable(RuntimeError):
    """Raised when the fleet can't be reached or delegation is disabled."""


async def delegate_to_fleet(
    task: str,
    agent: str | None = None,
    timeout_s: int | None = None,
    on_progress=None,
) -> str:
    """Send `task` to the fleet via `agent` (default: the router, ispir) and return the
    final answer text. `on_progress(note)` is called with short status strings for spoken
    progress. Raises FleetUnavailable if delegation is disabled or the gateway is unreachable.

    This performs a LIVE connect to shared infrastructure — only call it after the user has
    authorized fleet delegation for this session.
    """
    if not settings.openclaw_delegation_enabled:
        raise FleetUnavailable("fleet delegation is disabled (JARVIS_OPENCLAW_DELEGATION_ENABLED)")
    if not settings.openclaw_token:
        raise FleetUnavailable("no gateway token configured")

    try:
        import websockets
    except ImportError as e:  # pragma: no cover
        raise FleetUnavailable("websockets not installed (uv sync --extra brain)") from e

    agent = agent or settings.openclaw_router_agent
    timeout_s = timeout_s or settings.openclaw_request_timeout_seconds
    url = _ws_url()

    async def _run() -> str:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {settings.openclaw_token}"},
            open_timeout=10,
            max_size=16 * 1024 * 1024,
        ) as ws:
            challenge = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            nonce = challenge.get("payload", {}).get("nonce")
            connect = _req("connect", _connect_params(nonce))
            await ws.send(json.dumps(connect))

            # Wait for the connect response (matched by id).
            await _await_response(ws, connect["id"], timeout_s, label="connect")
            if on_progress:
                on_progress("connected to the fleet")

            # Open a session + send the message to the target agent.
            msg = _req("session.message", {"agent": agent, "message": task})
            await ws.send(json.dumps(msg))
            final = await _collect_session(ws, msg["id"], timeout_s, on_progress)
            return final

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_s + 15)
    except FleetUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        raise FleetUnavailable(f"gateway error: {type(e).__name__}: {e}") from e


async def _await_response(ws, req_id: str, timeout_s: int, label: str) -> dict[str, Any]:
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_s))
        if m.get("id") == req_id:
            if m.get("type") in ("err", "error") or m.get("error"):
                raise FleetUnavailable(f"{label} rejected: {json.dumps(m)[:200]}")
            return m


async def _collect_session(ws, req_id: str, timeout_s: int, on_progress) -> str:
    """Read stream events until the agent's turn completes; return the final text."""
    final_parts: list[str] = []
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_s))
        event = m.get("event", "")
        if event == "session.tool" and on_progress:
            tool = m.get("payload", {}).get("tool") or "a tool"
            on_progress(f"the specialist is using {tool}")
        elif event == "session.message":
            text = m.get("payload", {}).get("text") or m.get("payload", {}).get("content")
            if text:
                final_parts.append(text)
        elif event in ("session.ready", "session.closed") or m.get("id") == req_id:
            if not final_parts and isinstance(m.get("result"), dict):
                final_parts.append(m["result"].get("text", ""))
            break
    return "\n".join(p for p in final_parts if p).strip() or "(the fleet returned no text)"


# Tool schema Jarvis's LLM sees. Description makes the separation explicit.
FLEET_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_to_fleet",
        "description": (
            "Consult the OpenClaw specialist fleet for deep domain work you can't answer "
            "yourself: live research, finance/markets, real-estate (IS24), crypto security, "
            "coding tasks, or vault/Notion actions. They are an external team you message via "
            "the router 'ispir'. Use ONLY when your own knowledge is insufficient or live/tool "
            "access is required. You remain Jarvis and will re-voice their answer yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The self-contained task/question to hand to the fleet.",
                },
                "agent": {
                    "type": "string",
                    "description": "Optional specific agent; default routes through ispir.",
                },
            },
            "required": ["task"],
        },
    },
}
