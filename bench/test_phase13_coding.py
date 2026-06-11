"""Phase 13 — coding & self-improvement tools + skills, hermetic.

Verifies the safety rails that make self-improvement trustworthy: file I/O is confined to the repo
and refuses secrets; only reversible git ops exist (no reset/force-push tool is registered); the
read git ops work on the real repo; write_source round-trips inside the repo (to a temp file we
delete); skills load from skills/; and writes/commits/pushes are confirm-gated. Read-only against
git; no network.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    mark = "[PASS]" if ok else "[FAIL]"
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"  {mark} {name}" + (f" — {detail}" if detail and not ok else ""))


def main() -> None:
    import jarvis.brain.tools.coding as coding
    import jarvis.brain.tools.skills as skills
    from jarvis.brain.proactive import confirm_required
    from jarvis.brain.tools import tool_names

    print("[1] path safety — repo-relative only, secrets blocked")
    check("a normal source path resolves", coding._safe_path("src/jarvis/config.py") is not None)
    check("traversal outside repo is refused", coding._safe_path("../../etc/passwd") is None)
    check("absolute escape is refused", coding._safe_path("C:/Windows/system32") is None)
    check(".env is blocked", coding._safe_path(".env") is None)
    check("a .session file is blocked", coding._safe_path("jarvis.session") is None)
    check("voiceprint.json is blocked", coding._safe_path("voiceprint.json") is None)
    check("the audit/ dir is blocked", coding._safe_path("audit/2026-06-12.jsonl") is None)
    check(".git internals are blocked", coding._safe_path(".git/config") is None)

    print("\n[2] read_source reads real code; refuses secrets with a spoken note")
    out = asyncio.run(coding.read_source({"path": "src/jarvis/config.py"}))
    check("reads config.py", "Settings" in out or "class Settings" in out, out[:60])
    secret = asyncio.run(coding.read_source({"path": ".env"}))
    check("refuses to read .env", "outside the project or a protected file" in secret, secret)

    print("\n[3] write_source round-trips inside the repo (temp file, then cleaned)")
    rel = "bench/_p13_scratch.tmp"
    res = asyncio.run(coding.write_source({"path": rel, "content": "scratch 123"}))
    p = Path(__file__).resolve().parents[1] / rel
    check("write reports success", "Created" in res or "Updated" in res, res)
    check("file exists with content", p.is_file() and p.read_text() == "scratch 123")
    bad = asyncio.run(coding.write_source({"path": "../escape.tmp", "content": "x"}))
    check("write outside repo refused", "won't write there" in bad, bad)
    p.unlink(missing_ok=True)

    print("\n[4] git read ops work on the real repo")
    st = asyncio.run(coding.git_status({}))
    check("git_status returns text", isinstance(st, str) and st.strip() != "")
    lg = asyncio.run(coding.git_log({"n": 3}))
    check("git_log returns commits", isinstance(lg, str) and lg.strip() != "")

    print("\n[5] only reversible git tools exist — no destructive ones")
    names = set(tool_names())
    want = {"git_status", "git_diff", "git_log", "git_new_branch", "git_commit", "git_push",
            "git_revert", "read_source", "write_source", "list_source", "run_tests", "lint"}
    check("all coding tools registered", want <= names, str(sorted(want - names)))
    forbidden = {"git_reset", "git_force_push", "git_rebase", "git_clean", "git_amend",
                 "git_branch_delete", "git_push_force"}
    check("no destructive git tool is registered", not (forbidden & names), str(forbidden & names))

    print("\n[6] writes/commits/pushes are confirm-gated; reads are not")
    check("write_source confirm-gated", confirm_required("write_source"))
    check("git_commit confirm-gated", confirm_required("git_commit"))
    check("git_push confirm-gated", confirm_required("git_push"))
    check("git_revert confirm-gated", confirm_required("git_revert"))
    check("read_source NOT gated", not confirm_required("read_source"))
    check("git_status NOT gated", not confirm_required("git_status"))

    print("\n[7] skills library loads the coding playbooks")
    listing = asyncio.run(skills.list_skills({}))
    for s in ("self-improvement", "jarvis-architecture", "python", "adding-a-tool"):
        check(f"skill '{s}' listed", s in listing, listing[:80])
    doc = asyncio.run(skills.read_skill({"name": "self-improvement"}))
    check("read_skill returns the playbook", "reversible" in doc.lower(), doc[:80])
    check("unknown skill handled", "don't have" in asyncio.run(skills.read_skill({"name": "zzz"})).lower())
    check("list_skills + read_skill registered", {"list_skills", "read_skill"} <= names)

    print(f"\n=== {passed}/{passed + failed} checks passed ===")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
