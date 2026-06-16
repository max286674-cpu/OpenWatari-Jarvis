export default function License() {
  return (
    <>
      <h1>License &amp; attribution</h1>
      <p className="lead">
        OpenWatari is released under the <strong>MIT License</strong> — free to use, modify, and
        redistribute, including commercially.
      </p>

      <h2>Do you need to “acquire” a license?</h2>
      <p>
        No. MIT is a public template, not something you buy or register. To adopt it you keep the{" "}
        <code>LICENSE</code> file (with its copyright line) in copies of the code. That&apos;s the whole
        obligation for your own code.
      </p>

      <h2>Dependencies keep their own licenses</h2>
      <p>
        Almost all are permissive (MIT / BSD / Apache-2.0 / Unlicense) and ask only that you retain
        their notices — that&apos;s what <code>THIRD_PARTY_NOTICES.md</code> is for. The{" "}
        <strong>one</strong> copyleft dependency is <code>py-tgcalls</code> / <code>ntgcalls</code>{" "}
        (<strong>LGPL-3.0</strong>), pulled in only by the optional <code>channels</code> extra for
        streaming music into a Telegram voice chat. Using it as an unmodified <code>pip</code> library
        is compatible with shipping your own MIT code; omit it for a 100%-permissive stack (Telegram
        text still works via MIT-licensed Telethon).
      </p>

      <h2>Cloud services are Terms of Service, not licenses</h2>
      <p>
        ElevenLabs, Deepgram, your OpenAI-compatible LLM provider, Tavily, Google, Notion, Home
        Assistant, GitHub, ntfy — these are bring-your-own-key services governed by their own Terms,
        which you accept when you sign up. The framework ships no keys.
      </p>

      <h2>Naming &amp; trademark</h2>
      <p>
        The project is <strong>OpenWatari</strong> and the assistant is <strong>Watari</strong> — names
        chosen so the public brand doesn&apos;t rely on a franchise-associated mark. <em>Jarvis</em> is
        referenced only as the blueprint/inspiration and is not used as the project&apos;s brand; the
        internal package keeps the code identifier <code>jarvis</code>. MIT grants copyright, not
        trademark — if you fork under a different public name, make it your own.
      </p>

      <div className="callout">
        Before a public release, run <code>uvx pip-licenses --format=markdown</code> over your locked
        environment as a final check.
      </div>
    </>
  );
}
