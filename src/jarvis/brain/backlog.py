"""Autonomous backlog worker (Phase 3.1 / recommendation 1.4).

A daily routine that turns Watari from a task *recorder* into a task *worker*: pull the owner's
overdue + undated-inbox Notion tasks and have the bounded ``TaskWorker`` attempt the SAFE work on each
(research / draft / summarise), then post the worker's result as a Notion comment on that task so the
owner sees progress next time they open it.

Safe by construction: the worker DEFERS every outward/destructive (confirm-gated) step — it never
sends, deletes, pushes, or runs shell unattended; those are listed back for the owner to approve. The
routine is opt-in (``JARVIS_BACKLOG_ENABLED``), capped per run, and fully graceful — no Notion, no
tasks DB, or no tasks just means a no-op. ``fetch``/``comment`` are injectable so the logic is
hermetically testable without Notion or a real LLM.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from loguru import logger

from jarvis.brain.worker import TaskWorker


async def attempt_backlog(
    llm: Any,
    registry: dict[str, Callable[[dict], Awaitable[str]]],
    worker_tools: list[dict[str, Any]],
    max_tasks: int = 2,
    max_steps: int = 4,
    fetch: Callable[..., Awaitable[list[dict]]] | None = None,
    comment: Callable[[str, str], Awaitable[None]] | None = None,
) -> list[dict]:
    """Attempt the safe work on the top backlog tasks; return ``[{title, result, commented}]``.

    Each task gets its own fresh worker (no shared state). A worker error on one task is logged and
    skipped — one bad task never stops the pass. The Notion comment is the routine's sanctioned output
    (writing to the owner's own task page), so it's posted directly; genuinely outward actions stay
    deferred inside the worker.
    """
    if fetch is None:
        from jarvis.brain.tools.notion import fetch_backlog_tasks as fetch
    tasks = await fetch(limit=max_tasks)
    attempted: list[dict] = []
    for t in tasks:
        title = (t.get("title") or "(untitled)").strip()
        objective = (
            f"Work on this task from the owner's backlog: '{title}'. Do the safe research and drafting "
            "needed to move it forward. Do NOT take any outward-facing or destructive action."
        )
        worker = TaskWorker(llm, registry, worker_tools, max_steps=max_steps)
        try:
            result = await worker.run(objective)
        except Exception as e:  # noqa: BLE001 — one task must not break the whole pass
            logger.warning(f"backlog worker failed on '{title}': {type(e).__name__}")
            continue
        commented = False
        page_id = (t.get("id") or "").strip()
        if page_id:
            try:
                if comment is not None:
                    await comment(page_id, result)
                else:
                    from jarvis.brain.tools.notion import notion_comment

                    await notion_comment({"page_id": page_id, "text": f"[Watari] {result}"})
                commented = True
            except Exception as e:  # noqa: BLE001 — a failed comment shouldn't lose the work
                logger.warning(f"backlog comment failed on '{title}': {type(e).__name__}")
        attempted.append({"title": title, "result": result, "commented": commented})
    if attempted:
        logger.info(f"backlog pass: attempted {len(attempted)} task(s)")
    return attempted
