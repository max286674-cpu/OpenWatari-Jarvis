"""Protocol CHECKPOINT - archive key non-secret Jarvis context.

Launched detached with: <parent_pid> <repo_root> <python_exe>.
"""

from __future__ import annotations

import sys
import zipfile
from datetime import datetime
from pathlib import Path

INCLUDE_DIRS = ("memory", "personality", "docs")
INCLUDE_FILES = ("README.md", "SECURITY.md", "TODO-NOW.md", "pyproject.toml")
SKIP_DIRS = {"learned", "journal", "__pycache__"}


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def main() -> None:
    if len(sys.argv) < 3:
        return
    repo_root = Path(sys.argv[2])
    backups = repo_root / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups / f"jarvis-checkpoint-{stamp}.zip"

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in INCLUDE_FILES:
            path = repo_root / name
            if path.is_file():
                zf.write(path, path.relative_to(repo_root))
        for dirname in INCLUDE_DIRS:
            root = repo_root / dirname
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file() and not _should_skip(path.relative_to(root)):
                    zf.write(path, path.relative_to(repo_root))


if __name__ == "__main__":
    main()
