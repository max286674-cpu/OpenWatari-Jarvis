import Link from "next/link";

export default function Phones() {
  return (
    <>
      <h1>Phones — iPhone &amp; Android</h1>
      <p className="lead">
        Talk to Watari from your phone with <strong>no app and no web page</strong> — just the
        built-in voice assistant calling the brain&apos;s <code>/talk</code> endpoint over your{" "}
        <Link href="/networking">Tailnet</Link>. Below: the full iPhone Siri Shortcut (the one most
        people want), the Android equivalents, and the gotchas we hit so you don&apos;t.
      </p>

      <h2>Before you start</h2>
      <ol>
        <li>Both the phone and the brain host are on the same <Link href="/networking">Tailscale tailnet</Link>.</li>
        <li>The brain is reachable on its HTTP sidecar (port <code>8766</code>):
          <pre><code>{`# on the brain host (VPS or laptop):
JARVIS_BRAIN_HOST=0.0.0.0  uv run python -m jarvis.brain.server
# -> HTTP sidecar on http://0.0.0.0:8766  (POST /talk, GET /healthz)`}</code></pre>
        </li>
        <li>You have your <code>JARVIS_API_AUTH_TOKEN</code> (any non-empty token enables auth; required for non-loopback access).</li>
        <li>Note the brain&apos;s <strong>tailnet IP</strong> (e.g. <code>100.x.y.z</code>) — use it, not the LAN IP, so it works anywhere.</li>
      </ol>

      <h2>iPhone — the Siri Shortcut (step by step)</h2>
      <p>Open the <strong>Shortcuts</strong> app → <strong>+</strong> (new shortcut) → add these actions in order:</p>
      <ol>
        <li>
          <strong>Dictate Text</strong> — captures your speech.{" "}
          <em>(Russian iOS: it&apos;s &ldquo;Продиктовать текст&rdquo;. Set its language to the one you&apos;ll speak.)</em>
        </li>
        <li>
          <strong>Get Contents of URL</strong> — the request to the brain:
          <ul>
            <li><strong>URL</strong>: <code>http://&lt;brain-tailnet-ip&gt;:8766/talk?token=&lt;YOUR_TOKEN&gt;</code></li>
            <li><strong>Method</strong>: <span className="kbd">POST</span></li>
            <li><strong>Request Body</strong>: <span className="kbd">JSON</span></li>
            <li>Add <strong>one field</strong>: key <code>text</code>, value = the <strong>Dictated Text</strong> variable (tap to insert the magic variable — don&apos;t type the words).</li>
            <li><strong>Headers</strong>: none needed — the token rides in the URL query string. (You can instead send the body as <code>{`{"text": "...", "token": "..."}`}</code> if you prefer.)</li>
          </ul>
        </li>
        <li>
          <strong>Play</strong> the response — the endpoint returns Watari&apos;s voice as{" "}
          <code>audio/mpeg</code>, so &ldquo;Play&rdquo; speaks it in his ElevenLabs voice.
        </li>
        <li>Name the shortcut, then trigger it with &ldquo;Hey Siri, &lt;name&gt;&rdquo;.</li>
      </ol>

      <div className="callout">
        <span className="k">Siri-name gotcha (important).</span> Siri matches the shortcut name{" "}
        <em>phonetically in your phone&apos;s language</em>. On a Russian iPhone, &ldquo;Watari&rdquo;
        transcribes to Cyrillic and never matches a Latin name — so Siri won&apos;t launch it. Fix:
        name the shortcut something your Siri reliably hears in its own language (e.g. Cyrillic{" "}
        <code>Джарвис</code>, or a simple word/number). The <em>spoken name</em> and the{" "}
        <Link href="/personalize">assistant&apos;s identity</Link> are independent — the shortcut name
        is just the Siri trigger.
      </div>

      <h3>Simpler all-iOS variant (Siri&apos;s own voice, no audio decode)</h3>
      <p>
        Add <code>&amp;format=text</code> to the URL and use <strong>Speak Text</strong> on the JSON{" "}
        <code>reply</code> field instead of &ldquo;Play&rdquo;. This uses the Siri voice and works on
        any iOS — handy if audio playback is ever fiddly.
      </p>
      <pre><code>{`http://<brain-tailnet-ip>:8766/talk?token=<YOUR_TOKEN>&format=text`}</code></pre>

      <h3>With AirPods</h3>
      <p>
        Connect AirPods to the <strong>iPhone</strong> and run the same shortcut — iOS routes the
        reply into the AirPods automatically, and dictation uses their mic. Nothing extra to set.
      </p>

      <h2>Android — two ways</h2>
      <ul>
        <li>
          <strong>No-app voice (mirror of the iPhone shortcut):</strong> use{" "}
          <a href="https://tasker.joaoapps.com/" target="_blank" rel="noreferrer">Tasker</a>, HTTP
          Shortcuts, or a Google Assistant routine to POST your dictated text to{" "}
          <code>http://&lt;brain-tailnet-ip&gt;:8766/talk?token=…</code> and play the audio reply.
          Declare the listening endpoint with the <code>android</code> (speaker) or{" "}
          <code>android-headphones</code> device hint so barge-in/routing behave.
        </li>
        <li>
          <strong>Full mic stream (Termux edge-lite):</strong> install{" "}
          <a href="https://f-droid.org/packages/com.termux/" target="_blank" rel="noreferrer">Termux</a>{" "}
          + Termux:Boot, run the Python edge there, and it streams mic → brain and plays TTS just like
          a laptop — wake word and barge-in included. Disable battery optimisation so it survives in
          the background.
        </li>
      </ul>
      <p>With earbuds on the phone, the <code>android-headphones</code> hint makes the session private (barge-in on) and the reply plays in the earbuds.</p>

      <h2>Troubleshooting</h2>
      <table>
        <thead><tr><th>Symptom</th><th>Cause &amp; fix</th></tr></thead>
        <tbody>
          <tr><td>Siri won&apos;t launch the shortcut</td><td>Name mismatch in your language — rename to something Siri hears reliably (see the gotcha above).</td></tr>
          <tr><td>&ldquo;Couldn&apos;t understand / repeat&rdquo;</td><td>The brain returned empty — usually an LLM provider hiccup. The failover chain + empty-response retry fix this; make sure the brain is current and a fast primary (e.g. Groq) is set.</td></tr>
          <tr><td>&ldquo;Time limited&rdquo; / shortcut times out</td><td>The turn took too long. Use a fast primary model and keep the brain on the always-on host; typical <code>/talk</code> is ~3s.</td></tr>
          <tr><td>401 Unauthorized</td><td>The <code>?token=</code> doesn&apos;t match <code>JARVIS_API_AUTH_TOKEN</code> on the brain.</td></tr>
          <tr><td>Can&apos;t connect at all</td><td>Brain not bound to <code>0.0.0.0</code>, phone not on the tailnet, or a firewall blocks <code>8765/8766</code>. Prefer the tailnet IP; on Windows allow those ports inbound.</td></tr>
          <tr><td>File-path requests fail</td><td>Use forward slashes in paths (<code>C:/tmp/x.txt</code>) — backslashes break the JSON body.</td></tr>
        </tbody>
      </table>

      <div className="callout">
        <span className="k">Backup channel.</span> If dictation is ever flaky, the same brain answers
        over <Link href="/devices">Telegram</Link> as text — and can reply with a voice note.
      </div>
    </>
  );
}
