"""Process-level keep-alive for the edge daemons (voice assistant, PC agent).

Two real problems this solves:
  1. ``pythonw.exe`` (used so nothing flashes a console at logon) discards stdout/stderr — so when
     the edge died we had NO logs to say why. This tees everything to ``logs/<name>.log``.
  2. A daemon can exit either by crashing OR by ``main()`` returning cleanly (e.g. the audio
     pipeline ended). Windows Task Scheduler only restarts on a NON-zero exit, so a clean return
     left the edge silently dead. This wraps ``main()`` in a loop that relaunches it on ANY exit
     with backoff, so the only thing that stops it is a real shutdown (Ctrl-C / the task ending).

Used by ``jarvis.edge.assistant`` and ``jarvis.edge.pc_agent`` in their ``__main__``.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_supervised(name: str, main: Callable[[], Awaitable[None]]) -> None:
    """Run ``main()`` forever: relaunch on any exit (crash or clean) with capped backoff, log to file."""
    logdir = _REPO_ROOT / "logs"
    logdir.mkdir(exist_ok=True)
    logger.add(logdir / f"{name}.log", rotation="5 MB", retention=5, enqueue=True, level="INFO")
    logger.info(f"{name}: supervisor up — logs at logs/{name}.log")
    backoff = 2.0
    while True:
        started = time.time()
        try:
            asyncio.run(main())
            logger.warning(f"{name}: main() returned — relaunching to stay alive")
        except KeyboardInterrupt:
            logger.info(f"{name}: stopped by user")
            return
        except Exception:
            logger.exception(f"{name}: crashed — relaunching")
        # Reset backoff if it ran a healthy while; otherwise back off so a hard-crash loop is gentle.
        backoff = 2.0 if (time.time() - started) > 60 else min(backoff * 2, 60.0)
        logger.info(f"{name}: restarting in {backoff:.0f}s")
        time.sleep(backoff)
