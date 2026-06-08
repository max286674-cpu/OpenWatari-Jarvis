"""Switch Jarvis's audio output between speakers and headphones (incl. AirPods).

This is the mechanism the voice command "Jarvis, switch to my headphones" calls (the
brain registers it as a tool in Phase 2). It saves the preference; the edge worker reads
it when it (re)starts and opens the matching output device.

    uv run python -m jarvis.edge.switch_audio headphones
    uv run python -m jarvis.edge.switch_audio speakers
    uv run python -m jarvis.edge.switch_audio          # show current resolution

Why not hot-swap mid-stream: PyAudio binds the device when the output stream opens, so a
clean switch re-opens the stream. The brain tool sets the preference and signals the edge
to re-init its transport (fast, sub-second) rather than mutating a live stream.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jarvis.edge.audio_devices import (  # noqa: E402
    find_output_device,
    load_output_preference,
    resolve_output_index,
    save_output_preference,
)


def set_output(target: str) -> str:
    """Save `target` as the output preference. Returns a spoken-style confirmation."""
    dev = find_output_device(target)
    if dev is None:
        cur, _ = resolve_output_index(None)
        return (
            f"I couldn't find an output device matching '{target}'. "
            "If it's Bluetooth, make sure it's connected first."
        )
    save_output_preference(target)
    return f"Output set to {dev.name}. I'll use it the next time I start speaking."


def main() -> None:
    if len(sys.argv) > 1:
        target = " ".join(sys.argv[1:])
        print(set_output(target))
        return
    pref = load_output_preference()
    idx, label = resolve_output_index(None)
    print(f"saved preference: {pref or '(none — OS default)'}")
    print(f"current resolution: {label} (index {idx})")


if __name__ == "__main__":
    main()
