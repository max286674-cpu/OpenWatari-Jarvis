# OpenClaw fleet — Jarvis's external specialist team

> Jarvis is separate from this fleet. When a task needs deep domain work, Jarvis
> **consults** it by messaging the router **ispir** through the Gateway
> (`http://100.107.141.83:3200`), waits for the reply, then re-voices the result as himself.

## The 8 domain agents (consolidated from 30 on 2026-06-02)
- **ispir** — router / dispatcher. Jarvis always enters through ispir; ispir routes to the
  right specialist. (Jarvis does not address the others directly.)
- **finance** — investments, markets, crypto prices, ETFs, FX, economic data.
- **crypto-security** — wallets, self-custody (Trezor/Keystone), CVEs, security monitoring.
- **realty** — real estate, listings, ImmoScout24 (IS24). Voice-mode persona "Sahak".
- **business** — lead-gen (Advi Systems), holdings, channel-selling, ops.
- **creative-research** — research, papers, news, worldbuilding, writing.
- **dev-systems** — coding, infrastructure, fleet maintenance.
- **personal** — personal life, jobs, reminders, day-to-day.

> The 30 original Armenian-historical-figure personalities live on as voice-modes inside
> the 8 agents' SOUL.md files (e.g. realty speaks "as Sahak" about IS24).

## How delegation works (for Phase 2)
- Transport: Gateway `agent` RPC + `agent.wait`, streaming `assistant`/`tool`/`lifecycle` events.
- Dispatch shape: `openclaw agent --agent ispir -m "<task>" --json`.
- Jarvis narrates progress ("On it — asking the team…") then speaks the synthesized answer.
- Auth: gateway token (in `.env`, not here). Router agent configurable via `JARVIS_OPENCLAW_ROUTER_AGENT`.

## When NOT to delegate
- Quick facts, chit-chat, recall, and anything Jarvis can answer himself → answer directly
  with his own brain (freellmapi). Delegation is for real domain work, not every turn.
