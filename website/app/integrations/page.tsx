import Link from "next/link";

export default function Integrations() {
  return (
    <>
      <h1>Integrations &amp; enabling tools</h1>
      <p className="lead">
        Every capability is wired and tested; you switch each one on by adding its key/credential.
        Anything you skip <strong>degrades gracefully</strong> — Watari just says &ldquo;that
        isn&apos;t configured yet&rdquo;. Set values in <code>.env</code> (or answer the{" "}
        <Link href="/quickstart">setup wizard</Link>).
      </p>

      <div className="callout">
        <span className="k">How enabling works.</span> Tools register at startup regardless; a tool
        becomes <em>usable</em> when its credential is present. So you can enable integrations one at a
        time, restart the brain, and they light up. Reads are frictionless; outward/destructive
        actions (send, delete, spend, lock) are always confirm-gated.
      </div>

      <h2 id="telegram">Telegram — read DMs, send, voice notes</h2>
      <p>Telegram has up to three roles; add only what you want:</p>
      <h3>a) Read your DMs (Telethon user client)</h3>
      <p>The Bot API can&apos;t read your DMs, so reading needs a one-time user login.</p>
      <ol>
        <li>Get an <strong>api_id</strong> + <strong>api_hash</strong> at <a href="https://my.telegram.org" target="_blank" rel="noreferrer">my.telegram.org</a> → API development tools.</li>
        <li>In <code>.env</code>:
          <pre><code>{`JARVIS_TELEGRAM_API_ID=...
JARVIS_TELEGRAM_API_HASH=...
JARVIS_TELEGRAM_PHONE=+15551234567   # your number, for the one-time sign-in`}</code></pre>
        </li>
        <li>One-time interactive login (creates the gitignored <code>jarvis.session</code>):
          <pre><code>{`uv run python bench/telegram_login.py   # enter the code Telegram texts you`}</code></pre>
        </li>
      </ol>
      <p>Verify: <em>&ldquo;read me my last messages with Anna&rdquo;</em> (reads without marking them seen),
        <em> &ldquo;any unread Telegram?&rdquo;</em>. Tools: <code>check_telegram</code>, <code>read_chat</code>, <code>mark_telegram</code>.</p>

      <h3>b) DM Watari 24/7 (a dedicated bridge bot)</h3>
      <p>
        So you can text Watari from any device, give it its <strong>own</strong> bot — separate from
        any other bot you run (two pollers on one token steal each other&apos;s messages).
      </p>
      <ol>
        <li>In Telegram, message <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> → <code>/newbot</code> → copy the token.</li>
        <li><pre><code>{`JARVIS_TELEGRAM_BRIDGE_BOT_TOKEN=123456:ABC...`}</code></pre></li>
      </ol>
      <p>Now DM that bot — the same shared brain answers, so Telegram and voice share one memory. It can reply with a <strong>voice note</strong> for proactive nudges.</p>

      <h3>c) Send messages / GIFs (bot)</h3>
      <pre><code>{`JARVIS_TELEGRAM_BOT_TOKEN=...        # can be the same as the bridge bot
JARVIS_TELEGRAM_DEFAULT_CHAT=...     # your chat id, the default recipient`}</code></pre>
      <p>Verify: <em>&ldquo;tell Anna I&apos;ll be five minutes late&rdquo;</em> (it confirms first). GIFs: <em>&ldquo;@gif panda&rdquo;</em>.</p>

      <h2 id="music-room">Music Room — stream music live into a group call</h2>
      <p>
        The Music Room plays a track <strong>live inside a Telegram group voice chat</strong> (via
        pytgcalls) — so you hear it on your phone when you join that call, not as a file. It needs the
        Telethon <em>user</em> login (a) above and the <code>channels</code> extra.
      </p>
      <ol>
        <li>Install the streaming deps: <pre><code>{`uv sync --extra channels`}</code></pre></li>
        <li>Create a Telegram <strong>group</strong> (or use one you own) and <strong>start a voice chat</strong> in it.</li>
        <li>Get the group&apos;s id (a <code>-100…</code> number). Easiest: add <a href="https://t.me/myidbot" target="_blank" rel="noreferrer">@myidbot</a> to the group, or read it from <code>read_chat</code>.</li>
        <li>In <code>.env</code>:
          <pre><code>{`JARVIS_TELEGRAM_MUSIC_ROOM_CHAT=-1001234567890`}</code></pre>
        </li>
      </ol>
      <p>
        Then: <em>&ldquo;play lo-fi in the music room.&rdquo;</em> Watari joins that group&apos;s voice
        chat and streams the track into the call. <strong>Open the group&apos;s voice chat on your
        phone and join</strong> to hear it live. <em>&ldquo;stop the music&rdquo;</em> leaves the call.
        (Only the user account can stream into a call — a bot can&apos;t join voice chats.)
      </p>
      <p>
        Prefer files on your phone instead? Set a <strong>personal playlist</strong> chat and use{" "}
        <code>telegram_music</code>: <code>JARVIS_TELEGRAM_PLAYLIST_CHAT</code> (a chat/group of audio
        tracks). <code>local=true</code> plays out loud on the desktop; default delivers to your phone
        Telegram to tap-and-play. Or just <em>&ldquo;play X&rdquo;</em> — default source is free
        YouTube Music (no account).
      </p>

      <h2 id="web">Web search &amp; page reading</h2>
      <pre><code>{`JARVIS_TAVILY_API_KEY=...     # web_search (answer + sources); free tier at tavily.com
# scrape_url uses Jina Reader — FREE + KEYLESS; JARVIS_JINA_API_KEY only raises rate limits`}</code></pre>
      <p>Verify: <em>&ldquo;what&apos;s the latest on X&rdquo;</em> (search), <em>&ldquo;open this URL and read the headline&rdquo;</em> (scrape). The visible local <code>browser</code> tool needs no key.</p>

      <h2 id="notion">Notion — pages &amp; the tasks dashboard</h2>
      <ol>
        <li>Create an <strong>internal integration</strong> at <a href="https://www.notion.so/my-integrations" target="_blank" rel="noreferrer">notion.so/my-integrations</a> → copy the secret (<code>ntn_…</code>). <code>JARVIS_NOTION_TOKEN=ntn_…</code></li>
        <li><strong>Share</strong> each page/database with the integration: open it → ••• → Connections → add your integration. (Notion is deny-by-default.)</li>
        <li>For the <strong>tasks dashboard</strong>, share your Tasks database and set its id (the 32-hex chunk in its URL):
          <pre><code>{`JARVIS_NOTION_TASKS_DB_ID=9c5a572c...bd68`}</code></pre>
        </li>
      </ol>
      <p>Verify: <em>&ldquo;what&apos;s on my plate today?&rdquo;</em>, <em>&ldquo;add a task to call the bank Friday&rdquo;</em>, <em>&ldquo;mark groceries done&rdquo;</em>. A morning voice briefing reads overdue + today + this-week deadlines + recurring tasks. Tools: <code>notion_tasks</code>, <code>notion_create_task / update / complete / delete</code>, plus <code>notion_search / read_page / append / comment / create_page</code>.</p>

      <h2 id="google">Gmail + Google Calendar (one OAuth app)</h2>
      <ol>
        <li>In <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">Google Cloud Console</a>: new project → enable <strong>Gmail API</strong> + <strong>Calendar API</strong> → OAuth consent screen (External, add yourself as a test user) → create an <strong>OAuth client (Web)</strong> with redirect <code>http://127.0.0.1:8585/oauth2callback</code>.</li>
        <li><pre><code>{`JARVIS_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
JARVIS_GOOGLE_CLIENT_SECRET=...`}</code></pre></li>
        <li>One-time login → paste the refresh token it prints:
          <pre><code>{`uv run python bench/google_login.py
# -> JARVIS_GOOGLE_REFRESH_TOKEN=1//0g...`}</code></pre>
        </li>
      </ol>
      <p>Verify: <em>&ldquo;read my unread email&rdquo;</em>, <em>&ldquo;what&apos;s on my calendar today?&rdquo;</em>. Sending mail + creating events are confirm-gated.</p>

      <h2 id="ha">Home Assistant (smart home)</h2>
      <pre><code>{`JARVIS_HA_URL=http://homeassistant.local:8123   # or the IP
JARVIS_HA_TOKEN=...   # Profile -> Security -> Long-lived access token`}</code></pre>
      <p>Verify: <em>&ldquo;is the front door locked?&rdquo;</em> (<code>ha_state</code>), <em>&ldquo;turn on the living-room lights&rdquo;</em> (<code>ha_call</code>). Locks, alarms, covers confirm first. Local-first — the brain talks straight to your HA box, nothing via the cloud.</p>

      <h2 id="push">Phone push (ntfy) &amp; recurring reminders</h2>
      <pre><code>{`JARVIS_NTFY_TOPIC=watari-<your-unguessable-string>
JARVIS_NTFY_SERVER=https://ntfy.sh`}</code></pre>
      <p>Install the <strong>ntfy</strong> app and subscribe to that topic. Reminders fire as a phone push when you&apos;re away from the mic. One-shot/at reminders even fire with the PC off (ntfy holds them). For <strong>recurring</strong> reminders with the PC off, deploy the always-on VPS ticker — see <Link href="/production">Production readiness</Link>.</p>

      <h2 id="biometrics">Respond only to your voice (speaker biometrics)</h2>
      <pre><code>{`uv sync --extra identity
uv run python bench/enroll_voice.py --script "to-read-script.md"   # ~3 min
# then in .env:
JARVIS_SPEAKER_ID_ENABLED=true`}</code></pre>
      <p>After enrolling, Watari obeys only your enrolled voice and ignores the TV or a guest. Until you enroll it answers anyone (so it never locks you out). Tune strictness with <code>JARVIS_SPEAKER_THRESHOLD</code>.</p>

      <h2 id="browser">Cloud browser (optional)</h2>
      <pre><code>{`JARVIS_BROWSERBASE_API_KEY=...
JARVIS_BROWSERBASE_PROJECT_ID=...
uv sync --extra browse`}</code></pre>
      <p>For headless <code>browse_web</code>. The local <em>visible</em> <code>browser</code> tool (Playwright) already works without this — <code>uv sync --extra browse &amp;&amp; playwright install chromium</code>.</p>

      <h2 id="fleet">Optional: an external specialist fleet</h2>
      <p>
        For deep multi-step work Watari can delegate to an external OpenClaw gateway via a single
        team-lead agent. It ships <strong>fully disabled with no host baked in</strong>. Enable only if
        you run your own gateway:
      </p>
      <pre><code>{`JARVIS_OPENCLAW_GATEWAY_URL=http://<your-gateway>:3200
JARVIS_OPENCLAW_TOKEN=...
JARVIS_FLEET_AUTHORIZED=true   # opt-in; it reaches shared infra`}</code></pre>
      <p>Most users never need it — see <Link href="/security">Security</Link>.</p>

      <div className="callout good">
        <span className="k">No keys needed.</span> The utilities belt (weather, crypto, stocks, FX,
        news, Wikipedia, dictionary, unit/currency convert), local music (YouTube Music), page scraping
        (Jina), reminders, the task queue, system control, and coding tools all work out of the box.
      </div>
    </>
  );
}
