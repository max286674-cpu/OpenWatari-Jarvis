import Link from "next/link";

export default function Vault() {
  return (
    <>
      <h1>Obsidian vault &amp; memory</h1>
      <p className="lead">
        Watari has six layers of memory. Your Obsidian vault is the big one — its long-term, read
        (and optionally write) knowledge base. Here&apos;s how to connect it and switch on every
        memory capability.
      </p>

      <h2>The six layers</h2>
      <table>
        <thead><tr><th>Layer</th><th>What it is</th><th>Enable</th></tr></thead>
        <tbody>
          <tr><td><strong>L1 learned facts</strong></td><td>durable one-line facts it saves about you</td><td>on by default (<code>JARVIS_MEMORY_ENABLED=true</code>)</td></tr>
          <tr><td><strong>L2 journal</strong></td><td>a daily journal written at session end</td><td>on by default</td></tr>
          <tr><td><strong>L3 Obsidian vault</strong></td><td>your notes — searched &amp; read every session</td><td><code>JARVIS_VAULT_PATH</code> (below)</td></tr>
          <tr><td><strong>L4 hot cache</strong></td><td>Redis cache so lookups survive restarts</td><td><code>JARVIS_REDIS_URL</code> (optional)</td></tr>
          <tr><td><strong>L5 semantic recall</strong></td><td>recall by meaning, not just keywords</td><td><code>pip install sentence-transformers</code></td></tr>
          <tr><td><strong>Working</strong></td><td>this conversation; restart-durable, idle-reset</td><td>always on</td></tr>
        </tbody>
      </table>

      <h2>1 · Connect your Obsidian vault (L3)</h2>
      <p>Point Watari at the folder of Markdown notes you want it to read. In <code>.env</code>:</p>
      <pre><code>{`JARVIS_VAULT_PATH=C:\\Users\\you\\Documents\\Obsidian Vault   # Windows
# JARVIS_VAULT_PATH=/home/you/obsidian-vault                  # Linux/Mac`}</code></pre>
      <p>
        It&apos;s validated at startup (Watari warns loudly if the path isn&apos;t readable). Any
        folder of <code>.md</code> files works — it doesn&apos;t have to be Obsidian. Tuning knobs:{" "}
        <code>JARVIS_VAULT_SEARCH_MAX_RESULTS</code> (default 6) and{" "}
        <code>JARVIS_VAULT_READ_MAX_CHARS</code> (default 4000).
      </p>
      <p><strong>Reading is on as soon as the path is set.</strong> Try it by voice:
        <em> &ldquo;search my vault for the rabbit-farm note and read me the summary.&rdquo;</em>{" "}
        Tools: <code>search_vault(query)</code>, <code>read_vault_note(path)</code>.</p>

      <h2>2 · Enable WRITING to the vault</h2>
      <p>
        Writing is <strong>off by default</strong> on purpose: if your vault is a one-way sync target
        (e.g. a local mirror of a server-authoritative vault), local edits get clobbered. Turn it on
        only on the host that <em>owns</em> the vault:
      </p>
      <pre><code>{`JARVIS_VAULT_WRITABLE=true`}</code></pre>
      <p>
        Then <code>write_vault(path, text)</code> can save notes (path-scoped, no traversal). On the
        host that owns the vault this is safe; on a mirror, leave it false and let the authoritative
        host write.
      </p>

      <h2>3 · Learned facts &amp; journal (L1 / L2)</h2>
      <p>These are Watari&apos;s own memory, stored as Markdown under <code>memory/learned/</code> and
        <code> memory/journal/</code> (gitignored). They&apos;re on by default. Tools you can use by voice:</p>
      <ul>
        <li><code>remember(text, tags)</code> — &ldquo;remember that I keep rabbits at the farm.&rdquo; It also saves durable facts on its own.</li>
        <li><code>recall(query)</code> — &ldquo;what do you know about my farm?&rdquo;</li>
        <li><code>forget(query)</code> — drop a stored fact.</li>
        <li><code>read_journal()</code> — &ldquo;what did we do yesterday?&rdquo;</li>
      </ul>
      <p>
        The most recent learned facts are injected into the system prompt at startup (capped by{" "}
        <code>JARVIS_MEMORY_DIGEST_MAX</code>, default 12); <code>recall</code> reaches older ones. A
        background self-improvement pass quietly extracts durable facts after every few turns
        (<code>JARVIS_SELF_IMPROVE_ENABLED</code>).
      </p>

      <h2>4 · Recall by meaning (L5, optional)</h2>
      <pre><code>{`uv pip install sentence-transformers   # ~90 MB model downloads on first use`}</code></pre>
      <p>
        With it installed, <code>recall</code> matches on meaning (&ldquo;my bunnies&rdquo; → your
        rabbit-farm note), not just keywords. It&apos;s a graceful no-op until installed
        (<code>JARVIS_MEMORY_SEMANTIC_ENABLED=true</code> by default).
      </p>

      <h2>5 · Cache across restarts (L4, optional)</h2>
      <pre><code>{`JARVIS_REDIS_URL=redis://localhost:6379/0`}</code></pre>
      <p>
        Backs the hot cache with Redis so cached lookups survive a restart. Leave it blank and the
        cache falls back to in-process (no failure).
      </p>

      <div className="callout warn">
        <span className="k">Sync direction matters.</span> If your vault is mirrored from a server
        (the common 24/7 setup), treat the server as authoritative: write there, keep the local
        mirror read-only (<code>JARVIS_VAULT_WRITABLE=false</code>) so a sync never clobbers an edit.
      </div>

      <p style={{ marginTop: 22 }}>
        See also <Link href="/architecture#memory">Architecture → Memory</Link> for how the layers
        compose, and <Link href="/integrations">Integrations</Link> for every other tool.
      </p>
    </>
  );
}
