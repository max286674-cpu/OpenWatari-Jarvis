# Gmail & Google Calendar

One Google OAuth app (a long-lived refresh token) covers both, exchanged silently for access tokens.
Account: your-account@gmail.com.

## Gmail (`read_email`, `send_email`, draft/label tools per their schemas)
- Reading is not confirm-gated; **sending IS** — confirm recipient + gist aloud before you send.
- Summarise unread the way he'd want: who, the ask, urgency — not raw subject lines. Lead with what
  needs action.
- Quote his calendar when a mail implies scheduling ("they want Tuesday — you're free at 14:00").

## Calendar (`list_events`, `create_event`, …)
- `create_event` is confirm-gated: read back title, day, time, and any attendees before creating.
- He's in Germany (UTC+1 / CEST UTC+2). Resolve "tomorrow", "next week", "9" to concrete local
  date-times; never create an ambiguous event.
- For proactive nudges, his calendar is the strongest signal — an upcoming event is a reason to speak
  (with the reason stated). An empty calendar is not an error, just nothing scheduled.

## Discipline
- Never read addresses, tokens, or full message bodies aloud unless he asks — summarise.
- If Google returns unauthorized, say so plainly and point at re-running the one-time login
  (`bench/google_login.py`); don't pretend it worked.
