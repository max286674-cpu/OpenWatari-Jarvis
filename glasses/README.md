# MentraOS glasses client — SCAFFOLD, not runnable yet

Status: **parked.** This is the wire-protocol half of a smart-glasses client. It mirrors
`src/jarvis/shared/protocol.py` (hello → ready → utterance → streamed assistant deltas) and is
kept in-tree so the protocol stays honest, but the device-side MentraOS SDK calls are `TODO`
stubs — it cannot run on glasses today.

To finish it you need:

1. A MentraOS developer account and the `@mentra/sdk` package (`npm i` in this dir).
2. Fill the two `TODO(MentraOS SDK)` blocks in `src/index.ts`:
   - speak/HUD-display incoming assistant deltas,
   - subscribe to the live transcription stream and forward utterances.
3. Point it at your brain: `BRAIN_WS_URL=ws://<host>:8765/voice BRAIN_TOKEN=<token>`.

Until then, phones cover the mobile use case — see `clients/iphone/` and the docs site.
