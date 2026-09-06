"""B1 — intent→forced-tool router.

Narrows high-confidence intents to a single tool so weak models cannot choose the
wrong tool or fabricate a result. First matching route wins.
"""
from __future__ import annotations

import re

_ROUTES: list[tuple[re.Pattern[str], list[str]]] = [
    # Russian desktop process control MUST be deterministic and must not depend on the LLM.
    (re.compile(r"\b(?:закрой|закрыть|выключи|выключить|останови|остановить)\b", re.I), ["process_op"]),
    (re.compile(r"\b(?:открой|открыть|запусти|запустить)\b", re.I), ["open_app"]),
    (re.compile(r"\bremember (that|to|my|i|when|the|this|for)\b|\bmake a note\b|\bnote (that|down|to)\b|\bdon'?t let me forget\b|\bkeep in mind that\b", re.I), ["remember"]),
    (re.compile(r"\bforget (that|about|the|my|what)\b|\b(delete|remove|drop) (that|the|this) (memory|note)\b|\bscrub (that|it) from (memory|your memory)\b", re.I), ["forget"]),
    (re.compile(r"\b(send|shoot|fire off)\b[^.?!]{0,30}\bemail\b|\bemail\b[^.?!]{0,25}\b(saying|that|about)\b", re.I), ["send_email"]),
    (re.compile(r"\b(draft|compose|write|prepare)\b[^.?!]{0,25}\bemail\b", re.I), ["draft_email"]),
    (re.compile(r"\b(send|reply|text|message|dm)\b[^.?!]{0,30}\b(telegram|dm)\b|\b(telegram|message)\b[^.?!]{0,25}\b(saying|that)\b", re.I), ["send_telegram"]),
    (re.compile(r"\b(add|create|new|make|put)\b[^.?!]{0,20}\b(a |an |the )?task\b|\bcreate a to-?do\b|\badd (this |that )?to my (task list|notion)\b", re.I), ["notion_create_task"]),
    (re.compile(r"\b(mark|check|cross|tick|knock)\b[^.?!]{0,24}\b(off|done|complete|completed|finished)\b|\bmark (all|everything|them all|these|the rest)\b|\bi(?:'ve| have)?\s+(finished|completed|done with|wrapped up)\b|\b(complete|finish|close out|clear)\b[^.?!]{0,15}\b(task|tasks|to-?dos?|list|everything)\b", re.I), ["notion_complete_task"]),
    (re.compile(r"\b(delete|remove|drop|scrap|get rid of|take off)\b[^.?!]{0,20}\b(task|tasks|to-?do|to-?dos)\b|\b(off|from) my (task list|list|tasks)\b", re.I), ["notion_delete_task"]),
    (re.compile(r"\b(update|change|edit)\b[^.?!]{0,20}\btask\b|\badd a note to\b[^.?!]{0,20}\btask\b|\bnote on (my |the )?task\b|\bset\b[^.?!]{0,20}\btask\b[^.?!]{0,15}\b(in progress|priority|deadline|due|status)\b", re.I), ["notion_update_task"]),
    (re.compile(r"\bremind me\b|\bset (a |an )?reminder\b|\breminder to\b", re.I), ["set_reminder"]),
    (re.compile(r"\b(add|schedule|create|put|book|set up)\b[^.?!]{0,30}\b(calendar|event|meeting|appointment)\b", re.I), ["create_event"]),
    (re.compile(r"\b(open|go to|visit|fetch|scrape|read|pull up)\b[^.?!]{0,30}\b[\w-]+\.(com|org|net|io|co|dev|ai|gov|edu|uk)\b|\b(scrape|fetch) (the )?(url|page|site|website)\b", re.I), ["scrape_url"]),
    (re.compile(r"\b(my|the)\b[^.?!]{0,12}\b(calendar|agenda)\b|\b(what'?s|what is|when'?s|when is)\b[^.?!]{0,20}\b(calendar|agenda|schedule)\b|\b(do i have|any|got any)\b[^.?!]{0,20}\b(meetings?|events?|appointments?)\b|\b(when'?s|when is|what'?s|what is)\b[^.?!]{0,15}\b(next )?(meeting|appointment|event)\b|\bon my (calendar|agenda|schedule)\b", re.I), ["list_events"]),
    (re.compile(r"\b(unread|new|any|got any|check|read|got)\b[^.?!]{0,20}\b(email|emails|e-mail|mail|inbox)\b|\bwhat'?s in my inbox\b|\bcheck my (email|inbox|mail)\b", re.I), ["read_email"]),
    (re.compile(r"\b(unread|new|any|got any|check|read)\b[^.?!]{0,20}\b(telegram|dms?)\b|\bunread (messages?|dms?)\b|\bcheck (telegram|my messages)\b|\bany (new )?(telegram )?messages?\b", re.I), ["check_telegram"]),
    (re.compile(r"\b(overdue|what'?s due|due today|due this week)\b|\b(my|the) (tasks?|to-?dos?|task list)\b|\bon my plate\b|\bwhat do i (need|have) to do\b|\bwhat needs doing\b", re.I), ["notion_tasks"]),
    (re.compile(r"\b(do you remember|what do you (remember|know) about|recall)\b|\bwhat did i (say|tell you|mention) about\b|\b(when'?s|when is|what'?s|what is|where'?s|where is)\b[^.?!]{0,20}\bmy\b", re.I), ["recall"]),
    (re.compile(r"\bdefine\b|\bwhat does\b[^.?!]{0,30}\bmean\b|\bmeaning of\b|\bwhat'?s the definition of\b|\bdefinition of\b", re.I), ["define_word"]),
    (re.compile(r"\b(price|worth|value)\b[^.?!]{0,20}\b(bitcoin|btc|ethereum|eth|crypto|coin|token|solana|dogecoin|xrp)\b|\bhow much is\b[^.?!]{0,15}\b(bitcoin|btc|ethereum|eth|a coin)\b|\b(bitcoin|btc|ethereum|eth)\b[^.?!]{0,15}\b(price|worth|trading at)\b", re.I), ["crypto_price"]),
    (re.compile(r"\b(share|stock)\s+price\b|\bprice of\b[^.?!]{0,15}\b(shares?|stock)\b|\bhow(?:'?s| is)\b[^.?!]{0,15}\b(stock|shares?)\b[^.?!]{0,15}\b(doing|trading)\b|\b(stock|shares?) of\b", re.I), ["stock_price"]),
    (re.compile(r"\bweather\b|\b(temperature|forecast)\b|\bhow (hot|cold|warm) is it\b|\bis it (going to |gonna )?(rain|snow|sunny)\b", re.I), ["weather"]),
    (re.compile(r"\b(search|look up|check)\b[^.?!]{0,20}\b(vault|my notes?)\b|\bin my (vault|notes)\b", re.I), ["search_vault"]),
    (re.compile(r"\b(look up|search for|search online|google|find out|search the web)\b", re.I), ["web_search"]),
]


def forced_tools(user_text: str) -> list[str]:
    """Return high-confidence forced tool route; [] means normal model routing."""
    t = user_text or ""
    for rx, names in _ROUTES:
        if rx.search(t):
            return names
    return []


def demo() -> None:
    cases = {
        "what's on my calendar today?": "list_events",
        "do I have any new emails?": "read_email",
        "any unread telegram messages?": "check_telegram",
        "what's overdue on my task list?": "notion_tasks",
        "remember my flight is July 3rd": "remember",
        "forget that I said that": "forget",
        "define perspicacious": "define_word",
        "look up the latest news on the James Webb telescope": "web_search",
        "send an email to Bob saying hello": "send_email",
        "draft an email to the team": "draft_email",
        "what do you remember about my sister?": "recall",
        "when is my flight to London?": "recall",
        "add a task called buy milk due today": "notion_create_task",
        "mark all of these tasks as done": "notion_complete_task",
        "delete the buy milk task": "notion_delete_task",
        "update my report task priority to high": "notion_update_task",
        "search my vault for the rabbit-farm plan": "search_vault",
        "schedule a meeting tomorrow at 3": "create_event",
        "remind me to stretch in 90 minutes": "set_reminder",
        "open example.com and tell me the page heading": "scrape_url",
        "what's the current price of Bitcoin?": "crypto_price",
        "what's the share price of Apple?": "stock_price",
        "what's the weather in Yerevan today?": "weather",
        "закрой Telegram": "process_op",
        "закрой хром": "process_op",
        "выключи Discord": "process_op",
        "останови Spotify": "process_op",
        "открой Telegram": "open_app",
        "запусти калькулятор": "open_app",
        "открой Chrome": "open_app",
    }
    for text, want in cases.items():
        got = forced_tools(text)
        assert got and got[0] == want, f"{text!r} -> {got}, wanted {want}"
    for chat in ("what do you think about this?", "what's two plus two", "how are you today", "tell me a joke", "thanks, that's great"):
        assert forced_tools(chat) == [], f"{chat!r} wrongly narrowed to {forced_tools(chat)}"
    print("intent_router demo: all assertions passed")


if __name__ == "__main__":
    demo()
