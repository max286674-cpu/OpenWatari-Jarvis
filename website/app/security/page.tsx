export default function Security() {
  return (
    <>
      <h1>Security</h1>
      <p className="lead">
        Watari runs shell commands, drives a browser, sends messages, and edits its own code. The
        safety model makes that trustworthy: least surprise, full reversibility, deny-by-default.
      </p>
      <div className="callout">
        Full detail is in <code>SECURITY.md</code> in the repo. This page is the summary; read the file
        before you deploy.
      </div>

      <h2>Confirmation tier — enforced in code</h2>
      <p>
        Outward-facing or destructive tools (send a message/email, delete a file, kill a process, run
        PowerShell, write to Notion/calendar, smart-home locks, self-edits/commits, run a protocol) are
        in a confirmation tier that is <strong>enforced in the agent&apos;s execution path</strong> —
        not merely requested in the prompt. The agent <em>blocks</em> the first attempt, reads the
        action back, and runs it only after your next turn affirms it. One “yes” authorises exactly one
        action. So even a weak model that ignores the prompt cannot fire a consequential tool unprompted.
        Reads and lookups are never gated.
      </p>

      <h2>Secrets</h2>
      <ul>
        <li>All secrets live in a git-ignored <code>.env</code>; only <code>.env.example</code> (no values) is committed.</li>
        <li>Sessions, <code>voiceprint.json</code>, the audit log, browser profile, and private memory are git-ignored too.</li>
        <li>The audit log redacts secrets two ways: by argument key, and by scrubbing any real <code>.env</code> value from results.</li>
        <li>Use the narrowest token scopes (fine-grained GitHub PAT, Notion deny-by-default sharing, your own Google OAuth app).</li>
      </ul>

      <h2>Guardrails</h2>
      <ul>
        <li><strong>Filesystem</strong> — deletes refuse protected paths and Watari&apos;s own secrets/state; no traversal.</li>
        <li><strong>Self-improvement</strong> — repo-scoped, secret-blocked; reversible-only git (no reset/force-push/rebase/branch-delete — a revert is a new commit); tests run before trusting a change.</li>
        <li><strong>Elevation</strong> — admin PowerShell is explicit; nothing silently elevates.</li>
        <li><strong>Speaker biometrics</strong> — optional; obeys only your enrolled voice, fails open until enrolled.</li>
        <li><strong>External fleet</strong> — deny-by-default; armed deliberately.</li>
      </ul>

      <h2>Network posture</h2>
      <ul>
        <li>Local-first: audio, wake word, VAD, and optionally STT/TTS run on your machine.</li>
        <li>The brain binds loopback by default; off-loopback requires the bearer token <em>and</em> should sit on a private Tailnet, never the public internet.</li>
        <li>An unconfigured integration makes no network calls at all.</li>
      </ul>

      <h2>Reporting</h2>
      <p>
        Found a way to bypass the path/secret guards, the confirmation tier, or a protocol password?
        Report it privately to the repository owner, not as a public issue.
      </p>
    </>
  );
}
