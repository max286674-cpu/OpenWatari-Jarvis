import Link from "next/link";

export default function Features() {
  return (
    <>
      <h1>Features — everything Watari can do</h1>
      <p className="lead">
        A complete tour of the capability surface. Every integration{" "}
        <strong>degrades gracefully</strong> — anything you haven&apos;t configured simply says
        &ldquo;that isn&apos;t set up yet&rdquo; instead of breaking. Tool schemas in{" "}
        <code>src/jarvis/brain/tools/</code> are the source of truth.
      </p>

      <h2>Voice (the whole point)</h2>
      <ul>
        <li><strong>Always-listening wake word</strong> — openWakeWord, configurable phrase, runs on CPU; a spoken acknowledgement (&ldquo;Yes, sir?&rdquo;) the instant it fires so you know it heard you.</li>
        <li><strong>Speech-to-text</strong> — Deepgram (cloud) or Whisper (local, auto-detects six languages incl. Armenian/Ukrainian). <Link href="/configuration">Cloud→local fallback</Link>.</li>
        <li><strong>Text-to-speech</strong> — ElevenLabs (cloud) or Piper / Kokoro (fully local, offline). Auto-falls-back to local if the cloud voice can&apos;t be built.</li>
        <li><strong>Barge-in</strong> — interrupt mid-sentence on headphones/AirPods/glasses (auto-detected private endpoints); half-duplex on open speakers so it never hears itself.</li>
        <li><strong>Streaming &amp; latency</strong> — speaks sentence-by-sentence as the model generates; instant pre-LLM acknowledgements mask first-token latency; per-turn TTFW logged.</li>
      </ul>

      <h2>His own mind</h2>
      <ul>
        <li><strong>Multi-provider LLM</strong> with an ordered failover chain (Groq direct and/or an OpenAI-compatible proxy); empty/slow responses fail over automatically; providers are warmed at startup to cut cold-start latency.</li>
        <li>
          <strong>Layered memory</strong> (<Link href="/architecture#memory">details</Link>): L1 learned
          facts, L2 daily journal, L3 your Obsidian vault, L4 hot cache (Redis), L5 semantic recall by
          meaning. A background self-improvement pass quietly learns durable facts about you.
        </li>
        <li><strong>Conversation memory</strong> shared across every device (one brain), with a smart idle-reset so a new chat hours later doesn&apos;t drag stale context — and restart-durable so a reboot resumes mid-thread.</li>
      </ul>

      <h2>Proactive companion</h2>
      <ul>
        <li><strong>Initiates on its own</strong> — routine, calendar, unread, open threads, self-health — within a daily budget + quiet hours so it&apos;s a companion, not a nag.</li>
        <li><strong>Morning voice briefing</strong> — what&apos;s overdue, due today, this week&apos;s deadlines, and recurring tasks, spoken (or a phone voice-note if you&apos;re away).</li>
        <li><strong>Modes by voice</strong> — focus (hold nudges), lockdown (go quiet), guest, commute, panic.</li>
      </ul>

      <h2>Reminders &amp; true 24/7</h2>
      <ul>
        <li><strong>Reminders</strong> — one-shot, absolute time, or daily; spoken if you&apos;re there, pushed to your phone (ntfy) if not.</li>
        <li><strong>PC-off recurring</strong> — an always-on <Link href="/production">VPS ticker</Link> owns repeating reminders so they fire even with every personal device asleep.</li>
        <li><strong>Background task queue</strong> — hand off long work (deep research, a big build), keep chatting, ask &ldquo;how&apos;s that going?&rdquo;, and get a voice note when it finishes.</li>
      </ul>

      <h2>Channels &amp; knowledge</h2>
      <ul>
        <li><strong>Telegram</strong> — read your DMs (without marking them seen), send messages/files, proactive voice notes, and <em>stream music live</em> into a group voice chat.</li>
        <li><strong>Web</strong> — answer-with-sources search (Tavily) and keyless page scraping (Jina Reader); a real, visible browser (Playwright) that can log in with your credentials when you ask.</li>
        <li><strong>Notion</strong> — search/read/append/comment, and a full <strong>tasks dashboard</strong>: create, update, complete, delete tasks by voice.</li>
        <li><strong>Gmail &amp; Calendar</strong> — read/draft/send mail and read/create events (sending + writes are confirm-gated).</li>
        <li><strong>Smart home</strong> — Home Assistant device states + control (lights, scenes, climate, locks); locks/alarms confirm first. Local-first, no cloud.</li>
        <li><strong>Music</strong> — &ldquo;play X&rdquo; via YouTube Music (free), your Telegram playlist, or live into the music room.</li>
        <li><strong>Utilities belt (no keys)</strong> — weather, crypto, stocks, FX, unit/currency convert, news, Wikipedia, dictionary.</li>
      </ul>

      <h2>Control &amp; self-improvement</h2>
      <ul>
        <li><strong>This machine</strong> — create/delete files, list/kill/start processes, run shell (elevated raises a prompt), open apps — all behind the confirmation tier + path/secret guards.</li>
        <li><strong>Remote PC control</strong> — drive your laptop from your phone via an edge executor that connects out to the brain (no inbound ports).</li>
        <li><strong>Coding on its own source</strong> — read/write code, run the test suite, lint, and make <em>reversible-only</em> git commits (never force-push/reset); commits and pushes are confirm-first.</li>
        <li><strong>Protocols</strong> — password-gated routines: goodnight (stop), phoenix (restart self), ragnarok (restart the machine), backup, diagnostics, and more.</li>
      </ul>

      <h2>Identity &amp; safety</h2>
      <ul>
        <li><strong>Speaker biometrics</strong> — optional ECAPA voiceprint so it responds only to <em>your</em> voice and ignores the TV or a guest.</li>
        <li><strong>Enforced confirm-tier</strong> on every outward/destructive action, hard guards on secrets and protected paths, and an audit log with value-scrubbing.</li>
        <li><strong><Link href="/personalize">Configurable identity</Link></strong> — name, address, languages, persona — all from config.</li>
      </ul>

      <h2>Optional: an agent fleet</h2>
      <p>
        For deep multi-step domain work, Watari can delegate to an external{" "}
        <strong>OpenClaw</strong> fleet via a single team-lead agent — but it ships{" "}
        <strong>fully disabled with no host baked in</strong>. Most users never need it; enable it only
        if you run your own gateway (see <Link href="/security">Security</Link>).
      </p>

      <div className="callout">
        <span className="k">Devices.</span> All of the above reaches you on laptop, Mac, iPhone,
        Android, Mentra glasses, Home Assistant, and a remotely-controlled PC — see{" "}
        <Link href="/devices">Devices</Link> and <Link href="/phones">Phones</Link>.
      </div>
    </>
  );
}
