"""Coding & self-improvement tools (Phase 13) — Jarvis can read, edit, test, and *safely* commit.

This is what lets Jarvis improve his own codebase over time, with a hard safety rail: **every change
is reversible through git, and nothing destructive is reachable.** Concretely:

* **Repo-scoped file I/O** — `read_source` / `write_source` / `list_source` operate only inside the
  repo, and refuse secrets (`.env`, `*.session`, `voiceprint.json`, `audit/`, `backups/`, `.git/`).
* **Verify before trusting** — `run_tests` runs the full suite, `lint` runs ruff. The
  self-improvement skill tells him to test before he commits.
* **Reversible git only** — `git_status` / `git_diff` / `git_log` (read) and `git_new_branch` /
  `git_commit` / `git_push` / `git_revert` (write). The write set is deliberately limited to
  *additive* history: a revert is a new commit, never a rewrite. There is **no** reset, force-push,
  rebase, clean, or branch-delete tool, so he can't lose your work.

Commits, pushes, and source writes are confirm-gated (they're in `proactive.CONFIRM_TIER`), so the
persona reads back what it's about to do and waits for a yes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from jarvis.brain.tools.base import clip, tool_error
from jarvis.config import settings

_REPO = Path(__file__).resolve().parents[4]

# Top-level dirs/files Jarvis may never read or write (secrets, runtime state, vcs internals).
_BLOCKED_TOP = {".git", ".venv", ".jarvis-browser", "audit", "backups", "node_modules"}
_BLOCKED_NAMES = {"voiceprint.json", "jarvis_jobs.sqlite"}
_BLOCKED_SUFFIX = {".session", ".session-journal"}

# Git subcommands Jarvis is allowed to run. Anything that rewrites or discards history is absent
# by design (no reset/rebase/clean/checkout-of-files/push --force/branch -D).
_GIT_READ = {"status", "diff", "log", "branch", "show", "rev-parse"}


def _is_secret(p: Path) -> bool:
    name = p.name
    return (
        name == ".env"
        or name.startswith(".env")
        or name in _BLOCKED_NAMES
        or p.suffix in _BLOCKED_SUFFIX
    )


def _safe_path(rel: str) -> Path | None:
    """Resolve a repo-relative path, or None if it escapes the repo or hits a blocked target."""
    rel = (rel or "").strip().strip("/\\")
    if not rel:
        return None
    try:
        p = (_REPO / rel).resolve()
    except Exception:  # noqa: BLE001
        return None
    if p != _REPO and _REPO not in p.parents:
        return None  # path traversal outside the repo
    parts = p.relative_to(_REPO).parts
    if parts and parts[0] in _BLOCKED_TOP:
        return None
    if _is_secret(p):
        return None
    return p


def _enabled() -> str | None:
    if not settings.coding_tools_enabled:
        return "My coding tools are switched off right now, sir (JARVIS_CODING_TOOLS_ENABLED)."
    return None


async def _run(cmd: list[str], timeout: int = 240) -> tuple[int, str]:
    """Run a subprocess in the repo, return (rc, combined output)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(_REPO),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, f"timed out after {timeout}s"
    return proc.returncode or 0, (out or b"").decode("utf-8", "replace")


async def _git(*args: str, timeout: int = 60) -> tuple[int, str]:
    return await _run(["git", *args], timeout=timeout)


# ---- file I/O ---------------------------------------------------------------------------

async def read_source(args: dict) -> str:
    if (off := _enabled()):
        return off
    p = _safe_path(args.get("path", ""))
    if p is None:
        return "I can't read that path, sir — it's outside the project or a protected file."
    if not p.is_file():
        return f"There's no file at {args.get('path')}, sir."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return f"{args.get('path')} ({len(text)} chars):\n{clip(text, 6000)}"
    except Exception as e:  # noqa: BLE001
        return tool_error("read source", e)


async def write_source(args: dict) -> str:
    if (off := _enabled()):
        return off
    p = _safe_path(args.get("path", ""))
    if p is None:
        return "I won't write there, sir — it's outside the project or a protected file."
    content = args.get("content")
    if content is None:
        return "What should I write into that file, sir?"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.is_file()
        p.write_text(content, encoding="utf-8")
        verb = "Updated" if existed else "Created"
        return (f"{verb} {args.get('path')}, sir ({len(content)} chars). "
                "It's uncommitted — run the tests, then commit so it's reversible.")
    except Exception as e:  # noqa: BLE001
        return tool_error("write source", e)


async def list_source(args: dict) -> str:
    if (off := _enabled()):
        return off
    p = _safe_path(args.get("path") or ".")
    if p is None or not p.is_dir():
        return "That's not a folder I can list, sir."
    try:
        entries = sorted(
            (("📁 " if c.is_dir() else "") + c.name) for c in p.iterdir()
            if c.name not in _BLOCKED_TOP and not _is_secret(c)
        )
        return f"{args.get('path') or '.'}: " + ", ".join(entries[:80])
    except Exception as e:  # noqa: BLE001
        return tool_error("list source", e)


# ---- verify -----------------------------------------------------------------------------

async def run_tests(args: dict) -> str:
    if (off := _enabled()):
        return off
    rc, out = await _run(
        ["uv", "run", "python", "bench/run_all_tests.py"], timeout=420
    )
    tail = "\n".join(line for line in out.splitlines() if "passed," in line or "PASS" in line or "FAIL" in line)
    verdict = "all green" if rc == 0 else "FAILURES — do not commit yet"
    return f"Test run {verdict}, sir.\n{clip(tail or out, 1500)}"


async def lint(args: dict) -> str:
    if (off := _enabled()):
        return off
    target = (args.get("path") or "src bench").strip()
    p = _safe_path(target.split()[0]) if " " not in target else _REPO
    if " " not in target and p is None:
        return "I can't lint that path, sir."
    rc, out = await _run(["uv", "run", "ruff", "check", *target.split()], timeout=120)
    return ("Lint clean, sir." if rc == 0 else f"Ruff found issues, sir:\n{clip(out, 1500)}")


# ---- git (reversible only) --------------------------------------------------------------

async def git_status(args: dict) -> str:
    if (off := _enabled()):
        return off
    rc, out = await _git("status", "--short", "--branch")
    return clip(out or "clean working tree", 1500) if rc == 0 else tool_error("git status", Exception(out))


async def git_diff(args: dict) -> str:
    if (off := _enabled()):
        return off
    path = args.get("path")
    cmd = ["diff"] + ([path] if path and _safe_path(path) else [])
    rc, out = await _git(*cmd)
    return clip(out or "no unstaged changes", 4000)


async def git_log(args: dict) -> str:
    if (off := _enabled()):
        return off
    try:
        n = max(1, min(int(args.get("n") or 10), 50))
    except (TypeError, ValueError):
        n = 10
    rc, out = await _git("log", f"-{n}", "--oneline")
    return clip(out or "no commits yet", 1500)


async def git_new_branch(args: dict) -> str:
    if (off := _enabled()):
        return off
    name = (args.get("name") or "").strip().replace(" ", "-")
    if not name:
        return "What should I name the branch, sir?"
    rc, out = await _git("checkout", "-b", name)
    return f"On a new branch '{name}', sir." if rc == 0 else f"Couldn't branch, sir: {clip(out, 200)}"


async def git_commit(args: dict) -> str:
    if (off := _enabled()):
        return off
    message = (args.get("message") or "").strip()
    if not message:
        return "What should the commit message say, sir?"
    paths = args.get("paths")
    # Stage either the named paths (validated) or all tracked changes.
    if isinstance(paths, list) and paths:
        safe = [str(_safe_path(p)) for p in paths if _safe_path(p)]
        if not safe:
            return "None of those paths are ones I'm allowed to commit, sir."
        await _git("add", *safe)
    else:
        await _git("add", "-A")
    full = f"{message}\n\nMade by Jarvis (self-improvement)."
    rc, out = await _git(
        "-c", f"user.name={settings.git_author_name}",
        "-c", f"user.email={settings.git_author_email}",
        "commit", "-m", full,
    )
    if rc == 0:
        _, head = await _git("rev-parse", "--short", "HEAD")
        return f"Committed as {head.strip()}, sir — fully reversible. {clip(out.splitlines()[-1] if out else '', 120)}"
    return f"Nothing to commit or commit failed, sir: {clip(out, 200)}"


async def git_push(args: dict) -> str:
    if (off := _enabled()):
        return off
    _, branch = await _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch.strip() or "HEAD"
    rc, remotes = await _git("remote")
    if "origin" not in (remotes or ""):
        return ("There's no 'origin' remote yet, sir — add your GitHub repo first "
                "(see TODO-NOW.md Phase 13), then I can push.")
    rc, out = await _git("push", "origin", branch, timeout=120)
    return (f"Pushed '{branch}' to GitHub, sir." if rc == 0
            else f"Push didn't go through, sir: {clip(out, 200)}")


async def git_revert(args: dict) -> str:
    if (off := _enabled()):
        return off
    commit = (args.get("commit") or "HEAD").strip()
    # --no-edit keeps it non-interactive; a revert is a NEW commit, so nothing is lost.
    rc, out = await _git(
        "-c", f"user.name={settings.git_author_name}",
        "-c", f"user.email={settings.git_author_email}",
        "revert", "--no-edit", commit,
    )
    return (f"Reverted {commit} with a new commit, sir — the old state is restored and still in history."
            if rc == 0 else f"Couldn't revert {commit}, sir: {clip(out, 200)}")


SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_source",
        "description": "Read one of your own project source files (repo-relative path). Use to "
                       "inspect your code before changing it. Secrets are blocked.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Repo-relative path, e.g. src/jarvis/brain/agent.py"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_source",
        "description": "Write/replace one of your own source files (repo-relative). For self-"
                       "improvement. Confirm the change first; then run_tests, then git_commit so it's "
                       "reversible. Secrets and paths outside the repo are refused.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Repo-relative path."},
            "content": {"type": "string", "description": "The full new file contents."}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "list_source",
        "description": "List a folder in your project (repo-relative). Use to explore the codebase.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Repo-relative folder; default project root."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "Run the full Jarvis test suite (bench/run_all_tests.py). ALWAYS do this after "
                       "editing code and before committing — only commit when it's green.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "lint",
        "description": "Run ruff on your code (default: src and bench). Use after edits.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Optional path(s) to lint."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "git_status",
        "description": "Show your repo's working-tree status (branch + changed files).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "git_diff",
        "description": "Show the diff of your uncommitted changes (optionally for one path).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Optional repo-relative path."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "git_log",
        "description": "Show recent commits (oneline). Use to find a commit to revert to.",
        "parameters": {"type": "object", "properties": {
            "n": {"type": "integer", "description": "How many commits (default 10)."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "git_new_branch",
        "description": "Create and switch to a new branch before a self-improvement change "
                       "(keeps master clean).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Branch name, e.g. improve/faster-recall."}},
            "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "git_commit",
        "description": "Commit your changes (reversible). Stages the named paths, or all changes if "
                       "none given. Confirm with the owner first; only commit green code.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Commit message (what changed and why)."},
            "paths": {"type": "array", "items": {"type": "string"}, "description": "Optional specific paths."}},
            "required": ["message"]}}},
    {"type": "function", "function": {
        "name": "git_push",
        "description": "Push the current branch to GitHub (origin). Outward-facing — confirm first. "
                       "Needs the repo's origin remote configured.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "git_revert",
        "description": "Undo a commit by creating a NEW revert commit (history is preserved, nothing "
                       "is lost). Use to roll back a change that went wrong.",
        "parameters": {"type": "object", "properties": {
            "commit": {"type": "string", "description": "Commit hash or ref (default HEAD)."}},
            "required": []}}},
]

HANDLERS = {
    "read_source": read_source, "write_source": write_source, "list_source": list_source,
    "run_tests": run_tests, "lint": lint,
    "git_status": git_status, "git_diff": git_diff, "git_log": git_log,
    "git_new_branch": git_new_branch, "git_commit": git_commit, "git_push": git_push,
    "git_revert": git_revert,
}
