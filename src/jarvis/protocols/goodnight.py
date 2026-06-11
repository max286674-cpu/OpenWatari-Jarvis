"""Protocol GOODNIGHT — stop Jarvis.

Launched detached by the protocol runner with: <parent_pid> <repo_root> <python_exe>.
Waits a moment so Jarvis can speak his farewell, then terminates the Jarvis edge process.
"""

from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        return
    parent_pid = sys.argv[1]
    time.sleep(3)  # let Jarvis say "Goodnight, sir" before he dies
    # Terminate just the Jarvis process (no /T: keep this detached script alive to finish).
    subprocess.run(["taskkill", "/PID", str(parent_pid), "/F"], capture_output=True)


if __name__ == "__main__":
    main()
