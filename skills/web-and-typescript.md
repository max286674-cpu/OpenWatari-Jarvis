# The non-Python parts — TypeScript (glasses) and HTML/JS (phone client)

Most of you is Python, but two surfaces use other languages. When you self-improve those, work the
same way (branch → edit → commit), and prefer to keep logic in the Python brain — these are thin
bridges, not brains.

## Mentra glasses bridge — TypeScript (`glasses/`)
- The glasses are a pure mic/speaker/display device; the brain still does all thinking.
- The bridge connects the MentraOS SDK's transcription stream to your brain over the same WebSocket
  protocol the iPhone client uses (`shared/protocol.py`: `Hello`/`Utterance`/`Barge` →
  `StreamEvent`). Send the glasses' final transcript as an `Utterance`; render the streamed
  `assistant` chunks on the glasses display and via TTS.
- Keep TypeScript minimal and typed. Don't reimplement reasoning here — forward to the brain.
- It's parked until the hardware is bought (see `TODO-NOW.md`), but the brain side is ready.

## iPhone / web client — HTML + JS (`clients/iphone/`)
- A single self-contained `index.html`: Web Speech API for STT (`webkitSpeechRecognition`) with a
  text fallback, `speechSynthesis` for TTS, and a WebSocket to the brain.
- It speaks the same protocol: send `{type:"hello", session_id, device_id, headphones_connected}`,
  then `{type:"utterance", ...}`; handle `StreamEvent` lifecycle/tool/assistant frames.
- When you change the protocol in `shared/protocol.py`, update BOTH this client and the glasses
  bridge to match, or remote devices break. The brain server (`brain/server.py`) is the contract.

## Rule of thumb
A new capability belongs in the Python brain as a tool (so every device gets it at once), not in a
client. Touch the clients only for input/output/display concerns.
