export default function Configuration() {
  return (
    <>
      <h1>Configuration</h1>
      <p className="lead">
        Everything is driven by <code>JARVIS_</code>-prefixed environment variables in a local{" "}
        <code>.env</code>. Run <code>jarvis-setup</code> to generate it; <code>.env.example</code>{" "}
        documents every knob inline.
      </p>

      <div className="callout warn">
        <span className="k">Never commit <code>.env</code></span> — it&apos;s git-ignored. Keep your
        configured fork private if it carries personal data.
      </div>

      <h2>Core knobs</h2>
      <table>
        <thead>
          <tr><th>Variable</th><th>Purpose</th></tr>
        </thead>
        <tbody>
          <tr><td><code>JARVIS_STT_PROVIDER</code></td><td><code>deepgram</code> (cloud) / <code>whisper</code> / <code>moonshine</code> (local)</td></tr>
          <tr><td><code>JARVIS_TTS_PROVIDER</code></td><td><code>elevenlabs</code> (cloud) / <code>piper</code> / <code>kokoro</code> (local)</td></tr>
          <tr><td><code>JARVIS_LLM_BACKEND</code></td><td>the reasoning LLM: <code>freellmapi</code> / <code>openai</code> / <code>ollama</code></td></tr>
          <tr><td><code>JARVIS_WAKE_WORDS</code></td><td>e.g. <code>hey jarvis</code> (pre-trained set; custom phrases need Porcupine)</td></tr>
          <tr><td><code>JARVIS_VAULT_PATH</code></td><td>your Obsidian/Markdown notes folder (L3 memory)</td></tr>
          <tr><td><code>JARVIS_BRAIN_HOST</code></td><td><code>127.0.0.1</code> single-machine, <code>0.0.0.0</code> for multi-device</td></tr>
          <tr><td><code>JARVIS_API_AUTH_TOKEN</code></td><td>bearer token required off-loopback (wizard generates it)</td></tr>
          <tr><td><code>JARVIS_BRAIN_WS_URL</code></td><td>edge → brain, e.g. <code>ws://&lt;tailnet-ip&gt;:8765/voice</code></td></tr>
        </tbody>
      </table>

      <h2>Safety &amp; memory knobs</h2>
      <table>
        <thead>
          <tr><th>Variable</th><th>Purpose</th></tr>
        </thead>
        <tbody>
          <tr><td><code>JARVIS_VAULT_WRITABLE</code></td><td><code>true</code> only on the host that <em>owns</em> the vault; enables <code>write_vault</code>. Off on the laptop (its mirror is clobbered by the one-way sync).</td></tr>
          <tr><td><code>JARVIS_SESSION_IDLE_RESET_MINUTES</code></td><td>after this idle gap the brain journals the prior conversation and clears working memory (durable memory kept). <code>0</code> disables.</td></tr>
          <tr><td><code>JARVIS_PROACTIVE_ENABLED</code></td><td>allow unprompted speech (within budget + quiet hours)</td></tr>
          <tr><td><code>JARVIS_FLEET_AUTHORIZED</code></td><td>allow consulting the optional external fleet (off by default)</td></tr>
          <tr><td><code>JARVIS_SPEAKER_ID_ENABLED</code></td><td>respond only to your enrolled voice (off until enrolled)</td></tr>
          <tr><td><code>JARVIS_PROTOCOL_*_PASSWORD</code></td><td>passwords for the eight privileged routines (wizard generates them)</td></tr>
        </tbody>
      </table>

      <h2>What lives where</h2>
      <ul>
        <li><strong>Character</strong> — <code>personality/jarvis.md</code> (edit to make Watari yours).</li>
        <li><strong>Knowledge</strong> — Markdown under <code>memory/</code> + your vault.</li>
        <li><strong>Skills</strong> — on-demand playbooks in <code>skills/*.md</code>.</li>
      </ul>
      <p>
        Nothing is hard-coded: the same codebase runs CPU-local-only or cloud-quality by flipping
        provider flags, and an unconfigured integration simply says “that isn&apos;t configured yet”.
      </p>
    </>
  );
}
