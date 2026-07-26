# Task-manager cleanup — triage and tidy the backlog

Use this when Vazghen says "clean up my tasks", "sort out my to-do list", "tidy the backlog", or
during the daily/weekly pass. Goal: turn a messy task DB into a short, honest, actionable list —
never silently delete anything he might still want.

## The pass (in order)

1. **Read the state first.** `notion_tasks()` to pull what's due today / overdue / upcoming. Don't
   act blind — see the whole list before touching anything.
2. **Overdue but still real → re-date, don't delete.** For a task that's overdue but clearly still
   wanted, propose a new date and `notion_update_task(id, deadline=...)`. Say why ("moved 3 overdue
   items to this week").
3. **Done-in-reality → complete it.** If he says something's finished, `notion_complete_task(id)`.
   Never mark done on a guess — confirm first.
4. **Duplicates → keep one, comment the merge.** If two tasks are the same, keep the one with the
   better date/notes, `notion_comment(other_id, "duplicate of <title>")`, and only
   `notion_delete_task` the dupe **after** he confirms.
5. **Stale / vague → ask, don't archive.** A task with no date and no clear next action: ask one
   question ("'look into stuff' from March — still relevant?"). Archive only on a yes.
6. **Surface the top 3.** End by reading back the 3 most important open items so he leaves with a
   clear next action, not just a tidier list.

## Hard rules

- **`notion_delete_task` is destructive (archives the row) and confirm-gated.** Never delete without
  an explicit yes. Re-dating and completing are frictionless; deleting is not.
- **Batch your proposal, act on confirmation.** Say "I'd re-date these 3, complete these 2, and
  there are 2 dupes — want me to?" then do it. Don't fire 9 separate confirmations.
- **Report what changed and why**, in one or two spoken sentences. "Cleared 4 stale items, moved 3
  overdue to Thursday, and TT the deposit dispute is your top open task."
- Only touches the Notion tasks DB he shared with the integration — you can't see anything else.

## When there's nothing to do

If the list is already clean, say so plainly ("Your task list's in good shape, sir — three open,
none overdue.") and stop. A cleanup pass that finds nothing is a success, not a reason to invent work.
