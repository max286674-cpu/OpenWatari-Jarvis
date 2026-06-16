import Link from "next/link";

export default function Devices() {
  return (
    <>
      <h1>Devices</h1>
      <p className="lead">
        One brain, reached many ways — all sharing memory, all over your{" "}
        <Link href="/networking">Tailnet</Link>. All seven setups are wired and tested.
      </p>

      <table>
        <thead>
          <tr><th>Setup</th><th>Connects via</th><th>Barge-in</th><th>Notes</th></tr>
        </thead>
        <tbody>
          <tr><td>Laptop</td><td><code>jarvis.edge.assistant</code> → brain WS</td><td>off</td><td>baseline; open speakers run half-duplex</td></tr>
          <tr><td>Laptop + headphones</td><td>same, auto-routes to headphones</td><td><strong>on</strong></td><td>private endpoint; interrupt mid-sentence</td></tr>
          <tr><td>Phone (iPhone, no app)</td><td>“Hey Siri, Watari” → <code>/talk</code></td><td>n/a</td><td>Siri dictation → spoken reply</td></tr>
          <tr><td>Phone + headphones</td><td>same Siri Shortcut</td><td>n/a</td><td>reply plays in the AirPods</td></tr>
          <tr><td>Mentra OS glasses</td><td>TS bridge → brain WS</td><td>on</td><td>mic/speaker/display bridge</td></tr>
          <tr><td>Home Assistant</td><td>brain → HA REST (local)</td><td>n/a</td><td>states + control; locks confirm-gated</td></tr>
          <tr><td>Remote PC control</td><td>laptop executor → brain <code>/control</code></td><td>n/a</td><td>brain drives the laptop from anywhere</td></tr>
        </tbody>
      </table>

      <h2>Laptop &amp; laptop + headphones</h2>
      <pre>
        <code>{`uv run python -m jarvis.edge.assistant`}</code>
      </pre>
      <p>
        With headphones/AirPods connected to the laptop, output auto-routes to them and barge-in turns
        on (a private endpoint), so you can talk over Watari mid-sentence. On open speakers it runs
        half-duplex so it never transcribes its own voice. Each turn logs a TTFW latency number; aim for
        ~10 turns to get a stable mean.
      </p>

      <h2>Phone &amp; phone + headphones (iPhone, no app, no page)</h2>
      <p>
        Run the brain reachable over the tailnet, then build a one-time Siri Shortcut:
      </p>
      <pre>
        <code>{`# on the brain host:
JARVIS_BRAIN_HOST=0.0.0.0  uv run python -m jarvis.brain.server`}</code>
      </pre>
      <ol>
        <li><strong>Dictate Text</strong></li>
        <li>
          <strong>Get Contents of URL</strong> → <code>http://&lt;brain-tailnet-ip&gt;:8766/talk?token=&lt;JARVIS_API_AUTH_TOKEN&gt;</code>,
          method <span className="kbd">POST</span>, body <span className="kbd">JSON</span>, field{" "}
          <code>text</code> = the Dictated Text variable
        </li>
        <li><strong>Play</strong> the response (Watari&apos;s voice, <code>audio/mpeg</code>)</li>
        <li>Name the shortcut <strong>“Watari”</strong> → say “Hey Siri, Watari”.</li>
      </ol>
      <p>
        With AirPods connected to the phone, the same shortcut plays the reply in the AirPods — nothing
        extra to configure. iOS bans background mic for web pages, so a Siri Shortcut is the no-app,
        no-page path; Telegram voice notes are the backup.
      </p>

      <h2>Mentra OS glasses</h2>
      <p>
        The <code>glasses/</code> TypeScript bridge streams the glasses&apos; mic to the brain and shows
        the reply on the display; the brain still does the thinking. Register the app in the MentraOS
        console and wire its transcription stream to <code>sendUtterance()</code>. The brain link and
        device routing are already implemented; only those SDK calls are app-specific. The companion
        phone must be on the tailnet.
      </p>

      <h2>Home Assistant</h2>
      <p>
        Create a long-lived access token in HA (Profile → Security) and set <code>JARVIS_HA_URL</code> +{" "}
        <code>JARVIS_HA_TOKEN</code>. Watari reads device states (“is the door locked?”) and calls
        services (lights/scenes/climate/locks) — locks, alarms, and covers are{" "}
        <Link href="/security">confirm-gated</Link>. Local-first: the brain talks straight to your HA
        box over the tailnet/LAN, nothing via the cloud.
      </p>

      <h2>Remote PC control</h2>
      <p>
        An edge executor (<code>jarvis.edge.pc_agent</code>) connects out to the brain&apos;s{" "}
        <code>/control</code> socket, so the 24/7 brain can drive your laptop end-to-end from your phone
        — open apps, manage processes, run scripts. On Windows it installs as an elevated scheduled task.
        Every action still passes the enforced confirmation tier and the path/secret guards.
      </p>

      <div className="callout">
        <span className="k">Acceptance tests.</span> Each setup has a step-by-step test (TTFW, auto-route,
        barge-in, Siri voice, music room, proactive voice, shared memory) in <code>TODO-NOW.md §3</code>.
      </div>
    </>
  );
}
