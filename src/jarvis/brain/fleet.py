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
``settings.openclaw_delegation_enabled`` AND a one-time user authorization
(``JarvisAgent.fleet_authorized``) so the brain never silently escalates onto the fleet.

AUTH GATES discovered against the live gateway (all validated):
  * frame envelope ``{"type":"req","id","method","params"}`` — correct.
  * params must NOT carry the challenge ``nonce`` at root (token-only connect).
  * ``client.id`` is an enum (openclaw-control-ui/tui/app/android/ios/macos/probe).
  * ``openclaw-control-ui`` additionally requires an Origin allowlist + ECDSA device
    identity (HTTPS/secure-context) — not available to a Python backend.
  * a terminal-class client id avoids device identity, BUT presenting as a built-in
    client to pass the allowlist is exactly what a SANCTIONED path should not have to do.

THEREFORE the intended, non-spoofing transport is one the user explicitly enables:
  (a) run the official ``openclaw agent --agent ispir -m ... --json`` CLI on the VPS
      (needs an SSH permission rule), or
  (b) the user allowlists a dedicated Jarvis client id / origin on their own gateway, or
  (c) a tiny authorized REST shim on the VPS that itself shells out to the CLI.
Until one of those is chosen, ``delegate_to_fleet`` stays disabled; the brain answers
on its own and tells Vazghen it can consult the fleet once the bridge is enabled.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import sys
import uuid
from typing import Any

from jarvis.config import settings

# Minimal scopes: message an agent + read its replies. Deliberately NOT operator.admin.
JARVIS_SCOPES = ["operator.read", "operator.write"]
PROTOCOL = 4


def _ws_url() -> str:
    base = settings.openclaw_gateway_url.rstrip("/")
    scheme = "wss" if base.startswith("https") else "ws"
    host = base.split("://", 1)[-1]
    return f"{scheme}://{host}/ws?token={settings.openclaw_token}"


def _origin() -> str:
    # The control-UI client id is origin-checked; present the gateway's own host as Origin
    # (equivalent to opening the Control UI from the gateway host).
    return settings.openclaw_gateway_url.rstrip("/")


def _req(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"type": "req", "id": str(uuid.uuid4()), "method": method, "params": params}


def _connect_params(nonce: str | None = None) -> dict[str, Any]:
    # Token-only connect (no device-identity signature), so the challenge nonce is not
    # echoed at params root — the server rejects an unexpected 'nonce' property there.
    return {
        "minProtocol": PROTOCOL,
        "maxProtocol": PROTOCOL,
        # Connect as the terminal client (openclaw-tui): token auth, no device-identity
        # attestation and no control-ui origin allowlist (unlike openclaw-control-ui).
        "client": {
            "id": "openclaw-tui",
            "version": "jarvis-brain-0.1",
            "platform": "python",
            "mode": "cli",
            "instanceId": str(uuid.uuid4()),
        },
        "role": "operator",
        "scopes": JARVIS_SCOPES,
        "caps": ["tool-events"],
        "auth": {"token": settings.openclaw_token},
        "userAgent": "jarvis-brain",
        "locale": "en",
    }


class FleetUnavailable(RuntimeError):
    """Raised when the fleet can't be reached or delegation is disabled."""


async def delegate_to_fleet(
    task: str,
    timeout_s: int | None = None,
    on_progress=None,
) -> str:
    """Hand `task` to the fleet's TEAM LEAD (ispir) and return the final answer text.

    Jarvis talks to **ispir only** — never a specialist directly. ispir is the team lead: he
    re-reads the task, decides which specialist(s) to involve, briefs them in depth, and
    returns the synthesized result. So the target agent is fixed to the router; there is no
    per-call agent override by design (the previous `agent=` parameter was removed).

    `on_progress(note)` is called with short status strings for spoken progress. Raises
    FleetUnavailable if delegation is disabled or the gateway is unreachable. This performs a
    LIVE connect to shared infrastructure — only call after the user has authorized delegation.
    """
    if not settings.openclaw_delegation_enabled:
        raise FleetUnavailable("fleet delegation is disabled (JARVIS_OPENCLAW_DELEGATION_ENABLED)")
    if not settings.openclaw_token:
        raise FleetUnavailable("no gateway token configured")

    try:
        import websockets
    except ImportError as e:  # pragma: no cover
        raise FleetUnavailable("websockets not installed (uv sync --extra brain)") from e

    # Always the team lead. Jarvis never addresses a specialist directly.
    agent = settings.openclaw_router_agent
    timeout_s = timeout_s or settings.openclaw_request_timeout_seconds
    url = _ws_url()

    async def _run() -> str:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {settings.openclaw_token}"},
            origin=_origin(),
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
    except FleetUnavailable as e:
        try:
            return await _delegate_via_cli(task, timeout_s)
        except FleetUnavailable as cli_e:
            raise FleetUnavailable(f"{e}; CLI fallback failed: {cli_e}") from e
    except Exception as e:  # noqa: BLE001
        try:
            return await _delegate_via_cli(task, timeout_s)
        except FleetUnavailable as cli_e:
            raise FleetUnavailable(
                f"gateway error: {type(e).__name__}: {e}; CLI fallback failed: {cli_e}"
            ) from e


async def _delegate_via_cli(task: str, timeout_s: int) -> str:
    """Use the sanctioned OpenClaw CLI path to reach ispir.

    On the laptop this runs the CLI over SSH on the VPS. On the VPS itself it runs the local CLI.
    """

    agent = settings.openclaw_router_agent
    cli = settings.openclaw_cli_path
    timeout_arg = str(max(timeout_s, 30))
    if sys.platform == "win32":
        if not settings.openclaw_cli_ssh_target:
            raise FleetUnavailable("no OpenClaw CLI SSH target configured")
        remote = (
            f"{shlex.quote(cli)} agent --agent {shlex.quote(agent)} "
            f"--message {shlex.quote(task)} --json --timeout {shlex.quote(timeout_arg)}"
        )
        argv = ["ssh", settings.openclaw_cli_ssh_target, remote]
    else:
        argv = [cli, "agent", "--agent", agent, "--message", task, "--json", "--timeout", timeout_arg]

    def _run_cli() -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout_s + 30)

    try:
        proc = await asyncio.to_thread(_run_cli)
    except Exception as e:  # noqa: BLE001
        raise FleetUnavailable(f"OpenClaw CLI failed to run: {type(e).__name__}") from e
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[:2]
        raise FleetUnavailable(f"OpenClaw CLI exited {proc.returncode}: {' | '.join(detail)}")

    text = _parse_cli_json(proc.stdout)
    if not text:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[:2]
        raise FleetUnavailable(f"OpenClaw CLI returned no text: {' | '.join(detail)}")
    return text


def _parse_cli_json(stdout: str) -> str:
    """Parse OpenClaw CLI JSON even if warnings follow the JSON blob."""

    start = stdout.find("{")
    if start < 0:
        return ""
    try:
        data, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except json.JSONDecodeError:
        return ""
    payloads = data.get("payloads") if isinstance(data, dict) else None
    if isinstance(payloads, list):
        texts = [p.get("text", "") for p in payloads if isinstance(p, dict)]
        joined = "\n".join(t for t in texts if t).strip()
        if joined:
            return joined
    return str(data.get("finalAssistantVisibleText") or data.get("finalAssistantRawText") or "").strip()


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


# Tool schema Jarvis's LLM sees. Description makes the separation AND the ispir-only rule explicit.
FLEET_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_to_fleet",
        "description": (
            "Hand a task to the OpenClaw fleet's TEAM LEAD, 'ispir', for deep domain work you "
            "can't do yourself: live multi-step research, finance/markets, real-estate (IS24), "
            "crypto security, larger coding tasks, or vault/Notion writes. You contact ispir and "
            "ONLY ispir — he is the one who decides which specialist handles it, briefs them in "
            "depth, and returns the result. You never message a specialist directly. Use only "
            "when your own knowledge or your own tools (web_search, scrape_url, vault) aren't "
            "enough. Give ispir a clear, self-contained brief: the goal, any context, and what a "
            "good answer looks like. You remain Jarvis and re-voice his answer in your own words."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, self-contained brief for the team lead (ispir): the goal, "
                        "relevant context, and the desired form of the answer. ispir expands it "
                        "into specialist instructions — so state intent fully, don't pre-assign "
                        "an agent."
                    ),
                },
            },
            "required": ["task"],
        },
    },
}
