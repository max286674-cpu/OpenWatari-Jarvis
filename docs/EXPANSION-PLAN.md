# Jarvis — Expansion Plan (Phases 9–12) — *making him great, not just working*

Approved direction (2026-06-11): build **all four** workstreams below, sequenced. This doc captures
the requirements verbatim and the architecture, so each phase ships a tested, runnable slice.
Foundational order: **9 Memory → 10 Proactivity → 11 Email/Calendar/Smart-home → 12 Utilities belt.**
Phase 8a (Redis) folds into Phase 9 as a memory layer.

Run-everything check stays: `uv run python bench/run_all_tests.py`.

---

## Phase 9 — Elite multi-layer memory  *(build first; the foundation)*

> Requirement: *"his memory has to be elite. Besides the Obsidian vault — which must ALWAYS be
> configured so he can read it — there are other layers of memory that make usage more efficient/
> faster."*

Six cooperating layers, fastest→deepest. Each degrades gracefully; the Markdown layers are the
source of truth, the rest are derived/accelerators.

| Layer | What | Store | Status |
|---|---|---|---|
| **L0 Working** | current conversation (rolling 12 turns) | RAM | exists |
| **L1 Learned/episodic** | one fact per note (about you, prefs, people, decisions, threads) | `memory/learned/*.md` (frontmatter) | **9 — now** |
| **L2 Journal** | per-day session summaries → continuity ("what did we do yesterday?") | `memory/journal/YYYY-MM-DD.md` | **9 — now** |
| **L3 Vault** | the canonical Obsidian knowledge base (read-only, VPS-authoritative) | `JARVIS_VAULT_PATH` mirror | exists — make **always-on + validated** |
| **L4 Hot-cache** (8a) | front the slow paths (LLM answers, web/music/vault search, session ctx across restarts) | Redis, graceful no-op | 9b |
| **L5 Semantic/graph** | embeddings + (later) Neo4j graph for associative recall | derived index | 9c / Phase 8b (later) |

**Deliverables (9 now):**
- `brain/memory.py` — `MemoryStore`: `remember(text, tags)`, `recall(query, limit)` (keyword+recency
  scorer), `recent_digest(limit)` (top facts injected at startup), `journal_append/read`, dedup.
- `brain/tools/memory.py` — `remember`, `recall` tools (the LLM calls them; he also auto-remembers
  salient facts). Wired into the tool registry.
- `context.py` — inject the learned digest into the system prompt so he starts each session already
  knowing you; load order documented.
- **Vault always-on**: startup validation that logs loudly if `JARVIS_VAULT_PATH` is unset/missing,
  and `.env.example`/README mark it **required** (not optional).
- `JarvisAgent.end_session()` — summarize the conversation to L2 journal on shutdown.
- Tests: `bench/test_phase9_memory.py` (remember/recall/recency/dedup/journal/digest/vault-validate).

**9b (Redis, soon after):** `brain/cache.py` (redis-py, `JARVIS_REDIS_URL`, no-op fallback) wrapped
around `LLMClient.complete` + web/music/vault search. Repeated question → near-zero TTFW; survives a
brain restart. **9c (vector, later):** local embedder over L1+L3 for "what's related to X?".

---

## Phase 10 — Proactive engine  *(the companion you actually asked for)*

> Requirement: *"proactivity means Jarvis can remind, can pause, can ask questions to get more
> context, can re-ask/confirm what to do, can interrupt, and can start speaking on his own just
> because he thinks it's needed to achieve better results."*

A background **tick** in the brain that, on an interval, gathers signals → asks himself *"is there
anything worth saying right now, and how urgent?"* → acts within an **interruption budget** so he's
helpful, never noisy. Plus a clarify/confirm policy woven into the agent loop. Mapping each verb:

| Verb | Mechanism |
|---|---|
| **remind** | existing scheduler (Phase 4) + proactive surfacing |
| **pause** | "hold that thought" — pause TTS / hold a task; `lockdown` protocol for full mute |
| **ask for context** | agent **clarification loop**: ambiguous request → ask a question *before* acting |
| **re-ask / confirm** | **confirmation policy** before consequential/outward actions ("send this to X — yes?"); extends the existing confirm-before-destructive rule into a general tier |
| **interrupt** | proactive tick can push a TTS frame into the live pipeline mid-idle (brain_bridge already pushes spoken reminders) |
| **speak unprompted** | tick decides to initiate when signal > relevance threshold and budget allows; else ntfy if edge offline |

**Signals the tick reads:** time-of-day + routine (from L1/`proactive-companion.md`), calendar
(Phase 11), unread Telegram/email, open threads in L1/L2, active-window (opt-in, anti-distraction).
**Deliverables:** `brain/proactive.py` (the tick + relevance scoring + interruption budget +
quiet-hours), a `ProactiveEvent` → speak/ntfy bridge, agent-loop `clarify()`/`confirm()` helpers,
config (`JARVIS_PROACTIVE_ENABLED`, tick interval, quiet hours, daily interjection budget). Tests for
budget/quiet-hours/clarify-confirm logic (no live mic needed).

---

## Phase 11 — Email (Gmail) · Calendar · Smart home

> Requirement: *"for email make sure he can access my Gmail through an app and use the Gmail app to
> send/read emails."* Plus the earlier smart-home (Home Assistant) ask.

- **Gmail (via a Google app + OAuth)** — `brain/tools/gmail.py`: `read_email` (unread/search/read),
  `draft_email`, `send_email` (**confirm-gated**, outward-facing). One-time OAuth like the existing
  `bench/spotify_login.py` pattern → refresh token in `.env`. Uses Google's API (a real Cloud "app"),
  exactly as asked. Degrades to `not_configured` until set up.
- **Google Calendar** — `brain/tools/calendar.py`: `list_events` (today/range), `create_event`,
  `find_free` — the backbone of the Phase 10 proactive engine. Same Google OAuth app as Gmail.
- **Smart home — Home Assistant** (local-first, privacy-respecting) — `brain/tools/smarthome.py`:
  `ha_call` (lights/heating/locks/scenes), `ha_state` ("is the door locked?"). Local REST/WebSocket
  API + long-lived token (`JARVIS_HA_URL`, `JARVIS_HA_TOKEN`). Confirm before locks/security.

---

## Phase 12 — Utilities belt  *(small, high-frequency, mostly no-key)*

> Requirement: *"plan for minor tools like weather API, and other small utilities — news, economy,
> stock prices, crypto prices, and everything else that are beneficial one-time-add utilities."*

One module, many cheap tools, each self-degrading. Prefer **no-key / EU-friendly** providers (reuse
the ones the OpenClaw fleet already wired where keys exist):

- **Weather** — Open-Meteo (no key). "What's the weather", commute/clothing nudges.
- **News brief** — Guardian / NewsAPI (fleet keys) or HN/no-key; a short morning headline read.
- **Crypto prices** — CoinGecko (no key). "BTC price", portfolio glance.
- **Stocks / ETFs** — Alpha Vantage / Polygon (fleet keys) or yfinance (no key).
- **Economy / FX** — ECB / exchangerate.host (no key). "USD to EUR", rates.
- **Small belt** — unit/currency convert, world clock/timezones, calculator, dictionary/synonyms
  (Datamuse), Wikipedia lookup, translate (his EN/HY/RU/DE life + language-learning project),
  package tracking, "define/spell/how-do-you-say".
- **Deliverable:** `brain/tools/utility.py` (+ `prices.py` if it grows). Most are a single `httpx`
  call; all registered at once since they degrade gracefully.

---

## Cross-cutting (apply across 9–12)
- **Audit log** of every tool action (trust/debug) — fold in during Phase 10.
- **Self-health**: Jarvis notices his own brain/ticker/tunnel/vault down and says so.
- **More protocols** (cheap, Phase-7 pattern): `focus`/`deepwork`, `briefing`/`morning`,
  `lockdown`/`privacy`, `guest`, `panic`/`safe`, `commute`, `backup`.
- Every new tool: graceful `not_configured`, a one-line entry in `memory/tools.md`, a `.env.example`
  block, and a test asserting it self-degrades.
