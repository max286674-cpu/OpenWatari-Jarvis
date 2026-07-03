# OpenWatari / Watari — Development TODO

Complete end-to-end review of every subsystem. For each: **status**, real **bugs/issues**, and a
**dev plan** (even where there are no bugs — how to make it faster, cleaner, or more JARVIS-like).

**Objectives** every item is scored against:
**O1** efficiency · **O2** speed of execution · **O3** clean code + sound top-to-bottom architecture · **O4** closer to J.A.R.V.I.S. (proactive, anticipatory, intelligent, always-there).

Priority: **P0** = blocks "production-grade complete assistant" · **P1** = clear win · **P2** = polish.

---

## Done (context, not TODO)
Edge deafness watchdog · whisper small→base (4s→1.4s) · groq textual-toolcall recovery · L5 honest-off · proactive calendar source · dead `aec_enabled` + 10 dead config flags removed · daily memory backup · gated `deploy_vps.sh` · `dump_tools.py` · Composio fan-out search (all 17 connected apps reachable) · **ispir reachable + brain auto-delegates** (CLI path fixed, fleet armed, verified). VPS disk 89%→79%.

**2026-06-30 implementation pass (verified live):**
- ✅ **24/7 auto-start audited:** edge + pc_agent run on logon triggers (correct — edge needs the audio session); brain `Restart=always` + `Linger=yes`. Edge crash-restart **3→999** in `install_edge_service.ps1` (live task needs ONE elevated re-register — see below).
- ✅ **pc_agent keepalive live** (`ping_timeout=75`, task restarted).
- ✅ **Composio toolkit-hint:** keyword→connected-toolkit scopes the search (1 call, precise) — "send an email"→gmail in 0.57s.
- ✅ **LLM primary benchmarked** (groq-70b/8b/cerebras/gemini on native tool-calling) → **kept groq+recovery** (swap was a lateral move with new rate-limit risk; data-driven decision).
- ✅ **End-to-end reachability verified live:** brain `/healthz` ok · edge connected · pc_agent connected · **WS round-trip edge→brain→tool→reply 1.10s** ("what time is it" → real answer) · suite **51/0**.

> ⚠️ **One elevated step for you:** the live `JarvisEdge` task still shows RestartCount=3 (modifying it needs admin). Run as admin, or via `!`: `powershell -File scripts\install_edge_service.ps1` to re-register with 999.

---

## 2026-07-02 — Two-track plan (assistant + framework)

Deltas since the audit below: **cloud voice pivot** (Deepgram nova-3 streaming STT + ElevenLabs flash TTS)
**closed Edge P0 "STT blocking floor"** and the proper-noun item (nova-3 handles them); **custom wake
words trained** (`watari`/`hey_watari` openWakeWord, no API key) closing Edge P2; Composio toolkit-hint
+ LLM-primary benchmark landed 2026-06-30. Remaining work, in execution order:

**Track A — our assistant (Watari)**
- **A1 · Mic pin-by-NAME** (index pins go stale on BT reconnect → live `-9998` crash). *(in progress)*
- **A2 · Proactive depth**: MyNews morning-brief source added (`tools/mynews.py`, VPS-local
  `JARVIS_MYNEWS_URL=http://127.0.0.1:3000` — untruncated titles, no Vercel hop). Audit correction:
  notion `task_signals` + gmail `email_signals` were ALREADY wired, so 5 sources now tick.
  Task-deadline from the brain's own store: N/A (tasks.py tracks background work, no due dates —
  Notion covers todos). Routine-pattern: deferred — needs weeks of behavior history that no store
  collects yet; revisit when L2 journal is dense enough to mine.
- **A3 · Latency regression guard**: assert TTFW/STT budgets in the suite.
- **A4 · Glasses stub**: park honestly (README, no implied capability) until a MentraOS account exists.
- Needs-user: rotate Krisp+Cerebras keys · re-enroll speaker-ID voiceprint · elevated JarvisEdge re-register (RestartCount 999).

**Track B — OpenWatari framework (other people's setups)**
- **B1 · Wizard live key validation** + idempotent re-run (wrong key today = silent runtime failure).
- **B2 · Docs generated from code**: `dump_tools.py` → tool-reference page + architecture page.
- **B3 · Docs site top-tier UI/UX pass** (every subsystem described).
- **B4 · CI gate**: hermetic/live test split + pre-push hook.
- **B5 · Prune inert .env vars** from `.env.example` + wizard (config must reflect reality).

Each item is verified in production before the next starts.

**2026-07-03 round C (all verified):** wizard = WATARI banner + 8-step flow + live probes + run/deploy
finale (34/34 checks) · speakers barge-in via wake word over TTS (no AEC dep; threshold+0.15) ·
L5 semantic LIVE on VPS via Jina embeddings API (no torch; flag on) · backup RESTORE path +
hermetic drill (there was no restore at all before) · fleet routing memory (prefs counters →
system-prompt bias) + **bug fixed: no-gateway-token setups never reached the CLI path** ·
pc_agent catastrophic-op refuse-list · weekly live-integration timer on VPS (Mon 07:30 UTC,
Telegram alert on fail — first run already caught Browserbase unconfigured on VPS).
**Decisions:** WS gateway path KEPT (documented auth research; clean fallback; framework users can
allowlist a client id) · GitHub stays local-git-only by design (Composio `github` toolkit covers
API needs) · groq primary re-benchmark waits for new models · docs mobile nav stays a stack.

---

## 1. Brain — `src/jarvis/brain/`
Status: **strong core, proven live** (agent loop, LLM routing, L1–L4 memory, scheduler, self-improve, telegram all running with real output).

- **P0 · LLM primary is a poor tool-caller (O2).** `groq:llama-3.3-70b` throws `BadRequestError` (malformed tool calls) on most tool turns → recovery saves it but it's the *hot path*, not a fallback. Plan: benchmark `groq:llama-3.1-70b`/`cerebras:gpt-oss-120b`/`gemini` as primary on tool-call fidelity + latency; pick the one that emits native calls. Recovery becomes the net.
- **P1 · Groq free-tier rate-limits (O2).** Bursty use → both groq models cool down together → gemini carries. Plan: add a paid groq key OR a local `ollama:` model as a always-available floor so no turn ever waits on a cold cloud failover.
- **P1 · L5 semantic dark (O1/O4).** Off because torch is ~1GB on an 89%→79% disk. Plan: either commit (free disk, `uv pip install sentence-transformers`, flip flag) OR swap to an API embedder (gemini embeddings, no torch) so meaning-based recall works without the weight.
- **P2 · `agent.py` is ~1000 lines (O3).** Cohesive, not urgent. Leave until a second reason to touch it.
- **P2 · Single-VPS SPOF (O1).** No brain failover/monitoring beyond `/healthz`. Plan: external uptime ping → Telegram alert (cheap) before considering a hot standby (overkill for personal use).

## 2. Edge — `src/jarvis/edge/`
Status: **working**, pipeline order correct, watchdog added.

- **P0 · STT is a 1.4s *blocking* floor (O2/O4) — the #1 perceived-latency item.** Whisper `base` transcribes only after you stop talking. Plan: real streaming STT (Moonshine ONNX or faster-whisper streaming) so transcription overlaps speech → sub-500ms to text. `moonshine` provider is currently just an alias to whisper — implement it for real.
- **P1 · No barge-in on speakers (O4).** Half-duplex = can't interrupt Watari mid-sentence; very un-JARVIS. Plan: webrtc/Krisp AEC for full-duplex on open speakers (already works on headphones/glasses).
- **P1 · Proper-noun STT accuracy (O4).** "Yerevan"→"your event" on every whisper size. Plan: a small biasing/hotword list (names, places, contacts) post-correction pass, or a larger model only when the wake word fired.
- **P2 · Wake word is "hey jarvis" pretrained only (O4).** Custom "hey watari" needs Porcupine/training (`bench/train_wake_word.py` exists). Tune threshold for false-fire vs miss.

## 3. PC Agent — `src/jarvis/edge/pc_agent.py`
Status: **working**, connected; keepalive fixed this session.

- **P2 · Elevated, fully trusts the brain (O3).** Ops inherit `system.py` path/secret guards (so not unguarded), but a tiny on-agent refuse-list for catastrophic ops (format, whole-drive delete) is cheap defense-in-depth for a privileged process. Skipped earlier as redundant — revisit only if the agent ever runs commands from a less-trusted source.
- **P2 · No cross-platform parity check (O3).** Built for Windows; macOS/Linux PC-control untested.

## 4. Tools — `src/jarvis/brain/tools/` (80 tools)
Status: **all registered + advertised; credential-gated, mostly green.** Composio fan-out fixed.

- **P1 · Composio search relevance is brittle (O4).** Fan-out guarantees the right tool is in the candidate list, but Composio buries `SEND_EMAIL` under `LIST_DRAFTS`. Plan: a tiny verb→toolkit hint map (email→gmail, message→slack…) so the LLM passes `toolkit=` and skips the noisy global search; cheap, big precision win.
- **P1 · GitHub/Notion-write/etc. via local git only (O4).** The removed `github_token` flag revealed Watari's coding tools never call the GitHub API. Plan: decide — wire a real GitHub tool (PRs/issues via API or Composio `github` toolkit, already connected) OR keep local-git-only and stop implying otherwise.
- **P2 · Home Assistant + Giphy unconfigured.** Fine if you don't use them; wire creds when you do.
- **P2 · Overlapping verbs cleaned but watch drift (O3).** `open_url`/`browser`/`browse_web`/composio now disambiguated by description — keep them distinct as tools grow.

## 5. Protocols — `src/jarvis/protocols/`
Status: named one-shots; **backup now scheduled daily** this session.

- **P2 · No tests on phoenix/ragnarok (O3).** Recovery protocols that have never been drilled are a gamble. Plan: one hermetic restore drill in `bench/`.
- **P2 · Possible overlap (O3).** Audit `phoenix` vs `checkpoint` vs `backup`; merge if two do one job.

## 6. Config — `src/jarvis/config.py`
Status: **cleaned** (10 dead flags removed, 163 fields).

- **P2 · 163 flat fields (O3).** Pydantic validates, but it's a wall. Plan: only if it keeps growing — group into nested models (voice/llm/memory/integrations). Not worth churn yet.
- **P1 · Inert `.env` values mislead (O3).** GITHUB_TOKEN/ELEVENLABS_STREAMING/OPENCLAW_REMOTE_TOKEN are set but unread. Plan: prune them from the live `.env` files + the wizard so config reflects reality.

## 7. Setup wizard — `src/jarvis/setup_wizard.py`
Status: 326-line interactive first-run; functional.

- **P1 · No live key validation (O3/O4).** Wrong key → silent failure at runtime. Plan: ping each provider as entered (`/healthz`-style probe) and make the wizard re-runnable/idempotent so a partial setup resumes.

## 8. Personality — `personality/jarvis.md`
Status: tight, templated, good.

- **P2 · Proactive promise now backed (O4).** Calendar source landed; keep the "initiate at sensible moments" line honest as more signal sources land. No code change needed.

## 9. Clients — `clients/iphone/`, `glasses/`
- **P0 · Glasses client is an unfinished SCAFFOLD (O4).** `glasses/src/index.ts` has TODO MentraOS SDK calls — it can't run. Plan: finish the SDK calls (needs a MentraOS account + `npm i`) OR delete the stub until you have them. A half-client is worse than none.
- **P2 · iPhone client is a single 258-line HTML (O3).** Works; no offline/error states. Polish later.

## 10. Docs site — `website/`
Status: Next.js on Vercel.

- **P1 · Docs drift from code (O3).** `bench/dump_tools.py` now emits the tool list; wire it into the build so the 80-tool page regenerates. Add the architecture/component table (from the earlier inventory) as a generated page.

## 11. Bench / tests — `bench/`
Status: 51 green; deploy now gated.

- **P1 · No CI (O3).** `deploy_vps.sh` gates VPS deploys, but nothing gates commits. Plan: a pre-push hook (or GitHub Action if/when pushed) running the suite.
- **P2 · Live-integration tests need creds → skipped in CI (O3).** Split fast/hermetic from live so the gate is fast.
- **P2 · No latency regression guard (O2).** `benchmarks.py` exists but isn't asserted. Plan: assert TTFW/STT budgets so a regression fails the suite.

## 12. Fleet / ispir delegation — `src/jarvis/brain/fleet.py`
Status: **FIXED + verified this session.** CLI path set, fleet armed, brain auto-delegates ("Online." via ispir).

- **P1 · Reachability depends on one absolute `.env` path (O3).** `JARVIS_OPENCLAW_CLI_PATH` hard-set to the binary. Plan: have `_delegate_via_cli` `shutil.which("openclaw")` then fall back to `~/.npm-global/bin/openclaw` so it self-heals for other installs (OpenWatari users).
- **P1 · WS gateway path is dead (O3).** Control-UI auth is blocked ("requires device identity"). The CLI fallback is now the ONLY path. Plan: either drop the WS code (dead) or get a proper gateway client token so the WS path (faster, streaming) works again.
- **P2 · Delegation latency (O2).** CLI spawn ~25s for ispir's deep work. Fine for "deep work," but surface a spoken "working on it with the team, sir" ack (already have progress acks — confirm it fires for delegation).
- **P2 · No routing memory (O4).** Brain decides per-turn. Plan: learn which domains always go to ispir (finance/IS24/research) and pre-bias.

---

## Cross-cutting — for a "complete JARVIS"
- **P0 · Proactive depth (O4) — the soul of JARVIS.** Only health + calendar sources wired. Add: task-deadline, email-urgency, routine-pattern ("you usually X now"), weather/commute, news-of-interest signal sources. This is the single biggest gap between "voice tool" and "JARVIS."
- **P1 · Speaker-ID off (O4).** Voiceprint unenrolled (scored -0.13). Re-enroll so Watari answers only you and greets by voice.
- **P1 · Secrets hygiene (O3).** Real GitHub PAT + tokens sit in `.env`; Cerebras key arrived via chat (rotate). Plan: move to a secret store or at least rotate + document the never-commit set.
- **P2 · Observability (O1/O2).** No live latency/health dashboard. Plan: ship per-turn metrics (already measured) to a tiny log/endpoint.
- **P2 · Vision (O4).** JARVIS sees. No camera input. Big scope — park unless wanted.

---

## Suggested order
1. **P0 speed/feel:** streaming STT (#2) · proactive depth (cross-cutting) · LLM primary tool-caller (#1).
2. **P0 completeness:** glasses finish-or-delete (#9).
3. **P1 wins:** Composio toolkit-hint (#4) · barge-in/AEC (#2) · re-enroll speaker-ID · CLI self-heal + WS-or-drop (#12) · wizard validation (#7) · docs from code (#10) · CI gate (#11) · secrets hygiene.
4. **P2:** the polish above.
