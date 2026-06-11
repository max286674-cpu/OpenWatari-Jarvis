"""Protocol RAGNAROK — restart the laptop.

Launched detached with: <parent_pid> <repo_root> <python_exe>. Schedules a Windows restart
with a short grace period (and a visible reason) so Vazghen can still abort with
``shutdown /a`` if needed.
"""

from __future__ import annotations

import subprocess
import sys
import time

GRACE_SECONDS = 15


def main() -> None:
    time.sleep(2)  # let Jarvis announce it
    if sys.platform == "win32":
        subprocess.run(
            ["shutdown", "/r", "/t", str(GRACE_SECONDS), "/c", "Jarvis protocol Ragnarok: restarting."],
            capture_output=True,
        )
    else:  # POSIX fallback
        subprocess.run(["shutdown", "-r", "+1"], capture_output=True)


if __name__ == "__main__":
    main()
