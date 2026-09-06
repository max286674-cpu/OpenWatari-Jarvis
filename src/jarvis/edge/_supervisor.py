"""Process-level keep-alive for the edge daemons (voice assistant, PC agent).

The supervisor restarts the edge after crashes or unexpected clean exits, but an explicit
user shutdown (Ctrl+C / SIGTERM / SIGBREAK on Windows) is always terminal.
"""

from __future__ import annotations

import asyncio
import signal
import time
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_supervised(name: str, main: Callable[[], Awaitable[None]]) -> None:
    """Keep an edge daemon alive, while making explicit shutdowns genuinely terminal."""
    logdir = _REPO_ROOT / "logs"
    logdir.mkdir(exist_ok=True)
    logger.add(logdir / f"{name}.log", rotation="5 MB", retention=5, enqueue=True, level="INFO")
    logger.info(f"{name}: supervisor up — logs at logs/{name}.log")

    stop_requested = False

    def _request_stop(signum, _frame) -> None:  # noqa: ANN001
        nonlocal stop_requested
        stop_requested = True
        logger.info(f"{name}: shutdown requested (signal={signum})")

    # On Windows Ctrl+C is SIGINT; Ctrl+Break is SIGBREAK. SIGTERM is useful for Task Scheduler
    # and process managers. The handler deliberately does NOT raise inside asyncio: it records the
    # intent, so even if asyncio.run() turns the signal into a clean cancellation/return, the
    # supervisor will not mistake that return for a crash and relaunch the assistant.
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    backoff = 2.0
    while not stop_requested:
        started = time.time()
        try:
            asyncio.run(main())
            if stop_requested:
                break
            logger.warning(f"{name}: main() returned — relaunching to stay alive")
        except KeyboardInterrupt:
            # Defensive fallback for launchers that bypass the signal handler.
            stop_requested = True
            logger.info(f"{name}: stopped by user")
            break
        except Exception:
            if stop_requested:
                break
            logger.exception(f"{name}: crashed — relaunching")

        if stop_requested:
            break

        # Reset backoff if it ran a healthy while; otherwise back off so a hard-crash loop is gentle.
        backoff = 2.0 if (time.time() - started) > 60 else min(backoff * 2, 60.0)
        logger.info(f"{name}: restarting in {backoff:.0f}s")
        try:
            time.sleep(backoff)
        except KeyboardInterrupt:
            stop_requested = True
            break

    logger.info(f"{name}: supervisor stopped")
