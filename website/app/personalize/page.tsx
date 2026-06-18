import Link from "next/link";

export default function Personalize() {
  return (
    <>
      <h1>Personalize — make it yours</h1>
      <p className="lead">
        OpenWatari ships one generic persona <em>template</em>. Your assistant&apos;s name, what it
        calls you, and the languages it speaks all come from config — so the same code becomes{" "}
        <em>your</em> assistant without editing a single prompt or source file.
      </p>

      <h2>The five identity settings</h2>
      <table>
        <thead>
          <tr><th>Setting</th><th>What it does</th><th>Example</th></tr>
        </thead>
        <tbody>
          <tr><td><code>JARVIS_ASSISTANT_NAME</code></td><td>what it calls itself</td><td><code>Watari</code>, <code>Aria</code>, <code>Jeeves</code></td></tr>
          <tr><td><code>JARVIS_USER_NAME</code></td><td>your name (blank = none)</td><td><code>Dana</code></td></tr>
          <tr><td><code>JARVIS_USER_ADDRESS</code></td><td>how it addresses you</td><td><code>sir</code>, <code>ma&apos;am</code>, <code>boss</code>, or blank</td></tr>
          <tr><td><code>JARVIS_UNDERSTOOD_LANGUAGES</code></td><td>languages it can understand</td><td><code>English, Spanish</code></td></tr>
          <tr><td><code>JARVIS_REPLY_LANGUAGE</code></td><td>the one language it replies in</td><td><code>English</code></td></tr>
        </tbody>
      </table>

      <p>Drop them in <code>.env</code> (or answer the <Link href="/quickstart">setup wizard</Link>):</p>
      <pre><code>{`JARVIS_ASSISTANT_NAME=Aria
JARVIS_USER_NAME=Dana
JARVIS_USER_ADDRESS=ma'am
JARVIS_UNDERSTOOD_LANGUAGES=English, Spanish
JARVIS_REPLY_LANGUAGE=English`}</code></pre>

      <p>
        That alone yields: <em>&ldquo;You are Aria, Dana&apos;s personal voice assistant. Address Dana
        as ma&apos;am. They may speak English, Spanish — understand any of them, but always reply in
        English.&rdquo;</em> Leave a field blank and the prose adapts gracefully (no name → &ldquo;your
        personal assistant&rdquo;; no honorific → &ldquo;address them naturally&rdquo;).
      </p>

      <h2>How it works</h2>
      <p>
        The persona file (<code>personality/jarvis.md</code>, or whatever{" "}
        <code>JARVIS_PERSONA_FILE</code> points at) is a template with{" "}
        <code>{"{assistant_name}"}</code>, <code>{"{owner_possessive}"}</code>,{" "}
        <code>{"{address_line}"}</code> and <code>{"{language_line}"}</code> tokens.{" "}
        <code>build_system_prompt()</code> fills them from config at every turn — verified in{" "}
        <code>bench/test_identity.py</code> (which also asserts no unfilled token ever leaks into the
        prompt). A generic starting point lives at <code>personality/persona.example.md</code>.
      </p>

      <h2>Going deeper: persona &amp; profile</h2>
      <ul>
        <li>
          <strong>Rewrite the voice.</strong> Edit the prose in your persona file (tone, manner,
          boundaries) — keep the <code>{"{tokens}"}</code> and they&apos;ll still be filled. Point{" "}
          <code>JARVIS_PERSONA_FILE</code> at a different file to keep several personas.
        </li>
        <li>
          <strong>Give it knowledge about you (your profile).</strong> The Markdown files under{" "}
          <code>memory/</code> (who you are, your projects, your environment) are injected as
          long-term context. These are <em>yours</em> — fill them with your life, and keep them out
          of any public fork (they&apos;re your private profile, not framework code).
        </li>
        <li>
          <strong>Wake word.</strong> Independent of the name — see{" "}
          <Link href="/configuration">Configuration</Link> (<code>JARVIS_WAKE_WORDS</code>). The
          spoken name and the wake word can differ (e.g. wake on &ldquo;hey jarvis&rdquo;, identify as
          &ldquo;Aria&rdquo;).
        </li>
      </ul>

      <div className="callout">
        <span className="k">Local-first.</span> Identity is pure config — nothing is sent anywhere to
        personalize. Pair it with local STT/TTS (<Link href="/configuration">whisper + piper</Link>)
        for a fully offline, fully personal assistant.
      </div>
    </>
  );
}
