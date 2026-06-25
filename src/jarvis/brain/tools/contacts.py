"""Contacts tool — resolve a name to a send target before an outward action (Phase 4.3).

Watari calls this BEFORE send_email / send_telegram when the user names a person ("email John"): it
turns the name into an address/handle, asks a targeted clarification when the name is unknown or
ambiguous, and so an outward send always goes to a confirmed recipient (the send itself stays
confirm-gated). Read-only and degrades to a clear note when no contact book is configured.
"""

from __future__ import annotations

from jarvis.brain import contacts as _contacts


async def resolve_contact(args: dict) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Who should I look up, sir?"
    matches = _contacts.BOOK.resolve(name)
    if not matches:
        return (f"I don't have a contact for '{name}', sir — what's their email or Telegram, "
                "and I'll use it (say 'save it' to keep them for next time)?")
    if len(matches) > 1:
        names = "; ".join(c.name for c in matches[:6])
        return f"I have a few matches for '{name}', sir: {names}. Which one?"
    c = matches[0]
    return f"{c.name}: {c.targets()}, sir."


SCHEMAS = [
    {"type": "function", "function": {
        "name": "resolve_contact",
        "description": "Resolve a person's NAME to their email / Telegram / phone before sending or "
                       "drafting to them. Call this first whenever the user names a recipient ('email "
                       "John', 'message Anush') so the send goes to the right address. Returns the "
                       "contact's details, or asks which person if the name is unknown or ambiguous.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "The person's name to resolve."}},
            "required": ["name"]}}},
]

HANDLERS = {"resolve_contact": resolve_contact}
