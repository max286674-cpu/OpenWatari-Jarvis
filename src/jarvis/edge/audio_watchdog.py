"""Audio-stream liveness watchdog — recover a dead mic/speaker after a device change.

pipecat's ``LocalAudioTransport`` opens the mic + speaker PyAudio streams ONCE at startup. When the
OS audio topology changes mid-session — AirPods connect/disconnect, Bluetooth sleep/resume — those
streams go stale WITHOUT an error the pipeline notices: the mic stops delivering frames (Watari goes
deaf) or the speaker write fails with ``[Errno -9988] Stream closed`` (Watari goes mute). Until now the
only recovery was a manual restart — this was the recurring "I say hey watari and nothing comes" bug.

The fix reuses the existing supervisor (``run_supervised`` relaunches ``main()`` on any return): a probe
timestamps every input audio frame; a background task trips a ``dead`` Event when either

  * no mic frame has arrived for ``silence_limit_s`` (a live mic delivers frames continuously, even in
    silence — a gap means the stream died), or
  * the bound OUTPUT device has vanished from the device list (AirPods disconnected → speaker is dead).

``main()`` races the pipeline against that Event and returns when it trips, so the supervisor rebuilds
the edge with FRESH device resolution (mic → whatever's live, output → AirPods if present else Speakers).
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger
from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class AudioLivenessProbe(FrameProcessor):
    """Timestamps every input audio frame. Placed right after ``transport.input()`` (before any gate
    that could mute the mic), so it sees the RAW stream — the true signal of a live vs dead mic."""

    def __init__(self) -> None:
        super().__init__()
        self.last_input = time.monotonic()
        self.count = 0   # total input audio frames seen — diagnostic for "is the mic feeding pipecat?"

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self.last_input = time.monotonic()
            self.count += 1
        await self.push_frame(frame, direction)


def output_device_present(name: str | None) -> bool:
    """Is the bound output device still enumerable? A vanished device = the headphones disconnected.
    Fail-open (return True) on any error so a flaky enumeration never false-trips a restart."""
    if not name:
        return True
    try:
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            needle = name.split("(")[0].strip().lower() or name.lower()
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0 and needle in (info.get("name") or "").lower():
                    return True
            return False
        finally:
            pa.terminate()
    except Exception:  # noqa: BLE001 — can't check → don't false-trip
        return True


async def watch_audio_liveness(
    probe: AudioLivenessProbe,
    dead: asyncio.Event,
    out_device_name: str | None = None,
    *,
    silence_limit_s: float = 60.0,   # a live mic delivers frames (incl. silence) continuously; a 60s
                                     # gap is unambiguously a DEAD stream, never bursty delivery
    poll_s: float = 5.0,
    grace_s: float = 30.0,           # let device enumeration + first frames settle before judging
    device_check_every: int = 3,     # check output-device presence every 3rd poll (~15s) — cheaper
    cloud_desired: bool = False,     # settings ask for cloud STT/TTS -> allow upgrading back to it
    on_private: bool = False,        # are we currently playing to a private endpoint (AirPods)?
    auto_route: bool = True,         # auto-follow headphones connect/disconnect
) -> None:
    """Set ``dead`` when the mic stops delivering, the output device disappears, OR the cloud voice
    route is failing (fail over to local) / has recovered (upgrade back to cloud)."""
    from jarvis.edge import voice_health

    await asyncio.sleep(grace_s)
    i = 0
    out_misses = 0
    last_count = -1
    while not dead.is_set():
        gap = time.monotonic() - probe.last_input
        # Cloud voice auto-failover: if cloud (Deepgram/ElevenLabs) is the ACTIVE route and it's
        # failing (repeated escalated WebSocket errors the REST probe can't see), cool down + restart
        # -> the edge comes back up on LOCAL Whisper/Piper so Watari keeps hearing and speaking.
        if voice_health.cloud_is_active() and voice_health.cloud_failing():
            logger.error("audio watchdog: cloud voice failing — failing over to LOCAL (restarting edge)")
            voice_health.note_failover()   # long cooldown if it was a quota/auth failure, short if transient
            dead.set()
            return
        # Conversely, when we're DEGRADED on local (cloud desired but not active), re-probe every ~5
        # min and, once the cooldown lapses and cloud answers again, restart to UPGRADE back to cloud.
        # Probing only while degraded means no polling in the healthy steady state. Threaded: the REST
        # calls block for seconds and would stall the pipeline on the event loop (the old churn bug).
        if cloud_desired and not voice_health.cloud_is_active() and i > 0 and i % 60 == 0:
            if await asyncio.to_thread(voice_health.cloud_recovered):
                logger.info("audio watchdog: cloud voice recovered — upgrading back to cloud (restarting edge)")
                dead.set()
                return
        # Observability: every ~30s log the running frame count + gap so a flaky mic feed (the Intel
        # Smart Sound array intermittently stalls) is visible in the log without a full 60s dead-stream
        # trip. ``delta`` is frames since the last tick — a healthy mic adds hundreds; 0 means starved.
        if i % 6 == 0:
            delta = probe.count - last_count if last_count >= 0 else probe.count
            logger.info(f"audio liveness: frames={probe.count} (+{delta}/30s) gap={gap:.1f}s")
            last_count = probe.count
        # A stalled mic is the #1 "I say hey watari and nothing comes" cause: a device change (AirPods
        # connect/disconnect) stales pipecat's capture stream WITHOUT an error, so the mic goes deaf
        # with no recovery. pipecat's LocalAudioTransport delivers frames continuously (silence
        # included), so a gap past ``silence_limit_s`` (60s) is a genuinely dead stream — trip a
        # restart to rebuild it fresh. The threshold is high enough that normal delivery never hits it
        # (the earlier "bursty gaps" were an event-loop-blocking bug, since fixed via to_thread below).
        if gap > silence_limit_s:
            logger.error(f"audio watchdog: mic gap {gap:.0f}s (frames={probe.count}) — stream dead, restarting edge")
            dead.set()
            return
        if i % device_check_every == 0:
            # Follow AirPods connect/disconnect: re-resolve the route when headphones appear (switch to
            # them) or the bound output vanishes (fall back to speakers). Require TWO consecutive hits so
            # a momentary Bluetooth blip doesn't restart. Threaded — PyAudio enumeration blocks seconds on
            # BT init, and on the event loop that stalls the whole audio pipeline (sporadic frames/churn).
            from jarvis.edge.audio_devices import route_should_change

            reason = await asyncio.to_thread(route_should_change, out_device_name, on_private, auto_route)
            out_misses = out_misses + 1 if reason else 0
            if out_misses >= 2:
                logger.info(f"audio watchdog: {reason} — re-routing (restarting edge)")
                dead.set()
                return
        i += 1
        try:
            await asyncio.wait_for(dead.wait(), timeout=poll_s)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    # Self-check: a stalled probe trips `dead` fast; a fresh probe does not.
    async def _demo() -> None:
        p = AudioLivenessProbe()
        p.last_input = time.monotonic() - 100  # pretend the mic died 100s ago
        d = asyncio.Event()
        await watch_audio_liveness(p, d, out_device_name=None, silence_limit_s=20, grace_s=0, poll_s=0.1)
        assert d.is_set(), "watchdog should trip on a stalled mic"

        p2 = AudioLivenessProbe()  # fresh: never trips within the window
        d2 = asyncio.Event()
        try:
            await asyncio.wait_for(
                watch_audio_liveness(p2, d2, out_device_name=None, silence_limit_s=20, grace_s=0, poll_s=0.1),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass
        assert not d2.is_set(), "watchdog must NOT trip on a live mic"
        print("audio_watchdog self-check OK")

    asyncio.run(_demo())
