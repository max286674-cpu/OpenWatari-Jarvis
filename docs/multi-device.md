# Phase 6 — Multi-device: the four supported devices

Jarvis serves **one brain** to four endpoints. The laptop runs the full local pipeline; the phone
and glasses are thin clients that stream a finished transcript to the brain and play/show the reply.
Each declares a `device_id` so the brain routes **barge-in** and **audio** correctly (see
`src/jarvis/edge/device_profile.py::resolve_device_route` + the `Hello`/`Utterance` messages in
`src/jarvis/shared/protocol.py`).

| Device | `device_id` | Endpoint kind | Barge-in | How it connects |
|---|---|---|---|---|
| **This host laptop** | `laptop` | speakers (shared) | off* | runs `jarvis.edge.assistant` locally (full pipeline) |
| **iPhone** | `iphone` | phone speaker (shared) | off* | thin client → brain WS (Shortcuts / a small WebRTC app) |
| **AirPods Pro Max** | `airpods` | headphones (private) | **on** | becomes the active output of laptop or iPhone |
| **Mentra OS glasses** | `mentra` | glasses (private, on-device AEC) | **on** | `glasses/` MentraOS TS bridge → brain WS |

\* Barge-in flips **on** automatically the moment AirPods Pro Max connect to that device — the
"route everything to my headphones" rule (`headphones_connected=true` on `Hello`, or the laptop
auto-detecting them via `audio_devices.prefer_private_output`). Private endpoint ⇒ the mic can't
re-hear the TTS ⇒ you can talk over Jarvis safely.

## AirPods Pro Max auto-routing
- **On the laptop:** if the AirPods are connected, `resolve_output_index(..., auto_route_headphones=True)`
  picks them automatically (no config needed) and `resolve_barge_in` turns barge-in on.
- **On the iPhone:** the client sets `headphones_connected=true` in its `Hello`; the brain routes the
  session as `headphones` (private) so barge-in is on there too.

## The brain server (what the phone/glasses connect to)
The laptop pipeline runs the brain in-process, but a remote device needs it over the wire. That
server is `src/jarvis/brain/server.py` — it hosts **one shared `JarvisAgent`** behind the
`shared/protocol.py` WebSocket, so every device talks to the *same* brain + memory. Run it:

```bash
JARVIS_BRAIN_HOST=0.0.0.0 uv run python -m jarvis.brain.server
```

It binds the WebSocket on `:8765/voice` and also serves the phone client over HTTP on `:8766`.
Bind to `0.0.0.0` so the phone (same Wi-Fi) can reach it; set `JARVIS_API_AUTH_TOKEN` to require a
bearer token once you're off loopback. A turn streams back as: `lifecycle:thinking` →
`tool` fillers → `assistant` chunks (one per sentence, `final` on the last) → barge/supersede sends
`lifecycle:cancelled`.

## iPhone (thin client — built)
A self-contained web client ships at **`clients/iphone/index.html`** (no App Store, no Termux):
1. Run the brain server (above).
2. On the iPhone (same Wi-Fi), open `http://<laptop-ip>:8766/iphone/` in Safari → **Add to Home
   Screen** for a full-screen app.
3. It auto-connects, sends `Hello(device_id="iphone")`, push-to-talk via the Web Speech API (with a
   text box fallback where iOS dictation is flaky), and plays replies with `speechSynthesis`.
4. The **"AirPods on this phone"** toggle sets `headphones_connected=true` in the `Hello` — the brain
   then treats the session as private headphones (barge-in on), the "route everything to my
   headphones" rule.

(A Siri **Shortcut** — dictation → POST text → speak the reply — also works for hands-free launch.)

## Android (Termux edge-lite — later)
Termux + Termux:Boot running a stripped `edge` (mic → brain WS → TTS), battery-optimisation disabled.
Reuses the same protocol; `device_id="android"` can be added to `SUPPORTED_DEVICES` when needed.

## Mentra OS glasses
Scaffold in `glasses/` (the only non-Python component). `npm install` in that folder, register the
app in the MentraOS console, then wire the SDK's transcription stream to `sendUtterance()` — the
brain link + device routing are already implemented. Glasses declare `device_id="mentra"` ⇒ private
⇒ barge-in on.

## Verify
`bench/test_phase6_multidevice.py` checks the routing for all four devices, the AirPods
"auto-route to headphones" rule (on both laptop and phone), and the protocol round-trips. The live
multi-device test (same command from phone + glasses hitting one brain) needs the physical devices.
