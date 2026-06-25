"""Background task queue with live status — the "status-keeping butler" capability.

Long work (a fleet delegation that takes 20 minutes, say) shouldn't block a voice turn or leave you
in the dark. This module runs such work in the BACKGROUND, keeps a persisted record of every live
task and its latest progress, lets Watari answer "how's that going?" at any time, and — when a task
finishes — fires a completion callback (a voice note with metadata) and drops it from the queue.

Design:
  * SQLite-backed (``JARVIS_TASKS_DB_PATH``, default <repo>/jarvis_tasks.sqlite) so the queue
    survives a 24/7 brain restart; an in-memory mirror keeps reads instant.
  * ``run()`` wraps any coroutine *factory* that accepts an ``on_progress`` callback (e.g.
    ``delegate_to_fleet``); each streamed note is persisted as ``last_progress`` so a status query
    just reads the row — no second round-trip to the fleet.
  * Fail-quiet: a task that raises is recorded as ``failed`` with the error; it never crashes the brain.
  * ``on_complete(task)`` (set by the server) delivers the spoken completion note.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from jarvis.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _db_path() -> Path:
    return Path(settings.tasks_db_path) if settings.tasks_db_path else _REPO_ROOT / "jarvis_tasks.sqlite"


@dataclass
class Task:
    id: str
    title: str
    kind: str = "fleet"                  # fleet | coding | generic
    status: str = "running"             # running | done | failed
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_progress: str = ""
    result: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_s(self) -> float:
        end = self.updated_at if self.status != "running" else time.time()
        return max(0.0, end - self.started_at)

    def human_elapsed(self) -> str:
        s = int(self.elapsed_s)
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m {s % 60}s"
        return f"{s // 3600}h {(s % 3600) // 60}m"


# Completion callback: set by the server so a finished task is announced by voice. Signature: (Task).
OnComplete = Callable[[Task], Awaitable[None] | None]


class TaskQueue:
    """A small persisted registry of background tasks + a runner that keeps them updated."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._tasks: dict[str, Task] = {}
        self._bg: set[asyncio.Task] = set()
        self.on_complete: OnComplete | None = None
        self._init_db()
        self._load()

    # ---- persistence ------------------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        try:
            with self._conn() as c:
                c.execute(
                    "CREATE TABLE IF NOT EXISTS tasks ("
                    "id TEXT PRIMARY KEY, title TEXT, kind TEXT, status TEXT, "
                    "started_at REAL, updated_at REAL, last_progress TEXT, result TEXT, meta TEXT)"
                )
        except sqlite3.Error as e:
            logger.warning(f"task queue: db init failed ({e}); running in-memory only")

    def _persist(self, t: Task) -> None:
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?)",
                    (t.id, t.title, t.kind, t.status, t.started_at, t.updated_at,
                     t.last_progress, t.result, json.dumps(t.meta)),
                )
        except sqlite3.Error as e:
            logger.warning(f"task queue: persist failed ({e})")

    def _delete_row(self, task_id: str) -> None:
        try:
            with self._conn() as c:
                c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        except sqlite3.Error:
            pass

    def _load(self) -> None:
        """Reload unfinished tasks after a restart (so 'what's pending?' survives)."""
        try:
            with self._conn() as c:
                for r in c.execute("SELECT * FROM tasks WHERE status='running'"):
                    self._tasks[r["id"]] = Task(
                        id=r["id"], title=r["title"], kind=r["kind"], status=r["status"],
                        started_at=r["started_at"], updated_at=r["updated_at"],
                        last_progress=r["last_progress"] or "", result=r["result"] or "",
                        meta=json.loads(r["meta"] or "{}"),
                    )
        except sqlite3.Error:
            pass

    # ---- registry ---------------------------------------------------------------------
    def add(self, title: str, kind: str = "fleet", meta: dict | None = None) -> Task:
        t = Task(id=uuid.uuid4().hex[:8], title=title.strip()[:200], kind=kind, meta=meta or {})
        self._tasks[t.id] = t
        self._persist(t)
        return t

    def update(self, task_id: str, progress: str) -> None:
        t = self._tasks.get(task_id)
        if not t:
            return
        t.last_progress = progress.strip()[:500]
        t.updated_at = time.time()
        self._persist(t)

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def active(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == "running"]

    def find(self, topic: str) -> list[Task]:
        """Match active tasks by a word in their title (for 'how's the website going?')."""
        q = (topic or "").strip().lower()
        act = self.active()
        if not q:
            return act
        return [t for t in act if any(w in t.title.lower() for w in q.split())] or act

    def complete(self, task_id: str, status: str, result: str = "", meta: dict | None = None) -> Task | None:
        t = self._tasks.get(task_id)
        if not t:
            return None
        t.status = status
        t.result = (result or "").strip()
        t.updated_at = time.time()
        if meta:
            t.meta.update(meta)
        t.meta.setdefault("duration", t.human_elapsed())
        self._persist(t)
        return t

    def drop(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._delete_row(task_id)

    # ---- the runner -------------------------------------------------------------------
    def run(
        self,
        title: str,
        coro_factory: Callable[[Callable[[str], None]], Awaitable[str]],
        kind: str = "fleet",
        meta: dict | None = None,
    ) -> Task:
        """Enqueue background work and return its Task immediately.

        ``coro_factory(on_progress)`` must return the awaitable doing the work; each ``on_progress``
        note is persisted as the task's latest status. On finish we mark done/failed, attach
        metadata, fire ``on_complete``, and drop it from the active queue.
        """
        t = self.add(title, kind=kind, meta=meta)

        def _progress(note: str) -> None:
            self.update(t.id, note)

        async def _runner() -> None:
            try:
                result = await coro_factory(_progress)
                self.complete(t.id, "done", result=str(result),
                              meta={"complexity": _grade(t.elapsed_s)})
            except Exception as e:  # noqa: BLE001 — a failed task must never crash the brain
                logger.warning(f"background task {t.id} failed: {type(e).__name__}: {e}")
                self.complete(t.id, "failed", result=f"{type(e).__name__}: {e}")
            await self._announce(t.id)
            self.drop(t.id)

        bg = asyncio.ensure_future(_runner())
        self._bg.add(bg)
        bg.add_done_callback(self._bg.discard)
        logger.info(f"task queue: started [{t.id}] {t.title!r}")
        return t

    async def _announce(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        if not t or self.on_complete is None:
            return
        try:
            res = self.on_complete(t)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:  # noqa: BLE001
            logger.warning(f"task completion announce failed: {e}")

    def summary_line(self, t: Task) -> str:
        """A spoken status line for one task."""
        if t.status == "running":
            tail = f" — {t.last_progress}" if t.last_progress else ""
            return f"'{t.title}' is still in progress ({t.human_elapsed()} so far){tail}, sir."
        if t.status == "failed":
            return f"'{t.title}' failed after {t.human_elapsed()}, sir: {t.result[:160]}"
        return f"'{t.title}' is done ({t.meta.get('duration', t.human_elapsed())}), sir."


def _grade(elapsed_s: float) -> str:
    if elapsed_s < 30:
        return "quick"
    if elapsed_s < 300:
        return "moderate"
    return "heavy"


# Process-wide singleton (mirrors STORE / SCHEDULER).
TASKS = TaskQueue()
