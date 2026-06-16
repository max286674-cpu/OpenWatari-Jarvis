# OpenWatari — agent/companion audit (2026-06-16)

A critical, code-grounded review of OpenWatari as an LLM agent, companion, and identity — what can
go wrong in real human interaction, the root causes, and what was fixed vs. what's tracked. Every
claim here was checked against the source and, where relevant, a test was added or run.

> **Bottom line for the publish gate:** the test suite is **green (27/0/1)** and the efficiency
> report meets every target **except streaming TTFT** (1333 ms vs a 1200 ms goal — ~11% over,
> model/network-bound). Four substantive correctness/safety gaps found in this audit are **fixed and
> tested**. Recommendation: **stay private** until TTFT is either accepted as the goal-with-tolerance
> or brought under 1200 ms (options below). Everything else is publish-ready.

---

## Efficiency (the gate)

`uv run python bench/efficiency_report.py`:

| Metric | Measured | Target | Verdict |
|---|---|---|---|
| System prompt size | ~1835 tok | ≤ 2000 tok | OK |
| Tool surface (per turn) | 43 core (67 in registry) | ≤ 48 | OK |
| L1 recall (keyword) | 0.90 ms | ≤ 5 ms | GOOD |
| L1 digest (startup) | 0.82 ms | ≤ 5 ms | GOOD |
| L4 cache miss→hit | 53 ms → 0.003 ms | hit ≪ miss | GOOD |
| Utility cold→warm | 2412 ms → ~0 ms | warm ~0 | GOOD |
| Brain full turn (direct) | 976 ms | ≤ 2500 ms | GOOD |
| **Brain TTFT (stream)** | **1333 ms** | **≤ 1200 ms** | **TUNE** |

TTFT root cause: the primary model (`llama-3.3-70b-versatile`) reached over the network via the
freellmapi proxy. The prompt and tool surface are already lean, so the remaining cost is model +
network round-trip, not our code. Options, cheapest first: (a) accept 1200 ms as a soft goal — 1333
ms is still snappy; (b) keep a warm connection / HTTP-2 keep-alive to the proxy; (c) co-locate the
proxy with the brain on the VPS to cut RTT; (d) use a faster small model for the *first* token then
hand off. No code change is required to ship; this is a tuning dial.

---

## Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **Critical** | Confirmation tier was **not enforced in code** — only requested in the prompt | **Fixed** |
| 2 | High | Proactive nudges weren't **durably persisted** → "that thing you suggested last week" was unrecoverable | **Fixed** |
| 3 | High | No way for Watari to **write into the vault** (user-requested) | **Fixed** |
| 4 | Medium | No **smart session reset** → stale anaphora bled across long idle gaps | **Fixed** |
| 5 | Medium | Streaming **TTFT** slightly over target | Tracked (tuning) |
| 6 | Medium | The shared brain uses **one history for all devices** (cross-device interleave) | Tracked / by-design |
| 7 | Low | A turn **cancelled mid-stream** can leave a user message with no assistant reply | Tracked |
| 8 | Low | A proactive line is recorded as "said" even when only **pushed** (not heard aloud) | Accepted |
| 9 | Cosmetic | Internal prompts/log strings still say "Jarvis"/"Vazghen" while the persona is Watari | Tracked |

All fixes are covered by `bench/test_companion_safety.py` (20 checks) and verified in the full suite.

---

### 1 — Confirmation tier is now enforced (Critical, fixed)

**Root cause.** `confirm_required()` / `CONFIRM_TIER` existed in `brain/proactive.py` and SECURITY.md
claimed they were "enforced as a policy," but **nothing in the execution path called them** —
`brain/agent.py` never imported them. Confirmation depended entirely on the LLM obeying the system
prompt. With a weak primary/fallback model (exactly the kind that skips the confirm step), a single
hallucinated tool call could `send_email`, `file_op` delete, or `run_powershell` with no human yes.

**Fix.** `JarvisAgent._execute_calls` now calls `confirm_required(name, args)` for every tool. A
confirm-tier call with no standing grant is **blocked** (not executed): the model receives a
`CONFIRM_REQUIRED` sentinel, reads the action back, and the held call runs only after the next user
turn affirms it (`_is_affirmation`, e.g. "yes", "go ahead", "send it"). One "yes" authorises exactly
one action — the grant is consumed. A non-affirmative new utterance supersedes the pending one. Reads
and lookups are never gated. Verified: the gate blocks `send_email` without a yes, runs it after a
grant, consumes the grant, and never gates `get_time`.

### 2 — Proactive memory is now durable (High, fixed)

**Root cause.** `note_proactive()` only appended to the rolling working history, which is trimmed to
12 turns and lost on restart. So referring back to a proactive suggestion **one minute later** worked,
but **ten days later** was impossible — the nudge had vanished from all memory.

**Fix.** `note_proactive()` now also writes the nudge to the L2 journal
(`[proactive] Watari said unprompted: …`). It stays in working memory for immediate "yes, do it" and
in durable memory for "what was that thing you suggested last week?" (answerable via `read_journal` /
`recall`). Verified by test.

### 3 — Vault writing (High, fixed)

**Root cause.** The vault was read-only by design because on the laptop it's a one-way VPS→local sync
*target* (local edits get clobbered). But the brain runs on the **VPS where the vault is
authoritative**, so writing there is safe — and the user wants Watari to keep the knowledge base alive
himself.

**Fix.** New `write_vault` tool (append or create a note, scoped safely inside the vault, no
traversal) plus `JARVIS_VAULT_WRITABLE` (default **false**). It's a no-op with a spoken explanation
unless the host owns the vault, so it can never clobber the laptop mirror. Verified: refuses when not
writable; creates/appends when writable; blocks path traversal.

### 4 — Smart session reset (Medium, fixed)

**Root cause.** Working history was only ever trimmed to the last 12 turns — never reset on a topic
change or a long idle gap. After talking at 9 a.m. and again at 6 p.m., a terse "set it back" could
bind to a stale "it" from the morning.

**Fix.** `JARVIS_SESSION_IDLE_RESET_MINUTES` (default 180): when the gap since the last turn exceeds
it, the brain journals the prior conversation (background, non-blocking) and clears working memory —
durable memory (L1/L2/L3) untouched. A public `reset_session()` also lets the server/edge offer an
explicit "start a new conversation." Verified by test.

---

### 5 — TTFT (tracked). See the efficiency section. No code change required to ship.

### 6 — Single shared history across devices (tracked / by-design)

The shared brain (`brain/server.py`) runs **one** `JarvisAgent` with **one** history for all
connected devices, which is what makes "ask on the laptop, follow up on the phone" work. The trade-off
is that two *unrelated* conversations on two devices interleave. The smart reset (#4) limits staleness
over time. True per-device/per-speaker sessions (keyed by connection or speaker-ID) would be a larger
change; documented as a deliberate trade-off for now.

### 7 — Cancelled-mid-stream turn (tracked, low)

If a streaming turn is cancelled (e.g. a proactive interjection interrupts it), the user message was
appended but the assistant reply may not be, so the next turn can present two consecutive user
messages. The existing empty-assistant guard prevents the worst case (a 400 on replay); a tidy
follow-up is to append a short placeholder assistant turn on cancel. Low severity.

### 8 — Proactive recorded even when only pushed (accepted)

`note_proactive` records the line regardless of whether it was spoken, sent as a voice note, or pushed.
This is the right call for "answer it later" continuity; the minor cost is that a purely-pushed line is
in history as if "said." Accepted.

### 9 — Branding in internal strings (tracked, cosmetic)

Some hardcoded log/journal/system strings still say "Jarvis"/"Vazghen" while the persona is "Watari".
The model always speaks as the persona, so this is cosmetic; a later pass can parametrise the
principal's and assistant's names. The package name `jarvis` stays (code identifier).

---

## Human-interaction scenarios reviewed

- **"yes, do it" to a just-said proactive nudge** — works (working memory) and now the nudge is also
  journalled.
- **Referring to a nudge from days ago** — now answerable via the journal (#2).
- **A terse anaphoric command after a long break** — no longer binds to stale context (#4).
- **A weak model trying to send/delete without asking** — now physically blocked (#1).
- **Ambiguous "do it" with no object** — `needs_clarification` heuristic prompts a question (note: this
  helper is advisory in the prompt; the hard safety net is the enforced confirm tier).
- **Memory recall across turns** — verified live ("remember my rabbit farm is in Armavir" → recalled
  two turns later).
- **Self-improvement loop** — `bench/test_self_improve.py` passes; `background_review` distils durable
  facts into L1 every few turns and at session end, off the hot path.

## Recommendation

Ship to private use now. Before flipping the repo public: decide TTFT (accept ≤1.33 s or apply one of
the tuning options), then re-run `bench/run_all_tests.py` (green) and `bench/efficiency_report.py`.
