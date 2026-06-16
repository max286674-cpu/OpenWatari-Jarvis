"""Protocol tool — let Jarvis run a named, password-gated routine.

Jarvis must ASK for the password first (persona/memory rule) and pass it here; the runner
verifies it before anything executes. Wrong/missing password → nothing runs.
"""

from __future__ import annotations

from jarvis.brain.protocols import describe_protocols, run_protocol as _run


async def run_protocol(args: dict) -> str:
    name = (args.get("name") or "").strip()
    password = (args.get("password") or "").strip()
    if not name:
        return f"Which protocol, sir? I have: {describe_protocols()}."
    if not password:
        return f"Protocol {name} requires the password, sir. What is it?"
    result = _run(name, password)
    return result.spoken if (result.ok and result.spoken) else result.message


SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_protocol",
            "description": (
                "Run a named protocol — a privileged routine that requires Vazghen's password. "
                "Available: 'goodnight' (stop Jarvis), 'phoenix' (restart Jarvis), 'ragnarok' "
                "(restart the laptop), 'backup' (archive memory), 'ping' (phone push test), "
                "'diagnostics' (write health report), 'auditpack' (archive audit logs), and "
                "'checkpoint' (archive non-secret context). NEVER call this without the password: "
                "if he names a "
                "protocol but hasn't given the password, ask him for it first, then call this "
                "with both. The runner rejects a wrong password."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Protocol name."},
                    "password": {"type": "string", "description": "The password Vazghen provided."},
                },
                "required": ["name", "password"],
            },
        },
    },
]

HANDLERS = {"run_protocol": run_protocol}
