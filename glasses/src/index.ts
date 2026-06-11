/**
 * Jarvis MentraOS glasses bridge (Phase 6) — SCAFFOLD.
 *
 * The glasses are a pure mic/speaker/display peripheral; Jarvis's brain (Python) does all the
 * thinking. This bridge:
 *   1. registers a session with the brain over the edge<->brain WebSocket, declaring device_id
 *      "mentra" (so the brain routes barge-in ON — glasses have on-device AEC, a private endpoint);
 *   2. forwards the user's transcribed speech (from the MentraOS SDK) to the brain as an Utterance;
 *   3. speaks / displays the streamed reply (StreamEvent) back on the glasses.
 *
 * It intentionally mirrors src/jarvis/shared/protocol.py. Fill in the SDK calls marked TODO once
 * you register the app in the MentraOS console and have the package installed (npm i).
 */

import { WebSocket } from "ws";

const BRAIN_WS_URL = process.env.JARVIS_BRAIN_WS_URL ?? "ws://127.0.0.1:8765/voice";
const SESSION_ID = `mentra-${Date.now()}`;
const DEVICE_ID = "mentra";

type Hello = { type: "hello"; session_id: string; device_id: string; headphones_connected: boolean };
type Utterance = {
  type: "utterance";
  session_id: string;
  text: string;
  speaker_verified: boolean;
  ts_user_stop_ms: number;
  device_id: string;
};
type StreamEvent = {
  type: "stream";
  session_id: string;
  kind: "assistant" | "tool" | "lifecycle";
  delta: string;
  final: boolean;
};

function connectBrain(): WebSocket {
  const ws = new WebSocket(BRAIN_WS_URL);
  ws.on("open", () => {
    const hello: Hello = {
      type: "hello",
      session_id: SESSION_ID,
      device_id: DEVICE_ID,
      headphones_connected: false, // glasses ARE the private endpoint
    };
    ws.send(JSON.stringify(hello));
    console.log(`[glasses] connected to brain as ${DEVICE_ID} (${SESSION_ID})`);
  });
  ws.on("message", (raw) => {
    const ev = JSON.parse(raw.toString()) as StreamEvent;
    if (ev.kind === "assistant" && ev.delta) {
      // TODO(MentraOS SDK): speak ev.delta via TTS + show on the HUD.
      // session.layouts.showTextWall(ev.delta); session.audio.speak(ev.delta);
      process.stdout.write(ev.delta);
    }
    if (ev.final) process.stdout.write("\n");
  });
  ws.on("close", () => {
    console.log("[glasses] brain link closed; reconnecting in 2s");
    setTimeout(connectBrain, 2000);
  });
  ws.on("error", (e) => console.error("[glasses] ws error", e));
  return ws;
}

function sendUtterance(ws: WebSocket, text: string): void {
  const u: Utterance = {
    type: "utterance",
    session_id: SESSION_ID,
    text,
    speaker_verified: false,
    ts_user_stop_ms: Date.now(),
    device_id: DEVICE_ID,
  };
  ws.send(JSON.stringify(u));
}

async function main(): Promise<void> {
  const ws = connectBrain();

  // TODO(MentraOS SDK): subscribe to the live transcription stream and call sendUtterance:
  //   import { AppServer } from "@mentra/sdk";
  //   session.events.onTranscription((t) => { if (t.isFinal) sendUtterance(ws, t.text); });
  //
  // Until the SDK is wired, this scaffold proves the brain link only.
  console.log("[glasses] scaffold running — wire the MentraOS transcription stream to sendUtterance()");
  void sendUtterance; // referenced so the scaffold compiles before the SDK is wired
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
