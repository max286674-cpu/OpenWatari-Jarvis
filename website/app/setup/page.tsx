import Link from "next/link";

export default function Setup() {
  return (
    <>
      <h1>Setup &amp; keys — from <code>git clone</code> to talking</h1>
      <p className="lead">
        Everything a developer needs to stand up their own Watari: install, get every key, integrate
        each component, and run the tests. <code>TODO-NOW.md</code> in the repo is the exhaustive,
        copy-paste version of this page.
      </p>

      <h2>0 · Prerequisites</h2>
      <ul>
        <li><strong>Python 3.11+</strong> and <a href="https://github.com/astral-sh/uv" target="_blank" rel="noreferrer">uv</a>.</li>
        <li><strong>Node 18+</strong> only if you also build this docs site.</li>
        <li><strong>Tailscale</strong> on every device for a multi-device deploy (see <Link href="/networking">Networking</Link>).</li>
        <li>An always-on host (a small Linux VPS) if you want the 24/7 brain.</li>
      </ul>

      <h2>1 · Clone &amp; install</h2>
      <pre><code>{`git clone https://github.com/iamvazghen/OpenWatari openwatari
cd openwatari
uv sync --extra edge --extra cloud-voice --extra brain --extra channels --extra identity --extra dev
uv run jarvis-setup        # interactive .env generator`}</code></pre>

      <h2>2 · Get the keys</h2>
      <p>
        All keys live in <code>.env</code> (prefix <code>JARVIS_</code>). Everything degrades
        gracefully — set only what you want. <strong>Required</strong> to function: a voice (TTS), an
        ear (STT), a brain (LLM), and the vault path.
      </p>
      <table>
        <thead><tr><th>Component</th><th>Key(s)</th><th>Where to get it</th><th>Tier</th></tr></thead>
        <tbody>
          <tr><td>TTS voice</td><td><code>JARVIS_ELEVENLABS_API_KEY</code>, <code>_VOICE_ID</code></td><td>elevenlabs.io → Profile → API key; pick a voice, copy its ID (or use local Piper, no key)</td><td>Required</td></tr>
          <tr><td>STT</td><td><code>JARVIS_DEEPGRAM_API_KEY</code></td><td>deepgram.com (free tier). For Armenian/Ukrainian use local Whisper instead (no key)</td><td>Required</td></tr>
          <tr><td>Brain LLM</td><td><code>JARVIS_FREELLMAPI_BASE_URL</code> + <code>_API_KEY</code></td><td>any OpenAI-compatible endpoint: a free proxy, OpenAI (<code>api.openai.com/v1</code>), or local Ollama</td><td>Required</td></tr>
          <tr><td>Vault (L3 memory)</td><td><code>JARVIS_VAULT_PATH</code></td><td>path to your Obsidian/Markdown folder; <code>JARVIS_VAULT_WRITABLE=true</code> only on the host that owns it</td><td>Required</td></tr>
          <tr><td>Web search</td><td><code>JARVIS_TAVILY_API_KEY</code></td><td>tavily.com (scraping uses keyless Jina Reader)</td><td>Recommended</td></tr>
          <tr><td>Telegram</td><td><code>JARVIS_TELEGRAM_API_ID</code>, <code>_API_HASH</code>, <code>_BOT_TOKEN</code>, <code>_PHONE</code></td><td>my.telegram.org (api id/hash) + @BotFather (bot token); then <code>uv run python bench/telegram_login.py</code> once</td><td>Recommended</td></tr>
          <tr><td>Gmail + Calendar</td><td><code>JARVIS_GOOGLE_CLIENT_ID</code>, <code>_SECRET</code>, <code>_REFRESH_TOKEN</code></td><td>console.cloud.google.com: enable Gmail + Calendar APIs, make a Web OAuth client, add the redirect, then <code>uv run python bench/google_login.py</code></td><td>Recommended</td></tr>
          <tr><td>Notion</td><td><code>JARVIS_NOTION_TOKEN</code></td><td>notion.so/my-integrations → internal integration; share the pages you want it to touch</td><td>Optional</td></tr>
          <tr><td>Home Assistant</td><td><code>JARVIS_HA_URL</code>, <code>JARVIS_HA_TOKEN</code></td><td>HA → Profile → Security → long-lived access token</td><td>Optional</td></tr>
          <tr><td>Phone push</td><td><code>JARVIS_NTFY_TOPIC</code></td><td>pick an unguessable string; subscribe to it in the ntfy app</td><td>Recommended</td></tr>
          <tr><td>Self-improvement push</td><td><code>JARVIS_GITHUB_TOKEN</code>, <code>JARVIS_GITHUB_REPO</code></td><td>github.com/settings/tokens → fine-grained PAT, Contents: read/write on your repo</td><td>Optional</td></tr>
          <tr><td>Cloud browser</td><td><code>JARVIS_BROWSERBASE_API_KEY</code>, <code>_PROJECT_ID</code></td><td>browserbase.com (the local visible browser needs no key)</td><td>Optional</td></tr>
          <tr><td>Custom wake phrase</td><td><code>JARVIS_PORCUPINE_ACCESS_KEY</code></td><td>console.picovoice.ai (the pre-trained phrases need no key)</td><td>Optional</td></tr>
        </tbody>
      </table>
      <div className="callout">
        The wizard auto-generates the multi-device <code>JARVIS_API_AUTH_TOKEN</code> and all eight
        <code>JARVIS_PROTOCOL_*_PASSWORD</code> values for you — you don&apos;t fetch those anywhere.
      </div>

      <h2>3 · Integrate the components</h2>
      <ul>
        <li><strong>Vault</strong> — point <code>JARVIS_VAULT_PATH</code> at your notes; it&apos;s validated at startup.</li>
        <li><strong>Telegram / Google</strong> — run the one-time login helpers in <code>bench/</code> (they print a token or create a session file).</li>
        <li><strong>Redis (optional L4)</strong> — set <code>JARVIS_REDIS_URL</code>; otherwise an in-process cache is used.</li>
        <li><strong>Semantic recall (optional L5)</strong> — <code>uv pip install sentence-transformers</code> (downloads a ~90 MB CPU model on first use).</li>
        <li><strong>Multi-device</strong> — Tailscale on every device, then set <code>JARVIS_BRAIN_HOST=0.0.0.0</code> and the brain WS URL to the tailnet IP (the wizard&apos;s <em>vps</em> mode does this).</li>
        <li><strong>Voice enrollment</strong> — <code>uv run python bench/enroll_voice.py --script &quot;to-read-script.md&quot;</code>, then <code>JARVIS_SPEAKER_ID_ENABLED=true</code>.</li>
      </ul>

      <h2>4 · Run the tests</h2>
      <pre><code>{`uv run python bench/run_all_tests.py        # the single gate (offline; SKIP != FAIL)
uv run python bench/check_config.py         # which keys are set
uv run python bench/efficiency_report.py    # hot-path latency vs targets
uv run python bench/test_live_integrations.py  # exercises the keys you actually set`}</code></pre>

      <h2>5 · Run it</h2>
      <pre><code>{`uv run python -m jarvis.edge.assistant      # local voice loop
uv run python -m jarvis.brain.server        # the shared 24/7 brain (phone/glasses)`}</code></pre>
      <p>
        Then see <Link href="/production">Production readiness</Link> for the go-live checklist, and
        edit <code>personality/jarvis.md</code> to make it yours.
      </p>
    </>
  );
}
