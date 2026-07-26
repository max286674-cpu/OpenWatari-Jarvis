"""Audio watchdog: trips on a dead mic / vanished output device, stays quiet on a live stream.

Guards the recurring "I say hey watari and nothing comes" bug: a device change (AirPods connect/
disconnect) stales the mic/speaker streams; the watchdog must detect that and trigger a fresh restart.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis.edge.audio_watchdog import (  # noqa: E402
    AudioLivenessProbe, output_device_present, watch_audio_liveness,
)

_ok = _fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
    else:
        _fail += 1
        print(f"  FAIL: {label}")


async def _run():
    # A) a DEAD mic (gap past silence_limit) MUST trip a restart so Watari recovers from deafness
    dead = asyncio.Event()
    stalled = AudioLivenessProbe()
    stalled.last_input = time.monotonic() - 100
    await watch_audio_liveness(stalled, dead, None, silence_limit_s=20, grace_s=0, poll_s=0.05)
    check(dead.is_set(), "a dead mic (long gap) trips a restart")

    # B) does NOT trip on a live mic
    dead2 = asyncio.Event()
    live = AudioLivenessProbe()  # last_input = now
    try:
        await asyncio.wait_for(
            watch_audio_liveness(live, dead2, None, silence_limit_s=20, grace_s=0, poll_s=0.05),
            timeout=0.4,
        )
    except asyncio.TimeoutError:
        pass
    check(not dead2.is_set(), "stays quiet while the mic is live")

    # C) DOES trip when the bound output device vanishes (needs 2 consecutive misses = hysteresis)
    dead3 = asyncio.Event()
    live2 = AudioLivenessProbe()
    await watch_audio_liveness(live2, dead3, "NoSuchDevice ZZZ 9999",
                               silence_limit_s=999, grace_s=0, poll_s=0.05, device_check_every=1)
    check(dead3.is_set(), "trips when the bound output device vanished (headphones unplugged)")

    # D) output_device_present fail-open: unknown name → True (never false-trip on a missing name)
    check(output_device_present(None) is True, "output_device_present(None) fails open")


asyncio.run(_run())
print(f"=== {_ok}/{_ok + _fail} checks passed ===")
sys.exit(1 if _fail else 0)
