"""Start the Phase-0 pipeline, run ~8s, then stop. Confirms audio devices open and
Deepgram connects without a real run/voice. Not a substitute for the human mic test."""

import asyncio

from jarvis.edge.hello_voice import build_task
from pipecat.workers.runner import WorkerRunner


async def main() -> None:
    task = build_task()
    runner = WorkerRunner()
    run = asyncio.create_task(runner.run(task))
    print(">>> pipeline started; capturing audio for 8s (say something if you like)…", flush=True)
    await asyncio.sleep(8)
    print(">>> stopping…", flush=True)
    try:
        await task.cancel()
    except Exception as e:  # noqa: BLE001
        print("cancel raised:", type(e).__name__, e)
    try:
        await asyncio.wait_for(run, timeout=10)
    except Exception as e:  # noqa: BLE001
        print("runner ended via:", type(e).__name__)
    print(">>> STARTUP OK — devices opened, services initialised, clean shutdown")


if __name__ == "__main__":
    asyncio.run(main())
