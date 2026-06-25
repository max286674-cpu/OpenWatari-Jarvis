"""Audio device discovery + selection (speakers <-> headphones, incl. AirPods).

Jarvis can play through whichever output device the owner prefers — built-in laptop
speakers or Bluetooth headphones. On Windows, Apple AirPods Pro Max appear as a
*generic* Bluetooth audio device once paired+connected (there is no Apple SDK):

  * "Headphones (AirPods Pro Max Stereo)"  -> A2DP profile: high-quality OUTPUT only.
  * "Headset (AirPods Pro Max Hands-Free)" -> HFP profile: bidirectional but
    telephone-grade (8/16 kHz), and selecting it forces the mic into HFP too.

So realistically: yes, Jarvis can play through the AirPods (A2DP). Using them as the
*mic* simultaneously drops the whole link to low-quality HFP — for now Jarvis keeps the
laptop mic for input and only routes OUTPUT to the headphones. Output switching is what
the voice command toggles.

This module is pure discovery/resolution (no pipeline deps) so it is unit-testable on
its own and reused by both the edge transport builder and the runtime switch command.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Friendly aliases -> substrings to look for in a device's reported name (lowercased).
# Lets a voice command say "headphones" / "speakers" without knowing the exact OS label.
OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "headphones": ("airpod", "headphone", "headset", "buds", "bluetooth"),
    "headset": ("airpod", "headset", "headphone"),
    "airpods": ("airpod",),
    "speakers": ("speaker", "realtek", "internal", "laptop"),
    "laptop": ("speaker", "realtek", "internal", "laptop"),
    "speaker": ("speaker", "realtek", "internal", "laptop"),
}

# Where the chosen output preference is persisted so a (re)started worker honors the
# last voice command. Small JSON, user-home scoped.
PREF_PATH = Path.home() / ".jarvis" / "audio_pref.json"


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int

    @property
    def is_output(self) -> bool:
        return self.max_output_channels > 0

    @property
    def is_input(self) -> bool:
        return self.max_input_channels > 0


def list_devices() -> list[AudioDevice]:
    """Enumerate all host audio devices via PyAudio."""
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        out: list[AudioDevice] = []
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            out.append(
                AudioDevice(
                    index=i,
                    name=str(d.get("name", f"device {i}")),
                    max_input_channels=int(d.get("maxInputChannels", 0)),
                    max_output_channels=int(d.get("maxOutputChannels", 0)),
                )
            )
        return out
    finally:
        pa.terminate()


def default_output_index() -> int | None:
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        return int(pa.get_default_output_device_info().get("index"))
    except Exception:
        return None
    finally:
        pa.terminate()


def default_input_index() -> int | None:
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        return int(pa.get_default_input_device_info().get("index"))
    except Exception:
        return None
    finally:
        pa.terminate()


def _expand_query(query: str) -> tuple[str, ...]:
    """Turn a user word into the set of substrings to match against device names."""
    q = query.strip().lower()
    if q in OUTPUT_ALIASES:
        return OUTPUT_ALIASES[q]
    return (q,)  # treat as a literal substring (e.g. an exact device-name fragment)


def find_output_device(query: str, devices: list[AudioDevice] | None = None) -> AudioDevice | None:
    """Resolve a query like 'headphones' / 'airpods' / 'speakers' to an OUTPUT device.

    Numeric query -> that exact device index. Prefers non-Hands-Free (A2DP) matches so
    we get high-quality playback rather than the telephone-grade HFP endpoint.
    """
    devs = devices if devices is not None else list_devices()
    outputs = [d for d in devs if d.is_output]

    if query.strip().isdigit():
        idx = int(query.strip())
        return next((d for d in outputs if d.index == idx), None)

    needles = _expand_query(query)
    matches = [d for d in outputs if any(n in d.name.lower() for n in needles)]
    if not matches:
        return None
    # Prefer a high-quality stereo endpoint over the "Hands-Free" HFP one.
    non_hfp = [d for d in matches if "hands-free" not in d.name.lower() and "headset" not in d.name.lower()]
    pool = non_hfp or matches
    # Among those, prefer the one with the most output channels (stereo > mono).
    return max(pool, key=lambda d: d.max_output_channels)


# Substrings that mark an OUTPUT device as a PRIVATE/headphone endpoint (AirPods etc.). Used by
# auto-routing: if such a device is connected to this laptop, prefer it over the open speakers.
_PRIVATE_OUTPUT_CUES = ("airpod", "headphone", "headset", "buds", "earphone", "bluetooth", "bt audio")


def prefer_private_output(devices: list[AudioDevice] | None = None) -> AudioDevice | None:
    """Return a connected private/headphone OUTPUT device (e.g. AirPods Pro Max) if one exists.

    This is the "auto-route to headphones" rule: when AirPods are connected to the laptop, Jarvis
    should play through them automatically (and barge-in then auto-enables via device_profile).
    Prefers a high-quality A2DP stereo endpoint over the telephone-grade Hands-Free one.
    """
    devs = devices if devices is not None else list_devices()
    outputs = [d for d in devs if d.is_output]
    matches = [d for d in outputs if any(c in d.name.lower() for c in _PRIVATE_OUTPUT_CUES)]
    if not matches:
        return None
    non_hfp = [d for d in matches if "hands-free" not in d.name.lower() and "headset" not in d.name.lower()]
    pool = non_hfp or matches
    return max(pool, key=lambda d: d.max_output_channels)


def find_input_device(query: str, devices: list[AudioDevice] | None = None) -> AudioDevice | None:
    devs = devices if devices is not None else list_devices()
    inputs = [d for d in devs if d.is_input]
    if query.strip().isdigit():
        idx = int(query.strip())
        return next((d for d in inputs if d.index == idx), None)
    needles = _expand_query(query)
    matches = [d for d in inputs if any(n in d.name.lower() for n in needles)]
    return matches[0] if matches else None


# ---- persisted preference (so a voice command survives a worker restart) ----------------

def save_output_preference(query: str) -> None:
    PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREF_PATH.write_text(json.dumps({"output": query}), encoding="utf-8")


def load_output_preference() -> str | None:
    try:
        return json.loads(PREF_PATH.read_text(encoding="utf-8")).get("output")
    except Exception:
        return None


def resolve_output_index(
    preferred: str | None, auto_route_headphones: bool = True
) -> tuple[int | None, str]:
    """Pick an output device index given an optional preference (config or saved pref).

    Returns (index_or_None, human_label). None index means "use the OS default".

    With no explicit preference (or pref == 'auto') and ``auto_route_headphones`` on, Jarvis
    auto-routes to a connected private endpoint (AirPods Pro Max / headphones) when one is
    present — "if they're connected, send everything to my headphones" — otherwise the OS default.
    An explicit preference ('speakers', a device name, an index) always wins over auto-routing.
    """
    pref = preferred or load_output_preference()
    if not pref or pref.strip().lower() == "auto":
        if auto_route_headphones:
            priv = prefer_private_output()
            if priv is not None:
                return priv.index, f"{priv.name} (auto-routed to headphones)"
        idx = default_output_index()
        devs = list_devices()
        label = next((d.name for d in devs if d.index == idx), "system default")
        return idx, f"{label} (default)"
    dev = find_output_device(pref)
    if dev is None:
        return default_output_index(), f"'{pref}' not found — using system default"
    return dev.index, dev.name
