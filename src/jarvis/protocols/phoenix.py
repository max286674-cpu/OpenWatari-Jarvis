"""Protocol PHOENIX — restart Jarvis.

Launched detached with: <parent_pid> <repo_root> <python_exe>. Kills the old Jarvis edge
process, waits for it to release the mic/audio devices, then starts a fresh one.
"""

from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    if len(sys.argv) < 4:
        return
    parent_pid, repo_root, python_exe = sys.argv[1], sys.argv[2], sys.argv[3]
    time.sleep(3)  # let Jarvis announce the reboot
    subprocess.run(["taskkill", "/PID", str(parent_pid), "/F"], capture_output=True)
    time.sleep(2)  # give the OS time to free the audio devices

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
    subprocess.Popen(
        [python_exe, "-m", "jarvis.edge.assistant"],
        cwd=repo_root,
        creationflags=flags,
        close_fds=True,
    )


if __name__ == "__main__":
    main()
