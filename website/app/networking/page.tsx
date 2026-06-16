import Link from "next/link";

export default function Networking() {
  return (
    <>
      <h1>Networking — the Tailnet requirement</h1>
      <p className="lead">
        OpenWatari is multi-device. The secure way to connect your phone, laptop, and glasses to the
        same 24/7 brain on a VPS is a private mesh VPN — a <strong>Tailnet</strong>.
      </p>

      <div className="callout warn">
        <span className="k">Rule of thumb.</span> If a device should talk to Watari, it must be{" "}
        <strong>on your Tailnet and logged in</strong>. Off the tailnet, only the public fallbacks work
        (Telegram bot messages, ntfy push).
      </div>

      <h2>Why a Tailnet</h2>
      <p>
        The brain binds <code>0.0.0.0</code> so devices can reach it — but you must never expose that
        on the public internet. A Tailnet (
        <a href="https://tailscale.com" target="_blank" rel="noreferrer">Tailscale</a>, WireGuard under
        the hood) gives every one of <em>your</em> devices a stable private <code>100.x.y.z</code>{" "}
        address that is unroutable to anyone else. The brain is still additionally guarded by the{" "}
        <code>JARVIS_API_AUTH_TOKEN</code> bearer the wizard generates — defence in depth.
      </p>

      <h2>Install Tailscale on every device</h2>
      <p>Sign in to the same Tailscale account everywhere:</p>
      <table>
        <thead>
          <tr><th>Device</th><th>How</th></tr>
        </thead>
        <tbody>
          <tr><td>VPS / brain host (Linux)</td><td><code>curl -fsSL https://tailscale.com/install.sh | sh</code> then <code>sudo tailscale up</code></td></tr>
          <tr><td>Laptop (Windows/Linux)</td><td>install the Tailscale app, sign in</td></tr>
          <tr><td>Mac (macOS)</td><td>Tailscale from the Mac App Store (or <code>brew install --cask tailscale</code>), sign in</td></tr>
          <tr><td>iPhone</td><td>Tailscale from the App Store, sign in (keep it connected)</td></tr>
          <tr><td>Android</td><td>Tailscale from Google Play, sign in (keep it connected)</td></tr>
          <tr><td>Mentra OS glasses</td><td>via their companion phone, which is on the tailnet</td></tr>
          <tr><td>Home Assistant</td><td>the brain reaches HA over the tailnet (or your LAN)</td></tr>
        </tbody>
      </table>
      <p>
        Find your brain host&apos;s tailnet IP with <code>tailscale ip -4</code> on the VPS (e.g.{" "}
        <code>100.107.141.83</code>).
      </p>

      <h2>How each connection uses it</h2>
      <table>
        <thead>
          <tr><th>Path</th><th>Endpoint</th></tr>
        </thead>
        <tbody>
          <tr><td>Laptop / glasses edge → brain</td><td><code>ws://&lt;brain-tailnet-ip&gt;:8765/voice</code></td></tr>
          <tr><td>iPhone Siri Shortcut → brain</td><td><code>http://&lt;brain-tailnet-ip&gt;:8766/talk?token=…</code></td></tr>
          <tr><td>Remote PC-control executor → brain</td><td><code>ws://&lt;brain-tailnet-ip&gt;:8765/control</code></td></tr>
          <tr><td>Recurring-reminder ticker</td><td><code>http://&lt;brain-tailnet-ip&gt;:8770</code></td></tr>
        </tbody>
      </table>
      <p>
        No port-forwarding, no public exposure, no dynamic-DNS. Set these in <code>.env</code> (the
        wizard&apos;s <em>vps</em> deployment shape fills <code>JARVIS_BRAIN_HOST=0.0.0.0</code>,
        generates the token, and builds the edge URL from the host you give it). See{" "}
        <Link href="/configuration">Configuration</Link>.
      </p>

      <h2>Firewall</h2>
      <p>
        On a multi-device LAN test (no tailnet) you&apos;d open ports 8765/8766 in the OS firewall; over
        a tailnet you generally don&apos;t need to, since traffic arrives on the Tailscale interface.
        Keep the public internet closed to these ports regardless.
      </p>
    </>
  );
}
