"""Protocol BACKUP - archive Jarvis memory.

Launched detached with: <parent_pid> <repo_root> <python_exe>.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        return
    repo_root = Path(sys.argv[2])
    memory = repo_root / "memory"
    if not memory.is_dir():
        return

    backups = repo_root / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.make_archive(str(backups / f"jarvis-memory-{stamp}"), "zip", root_dir=str(memory))


if __name__ == "__main__":
    main()
