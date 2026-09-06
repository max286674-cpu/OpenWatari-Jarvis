"""High-confidence intent router."""
from __future__ import annotations
import re

_ROUTES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(?:посмотри|смотри|глянь|покажи|что (?:у меня|там) на (?:экране|рабочем столе)|найди на экране|нажми|кликни|щелкни|выбери|перетащи|введи на компьютере|сделай на компьютере|работай на компьютере|открой в окне|заполни в окне|поставь курсор|управляй компьютером|управляй экраном)\b", re.I), ["computer_use"]),
    (re.compile(r"\b(?:закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить)\b", re.I), ["process_op"]),
    (re.compile(r"\b(?:открой|открыть|запусти|запустить|включи|включить)\b", re.I), ["open_app"]),
    (re.compile(r"\bremember (that|to|my|i|when|the|this|for)\b|\bmake a note\b|\bnote (that|down|to)\b|\bdon'?t let me forget\b|\bkeep in mind that\b|\bзапомни\b|\bзапиши в память\b", re.I), ["remember"]),
    (re.compile(r"\bforget (that|about|the|my|what)\b|\b(delete|remove|drop) (that|the|this) (memory|note)\b|\bзабудь\b", re.I), ["forget"]),
    (re.compile(r"\b(send|shoot|fire off)\b[^.?!]{0,30}\bemail\b|\bemail\b[^.?!]{0,25}\b(saying|that|about)\b|\bотправь\b[^.?!]{0,30}\b(?:почту|письмо)\b", re.I), ["send_email"]),
    (re.compile(r"\b(draft|compose|write|prepare)\b[^.?!]{0,25}\bemail\b", re.I), ["draft_email"]),
    (re.compile(r"\b(send|reply|text|message|dm)\b[^.?!]{0,30}\b(telegram|dm)\b|\b(telegram|message)\b[^.?!]{0,25}\b(saying|that)\b", re.I), ["send_telegram"]),
    (re.compile(r"\bremind me\b|\bset (a |an )?reminder\b|\breminder to\b|\bнапомни\b|\bпоставь напоминание\b", re.I), ["set_reminder"]),
    (re.compile(r"\b(add|schedule|create|put|book|set up)\b[^.?!]{0,30}\b(calendar|event|meeting|appointment)\b|\b(?:создай|добавь|поставь)\b[^.?!]{0,30}\b(?:событие|встречу|календар)\b", re.I), ["create_event"]),
    (re.compile(r"\b(my|the)\b[^.?!]{0,12}\b(calendar|agenda)\b|\bwhat'?s?\b[^.?!]{0,20}\b(calendar|agenda|schedule)\b|\bчто у меня\b[^.?!]{0,20}\b(?:в календаре|по расписанию)\b", re.I), ["list_events"]),
    (re.compile(r"\b(check|read|unread|new|any)\b[^.?!]{0,20}\b(email|emails|e-mail|mail|inbox)\b|\b(?:проверь|прочитай)\b[^.?!]{0,20}\b(?:почту|письма|входящие)\b", re.I), ["read_email"]),
    (re.compile(r"\b(check|read|unread|new|any)\b[^.?!]{0,20}\b(telegram|dms?)\b", re.I), ["check_telegram"]),
    (re.compile(r"\b(overdue|what'?s due|due today|due this week)\b|\b(my|the) (tasks?|to-?dos?|task list)\b", re.I), ["notion_tasks"]),
    (re.compile(r"\b(do you remember|what do you (remember|know) about|recall)\b|\bwhat did i (say|tell you|mention) about\b|\bчто ты помнишь\b|\bвспомни\b", re.I), ["recall"]),
    (re.compile(r"\bdefine\b|\bwhat does\b[^.?!]{0,30}\bmean\b|\bmeaning of\b", re.I), ["define_word"]),
    (re.compile(r"\b(price|worth|value)\b[^.?!]{0,20}\b(bitcoin|btc|ethereum|eth|crypto|coin|token|solana|dogecoin|xrp)\b", re.I), ["crypto_price"]),
    (re.compile(r"\b(share|stock)\s+price\b|\bprice of\b[^.?!]{0,15}\b(shares?|stock)\b", re.I), ["stock_price"]),
    (re.compile(r"\bweather\b|\b(temperature|forecast)\b|\bhow (hot|cold|warm) is it\b|\bпогода\b|\bтемпература\b", re.I), ["weather"]),
    (re.compile(r"\b(search|look up|check)\b[^.?!]{0,20}\b(vault|my notes?)\b|\bin my (vault|notes)\b|\b(?:поищи|найди)\b[^.?!]{0,20}\b(?:в заметках|в памяти)\b", re.I), ["search_vault"]),
    (re.compile(r"\b(look up|search for|search online|google|find out|search the web)\b|\b(?:поищи|найди|посмотри в интернете|проверь в интернете)\b", re.I), ["web_search"]),
]

def forced_tools(user_text: str) -> list[str]:
    t = user_text or ""
    for rx, names in _ROUTES:
        if rx.search(t):
            return names
    return []
