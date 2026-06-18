import Link from "next/link";

export default function Home() {
  return (
    <>
      <div className="hero">
        <img src="/banner.png" alt="OpenWatari" />
      </div>
      <h1>OpenWatari</h1>
      <p className="lead">
        An open-source framework for building your own 24/7, voice-first, multi-device AI
        companion — <strong>Watari</strong>.
      </p>
      <p>
        <span className="badge v">MIT licensed</span>
        <span className="badge">Python 3.11+</span>
        <span className="badge">Local-first</span>
        <span className="badge">Self-hosted</span>
        <span className="badge">No GPU required</span>
      </p>

      <p>
        Clone it, run the <Link href="/quickstart#wizard">setup wizard</Link>, point it at the voice
        and LLM providers you like, and you have a personal assistant you <em>talk to</em>: it listens
        for a wake word, answers in a natural streaming voice, remembers across sessions, acts on your
        machine and your accounts, reaches you proactively when it matters, and can even improve its
        own code — safely and reversibly.
      </p>

      <div className="callout">
        <span className="k">Naming.</span> The project is <strong>OpenWatari</strong>; the assistant
        you build is <strong>Watari</strong>. <em>Jarvis</em> — the fictional assistant — is only the
        blueprint/inspiration; this is an independent, from-scratch implementation. The Python package
        and CLI keep the short internal name <code>jarvis</code> for stability.
      </div>

      <h2>What you get</h2>
      <ul>
        <li>
          <strong>Natural voice</strong> — wake word, multilingual understanding, streaming TTS with
          barge-in (talk over it on headphones).
        </li>
        <li>
          <strong>Its own mind</strong> — a reasoning LLM (any OpenAI-compatible endpoint) with a
          fallback chain, a tool-calling loop, and an editable Markdown personality.
        </li>
        <li>
          <strong>Six-layer memory</strong> — working context, durable learned facts, a daily journal,
          your Obsidian vault (read &amp; write), a hot-cache, and optional semantic recall.
        </li>
        <li>
          <strong>Acts</strong> — files, processes, PowerShell, a real browser, music, reminders &amp;
          push, Telegram, Gmail, Calendar, Notion, Home Assistant — each degrades gracefully when
          unconfigured.
        </li>
        <li>
          <strong>Proactive</strong> — speaks up within a budget and quiet hours, and remembers what it
          said so you can answer “yes, do that” a minute or ten days later.
        </li>
        <li>
          <strong>Self-improving</strong> — reads/edits its own source, runs its tests, makes reversible
          git commits, all confirm-gated.
        </li>
      </ul>

      <h2>One brain, every device</h2>
      <p>
        The brain runs 24/7 on an always-on host (a cheap VPS); the voice front-end runs wherever you
        are. A Windows/Linux laptop, a Mac, an iPhone or Android phone (no app), and Mentra OS glasses
        all reach the same brain and the same memory — connected privately over your{" "}
        <Link href="/networking">Tailnet</Link>. See <Link href="/devices">Devices</Link> for every
        supported setup.
      </p>

      <h2>Start here</h2>
      <div className="cards">
        <div className="card">
          <h3><Link href="/quickstart">Quick start →</Link></h3>
          <p>Install, run the wizard, and talk to it in 5 minutes.</p>
        </div>
        <div className="card">
          <h3><Link href="/integrations">Integrations & tools →</Link></h3>
          <p>Enable every capability — Telegram, Music Room, Notion, Gmail, vault, and more.</p>
        </div>
        <div className="card">
          <h3><Link href="/vault">Obsidian vault & memory →</Link></h3>
          <p>Connect your notes and switch on read/write long-term memory.</p>
        </div>
        <div className="card">
          <h3><Link href="/personalize">Personalize →</Link></h3>
          <p>Name it, set how it addresses you, and pick its languages — from config.</p>
        </div>
        <div className="card">
          <h3><Link href="/architecture">Architecture →</Link></h3>
          <p>The edge/brain split and the six memory layers.</p>
        </div>
        <div className="card">
          <h3><Link href="/security">Security →</Link></h3>
          <p>The enforced safety model to understand before you deploy.</p>
        </div>
      </div>

      <div className="footer">
        OpenWatari — a from-scratch, local-first companion framework. Jarvis was the inspiration, not
        the implementation.
      </div>
    </>
  );
}
