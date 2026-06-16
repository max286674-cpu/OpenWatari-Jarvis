import Link from "next/link";

export default function Production() {
  return (
    <>
      <h1>Production readiness</h1>
      <p className="lead">
        How to know your Watari is ready for 24/7 use — and the gate that decides when to make a fork
        public.
      </p>

      <div className="callout warn">
        <span className="k">The gate.</span> Keep your repo <strong>private</strong> until: the test
        suite is green, the efficiency report meets its targets, and you&apos;ve made the decisions
        below. OpenWatari&apos;s own status and open items are tracked in <code>docs/AUDIT.md</code>.
      </div>

      <h2>Readiness checklist</h2>
      <table>
        <thead><tr><th>Check</th><th>How</th></tr></thead>
        <tbody>
          <tr><td>Tests green</td><td><code>uv run python bench/run_all_tests.py</code> → all passed (SKIP is fine)</td></tr>
          <tr><td>Efficiency targets met</td><td><code>uv run python bench/efficiency_report.py</code> → every row OK/GOOD (watch streaming TTFT)</td></tr>
          <tr><td>Required keys set</td><td><code>uv run python bench/check_config.py</code> → TTS, STT, brain LLM, vault present</td></tr>
          <tr><td>Live integrations work</td><td><code>uv run python bench/test_live_integrations.py</code> → the keys you set respond</td></tr>
          <tr><td>Protocol passwords changed</td><td>the wizard generated them; confirm they aren&apos;t the placeholders</td></tr>
          <tr><td>Confirmation tier verified</td><td>ask it to send/delete something → it asks first, runs only after &quot;yes&quot;</td></tr>
          <tr><td>Voice enrolled (if shared space)</td><td><code>enroll_voice.py</code> + <code>JARVIS_SPEAKER_ID_ENABLED=true</code></td></tr>
          <tr><td>Tailnet on every device</td><td>brain reachable from laptop + phone over <code>100.x</code>; nothing public</td></tr>
          <tr><td>Vault writable only on the owner host</td><td><code>JARVIS_VAULT_WRITABLE=true</code> on the VPS, false on the laptop</td></tr>
          <tr><td>Proactivity decision</td><td><code>JARVIS_PROACTIVE_ENABLED</code> + quiet hours + budget tuned</td></tr>
          <tr><td>Fleet decision</td><td><code>JARVIS_FLEET_AUTHORIZED</code> stays false unless you mean it</td></tr>
          <tr><td>Device acceptance tests</td><td>walk <code>TODO-NOW.md §3</code> on each device (TTFW, barge-in, Siri voice, music room, proactive voice, shared memory)</td></tr>
        </tbody>
      </table>

      <h2>Run it as a service</h2>
      <ul>
        <li><strong>Brain (VPS, 24/7):</strong> run <code>python -m jarvis.brain.server</code> under systemd (it owns the reminder scheduler, proactive tick, and channels). Pattern in <code>deploy/vps/</code>.</li>
        <li><strong>Edge (laptop):</strong> Windows Task Scheduler / the helpers in <code>scripts/</code> so it auto-starts and reconnects.</li>
        <li><strong>Recurring reminders with the PC off:</strong> deploy the ticker in <code>deploy/vps/</code>.</li>
      </ul>

      <h2>What “done” looks like</h2>
      <p>
        Cold-boot the laptop → the edge auto-starts and reconnects to the brain. The wake word fires
        only on your voice and ignores the TV. A direct question answers in ~1 s; a hard one is
        delegated (if armed) with spoken progress. Vault search, Telegram, calendar work. A reminder
        fires proactively — spoken if you&apos;re listening, pushed if not — and you can answer it a
        minute or days later. Every consequential action is read back and confirmed. The suite is
        green and TTFT is within your tolerance.
      </p>

      <p>
        See the full audit and open items in <code>docs/AUDIT.md</code> and the per-phase evidence in{" "}
        <code>docs/PHASE-VERIFICATION.md</code>. For the credential walk-through, see{" "}
        <Link href="/setup">Setup &amp; keys</Link>.
      </p>
    </>
  );
}
