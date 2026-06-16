# Watari — acknowledgement, progress, and the task queue

Three "Jarvis-from-Iron-Man" behaviours, from simplest to biggest. The first two are **built**; the
third is **designed here and is the next focused build**.

## 1. Request acknowledgement — BUILT (2026-06-17)

Watari now answers *before* he works, so there's never a silent gap:

- **Instant ack (pre-LLM):** the moment a work-like request arrives (a command, or a tool-group
  trigger), he says **"Right away, sir."** — deterministic, no model call, so it's audible in
  milliseconds even when the model's first token is seconds away. (`_immediate_ack`)
- **Contextual ack (per tool):** just before each tool runs he says what he's doing, using the
  arguments — *"Looking that up — BTC price, sir."*, *"Right away, sir — putting that to the team
  lead."*, *"Checking your calendar, sir."* (`_ack_for`, spoken via the `on_progress` channel).
- Then the tool runs and he gives the real answer.

So your example works: *"Watari, the time in Denver?"* → **"Right away, sir."** → (model decides) →
**"Getting the time, sir."** → (tool) → **"It's 6:42 in Denver, sir."** Config: `ack_before_tools`.

This also directly mitigates the TTFT latency: perceived first-word is ~0, even when the free LLM
proxy is slow.

## 2. Long-task progress ("still on it") — BUILT (2026-06-17)

Any tool that runs longer than `tool_slow_warn_seconds` (default 8 s) triggers a spoken **"This is
taking a little longer than expected, sir — still on it."**, repeating every
`tool_long_update_seconds` (default 120 s) until it finishes — so a slow tool or a long fleet
delegation never goes silent. (`_await_with_progress`; the tool keeps running, we only narrate.)

## 3. Task queue + live status keeping — DESIGNED (next build)

**The gap today:** `delegate_to_fleet` is *blocking* — it `agent.wait`s for the fleet result, so a
20-minute job ties up the turn. You can't ask anything else, and you can't query progress. The
watchdog narrates "still on it", but the turn is still blocked.

**The target (your spec):** fire long work in the background, keep a live queue of in-flight tasks,
let you ask progress any time, and announce completion by voice with metadata — then drop it from the
queue.

### Design

```
brain/tasks.py            # TaskQueue: a persisted registry of background tasks
  Task{ id, title, kind('fleet'|'coding'|…), status('queued'|'running'|'done'|'failed'),
        started_at, updated_at, agent, last_progress, result, meta{duration, complexity,
        test_results, manual_checks} }
  add() · update() · complete() · active() · get() · drop()   (SQLite-backed, survives restart)

delegate_to_fleet(..., background=True)   # returns a task_id immediately; spawns a worker that
                                          # runs agent.wait, streams ispir progress into the Task,
                                          # and on finish calls the completion notifier
tools/tasks.py            # `list_tasks` / `task_status(id|topic)` — read the queue; for a fleet
                          # task, also pull ispir's latest related session lines for live detail
server/proactive wiring   # on completion -> a VOICE note: "Done, sir — the portfolio site update
                          # took 24 minutes; dev-systems rebuilt the hero + case studies, tests
                          # green; manually check the contact form." then queue.drop(id)
```

### Behaviour it unlocks

- *"Contact the fleet, tell ispir to have dev-systems redo the portfolio site — not generic."* →
  **"On it, sir — I've handed that to the team, I'll let you know when it's done."** (returns at once)
- *(8 min later)* *"How's the website going?"* → `task_status` reads the queue + ispir's latest
  session → **"Still in progress, sir — dev-systems is on the case-studies section, about 60% there."**
- *(on finish)* a proactive **voice note** with: time taken, complexity, test/verify results, and
  what you should check manually — then the task leaves the queue.

### Why it's a separate build

It needs (a) async fleet delegation (today it's synchronous), (b) a persisted queue store, (c) a
status tool that can read ispir's sessions, and (d) the completion-notifier wired into the proactive
voice channel — each with its own tests. It's ~3 modules + a tool + wiring. Done carefully so the
existing confirm-gate, audit, and memory paths are untouched.

**Status:** items 1 & 2 shipped and tested (`bench/test_companion_safety.py`). Item 3 is ready to
build on approval.
