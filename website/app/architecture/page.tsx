import Link from "next/link";

export default function Architecture() {
  return (
    <>
      <h1>Architecture</h1>
      <p className="lead">
        Two cooperating processes over one streaming WebSocket protocol: a local <strong>edge</strong>{" "}
        and an always-on <strong>brain</strong>.
      </p>

      <pre>
        <code>{`EDGE — laptop / phone / glasses (where you are)
  Mic -> wake word (openWakeWord) -> VAD (Silero) -> STT (Deepgram/Whisper)
      -> [BrainBridge] --WebSocket--+
  Speaker <- TTS (ElevenLabs/Piper) <-+   (barge-in, smart turn-taking, AEC)
                                |
              streaming events  |  (Tailnet + Bearer-token auth)
                                v
BRAIN — always-on host / VPS (24/7)
  Agent loop: own LLM (+fallback chain) - tool-calling - session + memory
  Confirmation tier ENFORCED in code - smart idle session reset
  Tools: vault(r/w) - web - telegram - gmail - calendar - notion - smart-home
         - utilities - system/PC-control - browser - reminders - coding/git
  Memory L0-L5 - proactive tick (durably logged) - scheduler - audit - health
  HTTP sidecar: /talk (iPhone Siri voice) - /control (remote PC executor)`}</code>
      </pre>

      <h2>Why the split</h2>
      <ul>
        <li>
          <strong>Edge</strong> (<code>src/jarvis/edge/</code>) keeps audio + STT/TTS local for privacy
          and low mic latency.
        </li>
        <li>
          <strong>Brain</strong> (<code>src/jarvis/brain/</code>) holds the 24/7 obligations —
          reasoning, memory, scheduler, channels — so they survive the laptop being off.
        </li>
        <li>
          The Pipecat “LLM stage” is replaced by a thin <code>BrainBridge</code> processor, so swapping
          reasoning backends or transports never touches the audio pipeline.
        </li>
        <li>
          The brain can run in-process (single machine) or as a shared WebSocket server so every device
          shares <em>one</em> brain and <em>one</em> memory.
        </li>
      </ul>

      <h2 id="memory">Memory — six layers</h2>
      <table>
        <thead>
          <tr><th>Layer</th><th>What</th><th>Where</th></tr>
        </thead>
        <tbody>
          <tr><td>L0 Working</td><td>live conversation; smart-reset on long idle</td><td>RAM</td></tr>
          <tr><td>L1 Learned</td><td>durable facts (remember/recall/forget)</td><td><code>memory/learned/</code></td></tr>
          <tr><td>L2 Journal</td><td>daily summaries + a durable log of proactive nudges</td><td><code>memory/journal/</code></td></tr>
          <tr><td>L3 Vault</td><td>your Obsidian KB — read always, <strong>write</strong> on the authoritative host</td><td><code>JARVIS_VAULT_PATH</code></td></tr>
          <tr><td>L4 Hot-cache</td><td>fronts slow paths (search, utilities)</td><td>in-process + optional Redis</td></tr>
          <tr><td>L5 Semantic</td><td>recall by meaning, not just keywords</td><td>optional local embedder</td></tr>
        </tbody>
      </table>
      <div className="callout good">
        <span className="k">Smart session reset.</span> After a long idle gap
        (<code>JARVIS_SESSION_IDLE_RESET_MINUTES</code>) the brain journals the prior conversation and
        clears working memory, so a fresh conversation hours later doesn&apos;t drag stale context or
        anaphora (“set it back” pointing at a “it” from this morning). Durable memory is untouched —
        Watari forgets the <em>thread</em>, not the <em>person</em>.
      </div>

      <h2>Proactivity that remembers</h2>
      <p>
        A background tick weighs signals and may speak unprompted within a budget and quiet hours. Every
        proactive line is recorded into both working memory (so you can answer “yes, do it” at once) and
        the L2 journal (so you can refer back days later). See <Link href="/security">Security</Link>{" "}
        for the enforced confirmation tier that gates anything it tries to act on.
      </p>
    </>
  );
}
