"""Document tools — "read this doc and answer" (Phase 4.4).

Three read-only tools over a temporary one-document index (`brain/docstore.py`): open a local file,
ask grounded questions about it, and close it. The model summarises/answers from the returned text,
so answers stay grounded in the document instead of the model's memory.
"""

from __future__ import annotations

from jarvis.brain import docstore


async def read_document(args: dict) -> str:
    path = (args.get("path") or "").strip()
    if not path:
        return "Which file should I read, sir? Give me its path."
    ok, msg = docstore.STORE.load(path)
    if ok:
        msg += (" Ask me anything about it with 'ask the document …', or say 'close the document' "
                "when you're done.")
    return msg


async def ask_document(args: dict) -> str:
    if not docstore.STORE.loaded():
        return "No document is open, sir — point me at one first with 'read this file …'."
    query = (args.get("query") or "").strip()
    if not query:
        return "What would you like to know from the document, sir?"
    hits = docstore.STORE.ask(query)
    if not hits:
        return (f"I couldn't find anything about that in '{docstore.STORE.source}', sir.")
    joined = "\n---\n".join(hits)
    return (f"From '{docstore.STORE.source}', the most relevant parts, sir:\n{joined}")


async def close_document(_args: dict) -> str:
    return docstore.STORE.clear()


SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_document",
        "description": "Open a LOCAL document (text, Markdown, code, CSV, JSON; PDF if a reader is "
                       "installed) into a temporary index so you can answer questions grounded in it. "
                       "Use for 'read this file and summarise it', 'what does this doc say about X'.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Local file path to read."}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "ask_document",
        "description": "Ask a question about the currently-open document; returns the most relevant "
                       "passages to answer from. Read the document first with read_document.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "The question to answer from the document."}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "close_document",
        "description": "Close the open document and drop its temporary index when you're done with it.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]

HANDLERS = {
    "read_document": read_document,
    "ask_document": ask_document,
    "close_document": close_document,
}
