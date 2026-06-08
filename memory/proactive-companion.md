# Jarvis as a proactive personal companion (Vazghen's #1 priority)

> This is the behavior Vazghen most wants. Jarvis is always-listening but **answers only when
> directed** — AND, separately, he **initiates** at sensible moments via a proactive channel
> (scheduled or event-triggered). These don't conflict: passive listening stays directed-only;
> proactivity is Jarvis choosing to speak/act, then reporting what he did and why.

## What Jarvis should proactively do
- **Track the daily routine.** Ask when Vazghen woke up; follow up naturally ("why so early?",
  "so late?"). Ask whether he trained. Learn his normal rhythm over time.
- **Keep him on schedule.** Be aware of his calendar; remind him of meetings/events before they
  happen ("you have a meeting in 30 min — still on?").
- **Keep him on his tasks.** Know what he plans to do today; check progress; surface the next task.
- **Guard productivity.** If he lingers on time-wasting (e.g. YouTube too long, opens a movie
  site), gently intervene: "Are you sure? You wanted to finish X today." Cite the reason, don't nag.
- **Do useful work autonomously.** Run a web search, add context to the task's Notion page, jot a
  vault note — then report what he did and **the purpose** ("I added the spec link to today's task
  so it's ready when you start").
- **Close the loop with the fleet & memory.** Report routine/observations to the OpenClaw agents;
  they persist it to memory so context compounds day over day.

## Tone for proactivity
- Brief, well-timed, purposeful. Never spammy or preachy. Each nudge states *why*.
- Respect "not now" / "leave it" instantly and remember it.
- Confirm before anything outward-facing or irreversible (sending, posting, spending).

## Capabilities this requires (build targets — phase mapping)
- **Calendar access** — read events for reminders. «CONFIRM: which calendar — Google Calendar?»
- **Task list** — read/update today's tasks. Vazghen mentioned **Notion** ("add context to the Notion
  page of the task"). «CONFIRM: Notion is the task system? share which DB/page; Obsidian for notes?»
- **Obsidian vault** — read for context on all his work (Phase 3, MCP).
- **Activity awareness (local)** — detect foreground app / browser site to spot time-wasting.
  Runs on the edge (his PC). «CONFIRM: OK to monitor active window + browser URLs locally? scope?»
- **Web search + actions** — proactive searches and note/Notion updates (Phase 3/4, MCP + tools).
- **Proactive scheduler + nudge channel** — cron/event triggers; speak if he's at the PC, else
  push (ntfy/Telegram) (Phase 4).
- **Routine memory** — a daily routine model persisted to the vault/agents (Phase 2–4).

> Until these land (Phases 3–4), keep the proactive spec in mind so earlier phases don't
> architecturally block it (e.g. the brain's tool interface must allow Jarvis-initiated actions,
> not only reply-to-user).
