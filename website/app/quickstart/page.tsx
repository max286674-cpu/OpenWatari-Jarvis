import Link from "next/link";

export default function QuickStart() {
  return (
    <>
      <h1>Quick start</h1>
      <p className="lead">Install, configure with the wizard, and talk to Watari in about 5 minutes.</p>

      <p>
        Requires <strong>Python 3.11+</strong> and{" "}
        <a href="https://github.com/astral-sh/uv" target="_blank" rel="noreferrer">
          uv
        </a>
        . For a multi-device deployment you also need <Link href="/networking">Tailscale</Link> on
        every device.
      </p>

      <h2>1 · Clone &amp; install</h2>
      <pre>
        <code>{`git clone https://github.com/iamvazghen/OpenWatari openwatari
cd openwatari

# Install the base + the stack you want (also installs the \`jarvis-setup\` CLI):
uv sync --extra edge --extra cloud-voice --extra brain --extra channels --extra identity --extra dev
#   for a 100% local/offline voice stack: drop cloud-voice, add local-voice`}</code>
      </pre>
      <div className="callout warn">
        <span className="k">Note.</span> <code>uv sync</code> prunes extras you don&apos;t list —
        install the full set you intend to use in one command.
      </div>

      <h2 id="wizard">2 · Run the setup wizard</h2>
      <pre>
        <code>uv run jarvis-setup</code>
      </pre>
      <p>
        A terminal UI (Rich; falls back to plain text) walks you through the decisions and writes a
        ready <code>.env</code>. It never prints a secret back, backs up an existing <code>.env</code>,
        and auto-generates your brain auth token and all eight protocol passwords.
      </p>
      <table>
        <thead>
          <tr>
            <th>Step</th>
            <th>What it sets</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Identity</td><td>display name + wake phrase</td></tr>
          <tr><td>Voice</td><td>cloud (ElevenLabs + Deepgram) or local (Piper/Kokoro + Whisper)</td></tr>
          <tr><td>Brain</td><td>LLM backend: free proxy, OpenAI, or local Ollama</td></tr>
          <tr><td>Knowledge</td><td>path to your Obsidian/Markdown notes (L3 memory)</td></tr>
          <tr><td>Deployment</td><td><code>single</code> (loopback) or <code>vps</code> (binds 0.0.0.0 + token)</td></tr>
          <tr><td>Security</td><td>generates strong protocol passwords</td></tr>
          <tr><td>Integrations</td><td>optional: Telegram, Tavily, Google, Notion, ntfy</td></tr>
          <tr><td>Behaviour</td><td>proactivity on/off; fleet stays off by default</td></tr>
        </tbody>
      </table>

      <h2>3 · Verify</h2>
      <pre>
        <code>{`uv run python bench/run_all_tests.py     # the single gate — should be all green
uv run python bench/efficiency_report.py # hot-path latency vs targets`}</code>
      </pre>
      <div className="callout">
        <span className="k">Publish gate.</span> Keep your repo <strong>private</strong> until the
        suite is green and the efficiency report meets its targets.
      </div>

      <h2>4 · Talk to it</h2>
      <pre>
        <code>{`# Local voice loop on this machine:
uv run python -m jarvis.edge.assistant

# …or the shared 24/7 brain (for phone/glasses, over your tailnet):
uv run python -m jarvis.brain.server`}</code>
      </pre>

      <h2>5 · Finish setup</h2>
      <p>
        <code>TODO-NOW.md</code> in the repo is the full deployment checklist: Tailscale on every
        device, voice enrollment, the recurring-reminder ticker, Google/Notion/Telegram logins, and a
        device-by-device acceptance test (TTFW, barge-in, Siri voice, music room, proactive voice,
        shared memory). Then make it yours by editing <code>personality/jarvis.md</code>.
      </p>
    </>
  );
}
