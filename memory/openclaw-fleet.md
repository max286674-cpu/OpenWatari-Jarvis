# OpenClaw fleet — Jarvis's external specialist team

> Jarvis is separate from this fleet. When a task needs deep domain work, Jarvis
> **consults** it by messaging the router **ispir** through the Gateway
> (`http://100.107.141.83:3200`), waits for the reply, then re-voices the result as himself.

## The one door: ispir (team lead)
**Jarvis contacts ispir and ispir only.** Jarvis sends his request to ispir, then *waits and
watches* for ispir's reply. He never messages a specialist directly and never pre-assigns one.
ispir is the team lead: he reads Jarvis's brief, decides which specialist(s) to involve,
**explains the task to them in depth** (expanding Jarvis's brief into precise specialist
instructions), gathers their work, and returns one synthesized answer. Jarvis's job is to give
ispir a *good brief* — goal, context, and what a good answer looks like — and to re-voice the
result as himself. This keeps delegation reliable (one well-understood interface) and keeps the
specialists well-instructed (a single lead who owns task framing).

## The 8 domain agents (consolidated from 30 on 2026-06-02)
- **ispir** — router / team lead / dispatcher. The ONLY agent Jarvis talks to. ispir routes to
  the right specialist and briefs them fully. (Jarvis does not address the others directly.)
- **finance** — investments, markets, crypto prices, ETFs, FX, economic data.
- **crypto-security** — wallets, self-custody (Trezor/Keystone), CVEs, security monitoring.
- **realty** — real estate, listings, ImmoScout24 (IS24). Voice-mode persona "Sahak".
- **business** — lead-gen (Advi Systems), holdings, channel-selling, ops.
- **creative-research** — research, papers, news, worldbuilding, writing.
- **dev-systems** — coding, infrastructure, fleet maintenance.
- **personal** — personal life, jobs, reminders, day-to-day.

> The 30 original Armenian-historical-figure personalities live on as voice-modes inside
> the 8 agents' SOUL.md files (e.g. realty speaks "as Sahak" about IS24).

## How delegation works
- Transport: Gateway `agent` RPC + `agent.wait`, streaming `assistant`/`tool`/`lifecycle` events.
- Target is ALWAYS the router (`JARVIS_OPENCLAW_ROUTER_AGENT`, default `ispir`). The brain's
  `delegate_to_fleet` tool has no per-call agent parameter — by design Jarvis can't pick a
  specialist; he can only brief ispir.
- Dispatch shape: `openclaw agent --agent ispir -m "<brief>" --json`.
- Jarvis narrates progress ("On it — putting that to the team…") then waits for ispir's reply
  and speaks the synthesized answer in his own voice.
- Auth: gateway token (in `.env`, not here).

## When NOT to delegate (use your own tools first)
- Quick facts, chit-chat, recall → answer directly with your own brain (freellmapi).
- A web lookup → `web_search`; reading one page → `scrape_url`; your notes → `search_vault`.
- Telegram and Spotify → your own channel tools.
- Delegate to ispir only when the work is genuinely multi-step / specialist / needs a vault
  write — not for every turn.
