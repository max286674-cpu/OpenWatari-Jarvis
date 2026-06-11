# Jarvis — deployment checklist (everything only you can do)

This is the **complete** list of one-time setup steps to take Jarvis from "all code built & tested"
to "deployed and fully capable." The code is done and green
(`uv run python bench/run_all_tests.py` → **18 passed, 0 failed, 1 gated-skip**); these steps add the
credentials and physical enrolments that, by design, only *you* can provide.

**How to read this:** sections are grouped **Required** (Jarvis won't really function without them)
→ **Recommended** → **Optional**. Each capability **degrades gracefully** — anything you skip just
makes Jarvis say "that isn't configured yet" instead of crashing. **Do the Required block, then run
the tests; complete the rest as you want each capability.** A capability matrix at the very bottom
([§ Readiness matrix](#readiness-matrix)) maps every credential to what it unlocks.

> Convention: **PowerShell** blocks run on this laptop (`C:\Jarvis`), **bash** blocks run on the VPS.
> `# →` lines show what you should expect to see. All keys go in `.env` (copy from `.env.example`).

---

# REQUIRED — voice, brain, and memory (without these he can't really run)

## 0. The foundations (~15 min)

**Why:** these four give Jarvis a voice, a mind, ears, and his knowledge base. Everything else is
additive; this block is the floor.

**0a. `.env` exists.** `cp .env.example .env` (PowerShell: `Copy-Item .env.example .env`), then fill
in the keys below. Never commit it (it's git-ignored).

**0b. ElevenLabs — his voice (required).**
1. Get an API key at https://elevenlabs.io → Profile → API key. Pick/clone a voice and copy its
   **Voice ID** (Voice Lab → the voice → ID).
2. In `.env`:
   ```
   JARVIS_ELEVENLABS_API_KEY=...
   JARVIS_ELEVENLABS_VOICE_ID=...
   ```
*(Fully offline alternative: set `JARVIS_TTS_PROVIDER=piper` for a local CPU voice — lower quality,
no key.)*

**0c. Deepgram — his ears / speech-to-text (required for the default, accurate path).**
1. Key at https://deepgram.com → free tier is generous. In `.env`: `JARVIS_DEEPGRAM_API_KEY=...`
2. Deepgram can't do Armenian/Ukrainian. To understand **all six** of your languages offline, set
   `JARVIS_STT_PROVIDER=whisper` instead (local faster-whisper, no key, heavier on CPU).

**0d. The brain LLM — freellmapi (required).** Jarvis's reasoning runs through a free
OpenAI-compatible proxy (the `jarvis-freellmapi` service on `127.0.0.1:3001`).
1. Make sure that proxy is running/reachable (it's the same one the OpenClaw stack uses; start its
   Docker container or open the tunnel to the VPS).
2. In `.env`:
   ```
   JARVIS_FREELLMAPI_BASE_URL=http://127.0.0.1:3001/v1
   JARVIS_FREELLMAPI_API_KEY=<the unified key>
   ```
3. Verify: `uv run python bench/run_all_tests.py` — the "Phase 2: brain agent" row should PASS (not
   SKIP). If it SKIPs, the proxy isn't reachable.

**0e. Obsidian vault — his L3 memory (required; validated at startup).**
```
JARVIS_VAULT_PATH=C:\Users\iamva\Documents\Obsidian Vault
```
He reads/searches it; he warns loudly if it's missing.

**Verify the foundations:** `uv run python bench/check_config.py` (keys present) then
`uv run python bench/run_all_tests.py` (Phase 2 brain row PASS, not SKIP).

---

# The three physical / hands-on items

The three items in this section are physical — they need your voice, an SSH session, or the devices
in your hands. Do them in any order.

---

## 1. Enroll your voiceprint — *respond only to your voice* (~3 min)

**Why:** Phase 5 speaker biometrics is built but inert until it has a sample of *you*. Until you
enroll, Jarvis accepts every voice (so he never locks you out). After enrolling + flipping one flag,
he ignores the TV, a guest, anyone who isn't you.

**Prerequisite (already done by me):** the `identity` extra (`torch` + `speechbrain`) is installed.
If you ever rebuild the env, restore it with `uv sync --extra identity`.

**Steps**
```powershell
# 1. Be somewhere quiet, with the mic you normally use (laptop mic is fine).
uv run python bench/enroll_voice.py
```
What happens: it records **3 clips of 4 seconds** each, with a 3-2-1 countdown before each one.
It prints a prompt per clip:
```
# → [1/3] Say: 'Hey Jarvis, this is Vazghen.'
# →   ● recording 4s — speak now
# →   captured ✓
# → ... (clips 2 and 3: just talk normally, a sentence each)
# → Voiceprint saved to C:\Jarvis\voiceprint.json (192-dim, 3 clips).
```
Speak in your **normal** voice and volume — how you'll actually talk to him. It averages the 3 clips
into one 192-dimension fingerprint and writes `voiceprint.json`.

**Then turn it on** — edit `.env` (create it from `.env.example` if you haven't):
```
JARVIS_SPEAKER_ID_ENABLED=true
# optional, default 0.25 — higher = stricter (rejects more, incl. risk of rejecting you):
JARVIS_SPEAKER_THRESHOLD=0.25
```

**What to expect afterwards:** when the live assistant runs, each transcript is checked against your
print; non-matching speech is silently dropped *after* transcription (you'll see it logged, not
acted on). Yours passes through normally.

**Verify it took:** confirm `C:\Jarvis\voiceprint.json` exists and is ~a few KB of JSON. The real
proof is the live test (item 3): have someone else say "Hey Jarvis…" — he should ignore them.

**Troubleshooting**
- `ECAPA backend not available` → `uv sync --extra identity`, retry.
- `(clip too short / failed, retrying)` → speak sooner/louder; it needs audible speech in the 4s.
- Locked out / he ignores *you* → lower `JARVIS_SPEAKER_THRESHOLD` (e.g. 0.15), or just delete
  `voiceprint.json` / set `JARVIS_SPEAKER_ID_ENABLED=false` to disable instantly. You can re-enroll
  any time by re-running the script (it overwrites).

---

## 2. Deploy the VPS ticker — *recurring reminders fire even with the PC off* (~10 min)

**Why:** One-shot/`at` reminders already survive a powered-off PC (ntfy holds them server-side, no
VPS needed). The **one** case ntfy can't cover is a *repeating* schedule ("every day at 08:00") —
that needs an always-on process. This tiny daemon is it. It lives on the VPS you already have, owns
the daily jobs, and pushes them to the **same ntfy topic** your laptop uses. It's fully decoupled
from the OpenClaw fleet — it only knows ntfy + a local JSON file.

**Decide your ntfy topic first** (if you haven't already). Pick one unguessable string and use it in
**both** places. Example used below: `jarvis-vaz-619-7f3k9q2`. Put it in the laptop `.env`:
```
JARVIS_NTFY_TOPIC=jarvis-vaz-619-7f3k9q2
JARVIS_NTFY_SERVER=https://ntfy.sh
```
(Subscribe your phone to that topic in the ntfy app to actually receive pushes.)

**Step A — copy the deploy folder to the VPS** (from the laptop):
```powershell
scp -r C:\Jarvis\deploy\vps openclaw@100.107.141.83:~/jarvis-ticker-deploy
```

**Step B — SSH in and run the installer** (it makes a venv, writes an env file, installs+enables a
systemd service, prints a health check). I set `HOST=0.0.0.0` + a token so the laptop can reach it
over your Tailscale network (`100.107.141.83`):
```bash
ssh openclaw@100.107.141.83
cd ~/jarvis-ticker-deploy
JARVIS_NTFY_TOPIC=jarvis-vaz-619-7f3k9q2 \
JARVIS_TICKER_HOST=0.0.0.0 \
JARVIS_TICKER_TOKEN=pick-a-long-secret-here \
bash install.sh
# → --- health ---
# → {"ok":true,"jobs":0}
# → Deployed to /home/openclaw/jarvis-ticker. Point the edge at it with JARVIS_TICKER_URL=...
```

**Step C — point the laptop at it.** In the laptop `.env`:
```
JARVIS_TICKER_URL=http://100.107.141.83:8770
JARVIS_TICKER_TOKEN=pick-a-long-secret-here   # must match Step B exactly
```

**What to expect afterwards:** `set_reminder(daily="08:00", …)` on the PC now **also** POSTs the job
to the ticker, so it fires from the VPS even with the laptop off. `cancel_reminder` removes it from
both. If `JARVIS_TICKER_URL` is unset or unreachable, nothing breaks — the local scheduler still
speaks it when the PC is on (graceful degradation).

**Verify** (on the VPS):
```bash
curl -s http://127.0.0.1:8770/health                              # → {"ok":true,"jobs":N}
curl -s -XPOST http://127.0.0.1:8770/reminders -d '{"message":"ticker test","daily":"09:00"}'
curl -s http://127.0.0.1:8770/reminders                          # → lists it
journalctl -u jarvis-ticker -f                                   # watch it fire/push at 09:00
```
End-to-end check from the laptop: tell Jarvis "remind me every day at 9am to stretch," then power the
laptop *off* before 9am — the push should still land on your phone.

**Security note:** binding `0.0.0.0` exposes the port on your Tailscale interface; the
`JARVIS_TICKER_TOKEN` bearer guards it. If you'd rather not expose it at all, leave HOST at
`127.0.0.1` and instead open an SSH tunnel when needed
(`ssh -L 8770:127.0.0.1:8770 openclaw@100.107.141.83`) with `JARVIS_TICKER_URL=http://127.0.0.1:8770`.

> If you'd rather I run Step B for you: paste the go-ahead and I'll SSH in and execute it (I won't
> SSH on my own — standing rule).

---

## 3. Live device test — AirPods routing + real TTFW/VAQI numbers (~15 min)

**Why:** the routing logic, the brain server, and the phone client are all built and unit-tested, but
the *real* latency numbers and the auto-route behaviour can only be measured through a real mic with
the real devices. This is the acceptance test for Phases 1/5/6 together.

**Prerequisite:** make sure the full provider set is installed (one time):
```powershell
uv sync --extra edge --extra cloud-voice --extra local-voice --extra brain --extra channels --extra browse --extra identity --extra dev
```
And that `.env` has your `JARVIS_DEEPGRAM_API_KEY` + `JARVIS_ELEVENLABS_API_KEY` set (cloud STT/TTS
are the default quality path).

### 3a. Laptop + AirPods auto-route
```powershell
# Connect the AirPods Pro Max to the laptop via Windows Bluetooth FIRST, then:
uv run python -m jarvis.edge.assistant
```
- On startup it auto-picks the AirPods as output and logs something like
  `output: ... (auto-routed to headphones)`, and barge-in flips **on** (private endpoint).
- Say **"Hey Jarvis, what time is it?"** → it wakes, transcribes, answers in his voice.
- **Barge-in check:** start talking while he's mid-sentence — he should stop and listen.
- **TTFW reading:** each turn logs the latency, e.g.
  `TTFW 940 ms (mean 1010, n=3)`. That's user-stop → first spoken word. Target is **< ~1.2s** on this
  CPU. Do ~10 turns to get a stable mean (that 10-utterance battery is the VAQI basis).
- **Speaker-ID check** (if you did item 1): have someone else say "Hey Jarvis…" → ignored; you →
  served.
- Disconnect the AirPods mid-session and Jarvis should fall back to laptop speakers (barge-in off).

### 3b. iPhone client → same brain
```powershell
# In one terminal, run the brain server bound so the phone can reach it:
$env:JARVIS_BRAIN_HOST="0.0.0.0"; uv run python -m jarvis.brain.server
# → jarvis-brain listening on ws://0.0.0.0:8765/voice
# → phone client served at http://0.0.0.0:8766/iphone/
```
- Find the laptop's LAN IP: `ipconfig` → the IPv4 of your Wi-Fi adapter (e.g. `192.168.1.42`).
- On the **iPhone** (same Wi-Fi), open Safari → `http://192.168.1.42:8766/iphone/` → **Share → Add to
  Home Screen** for a full-screen app.
- It auto-connects (top dot turns green, "ready"). **Hold the mic** button and speak, or type in the
  box. His reply streams in and is spoken via the phone.
- **AirPods-on-phone test:** connect the AirPods to the *iPhone*, tick **"AirPods on this phone"** in
  the client's ⚙︎ panel, reconnect — the brain now treats the session as private headphones
  (barge-in on). This is the "route everything to my headphones when on either device" rule.
- **Same-brain proof:** ask something on the laptop ("remember the number 7"), then ask the phone
  ("what number did I say?") — same shared memory answers. (Both must point at the one brain; on the
  laptop that means running 3b's server and connecting the laptop edge to it too, or just compare
  within the phone session.)

**What "done" looks like:** TTFW consistently under ~1.2s, barge-in interrupts cleanly, AirPods
auto-route on both laptop and phone, a non-you voice is ignored (if enrolled), and the same question
works from phone and laptop. Jot the TTFW mean somewhere — that's your real Phase 5 benchmark number.

**Troubleshooting**
- Phone can't load the page → the laptop firewall is blocking 8766/8765. Allow Python through
  Windows Firewall (Private network), or run `New-NetFirewallRule -DisplayName "Jarvis" -Direction
  Inbound -Action Allow -Protocol TCP -LocalPort 8765,8766` in an elevated PowerShell.
- Phone connects but no voice → iOS Safari needs a tap before `speechSynthesis`/mic; press the mic
  once. If dictation is flaky on your iOS version, use the text box (always works).
- Wrong audio device on the laptop → set `JARVIS_AUDIO_OUTPUT_DEVICE=auto` (always prefer headphones)
  or a device-name fragment in `.env`.

---

# RECOMMENDED — channels & knowledge (what makes him useful day-to-day)

## A. Telegram — read *and* send your DMs (~10 min)

**Why:** lets Jarvis read your last messages in **any** chat (read or unread, *without* marking them
seen), mark chats read/unread, and send messages/GIFs/files. Reading needs a Telethon **user** login
(the Bot API can't read your DMs); sending can also use a bot token.

**Steps**
1. Get an **API id + hash** at https://my.telegram.org → API development tools. In `.env`:
   ```
   JARVIS_TELEGRAM_API_ID=...
   JARVIS_TELEGRAM_API_HASH=...
   JARVIS_TELEGRAM_PHONE=+...          # your number, intl format, for the one-time sign-in
   ```
2. One-time interactive login (creates the `jarvis.session` file, which is git-ignored):
   ```powershell
   uv run python bench/telegram_login.py     # enter the code Telegram sends you
   ```
3. (Optional, for bot-based sending) create a bot via @BotFather and set
   `JARVIS_TELEGRAM_BOT_TOKEN=...` and `JARVIS_TELEGRAM_DEFAULT_CHAT=<your chat id>`.

**Verify:** "Jarvis, read me my last messages with <name>" (reads without marking seen);
"mark that chat as read." Honest limit he'll tell you: once a sender has seen a read receipt,
Telegram can't reverse it — `seen`→`delivered` on their side is impossible.

## B. Web search & scrape (~5 min) — Tavily + Firecrawl

**Why:** `web_search` (fast answer + sources) and `scrape_url` (read one page) for anything live.
- **Tavily** — https://tavily.com → API key → `JARVIS_TAVILY_API_KEY=...`
- **Firecrawl** — https://firecrawl.dev → API key → `JARVIS_FIRECRAWL_API_KEY=...`

**Verify:** "what's the latest on <topic>" (web_search); "open <url> and read me the headline" (scrape).
*(The utilities belt — weather, crypto, stocks, FX, news, wiki, dictionary — needs **no keys** and
already works.)*

## C. Notion — read / write / comment (~5 min)

**Why:** Jarvis can search your Notion, read pages, append text, comment, and create sub-pages.
1. Create an **internal integration** at https://www.notion.so/my-integrations → copy its secret
   (`ntn_...`). In `.env`: `JARVIS_NOTION_TOKEN=...`
2. **Share each page/database** you want him to touch with the integration: open the page → ••• →
   **Connections** → add your integration. (Notion is deny-by-default — he sees only what you share.)

**Verify:** "search my Notion for the project page", then "read it to me", then "add a line to it"
(he'll confirm before writing).

## D. Change the protocol passwords (~2 min, security)

**Why:** the privileged routines ship with placeholder passwords. Set real ones before deployment:
```
JARVIS_PROTOCOL_GOODNIGHT_PASSWORD=...     # stop Jarvis
JARVIS_PROTOCOL_PHOENIX_PASSWORD=...       # restart Jarvis
JARVIS_PROTOCOL_RAGNAROK_PASSWORD=...       # restart the laptop
```
He never speaks or logs these; a wrong password runs nothing.

## E. ntfy phone push (~3 min)

**Why:** how reminders/alerts reach your phone when you're away from the mic (also used by the VPS
ticker in item 2).
1. Pick one unguessable topic string. In `.env`: `JARVIS_NTFY_TOPIC=jarvis-<something-unique>`
2. Install the **ntfy** app on your phone and subscribe to that exact topic.

**Verify:** "ping my phone with a test" (`send_push`) → it arrives.

---

# OPTIONAL — nice-to-haves

- **Browserbase** (cloud headless browser for `browse_web`): `JARVIS_BROWSERBASE_API_KEY` +
  `JARVIS_BROWSERBASE_PROJECT_ID`, then `uv sync --extra browse`. (The local visible `browser` tool
  already works without this.)
- **Spotify** playback control (Premium): make an app at developer.spotify.com, set
  `JARVIS_SPOTIFY_CLIENT_ID/_SECRET`, run `uv run python bench/spotify_login.py`. (Everyday music
  uses free YouTube Music — no setup.)
- **Extra wake words** beyond "jarvis" (alfred/robbin/assist/…): needs a Picovoice **Porcupine**
  AccessKey + `.ppn` files; set `JARVIS_WAKE_WORD_ENGINE=porcupine` + `JARVIS_PORCUPINE_ACCESS_KEY`.
  See `README.md` wake-word notes.

---

# Phases 9–12 — the code is built & green; these switch each capability ON

Everything below is **built and tested** (`uv run python bench/run_all_tests.py` → 16 passed). Each
integration **degrades gracefully** — Jarvis simply says "that isn't configured yet" until you do the
one-time setup. Do them in any order; none blocks the others.

## 4. Gmail + Google Calendar — one Google login (~15 min, one time)

**Why:** Phase 11 lets Jarvis read/draft/send your mail and read/create calendar events. You asked
to use Gmail "through an app" — this is exactly that: a real Google Cloud OAuth app you own. One
consent covers **both** Gmail and Calendar.

**Step A — make the Google app (in the browser):**
1. Go to https://console.cloud.google.com/ → create a project (any name, e.g. "Jarvis").
2. **APIs & Services → Library** → search and **Enable**: **Gmail API**, then **Google Calendar API**.
3. **APIs & Services → OAuth consent screen** → choose **External** → fill the app name + your email
   → on the **Test users** step, **add your own Gmail address** (so you can use it without app review).
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → type **Web application**.
   Under **Authorized redirect URIs** add exactly:
   ```
   http://127.0.0.1:8585/oauth2callback
   ```
   Create, then copy the **Client ID** and **Client secret**.

**Step B — put the client id/secret in `.env`:**
```
JARVIS_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
JARVIS_GOOGLE_CLIENT_SECRET=...
```

**Step C — run the one-time login (on the laptop):**
```powershell
uv run python bench/google_login.py
```
What happens: your browser opens Google's consent screen → you pick your account → "Continue" past
the "unverified app" notice (it's your own app) → grant Gmail + Calendar → the tab says "authorized".
Back in the terminal it prints:
```
# → SUCCESS — paste this line into your .env:
# → JARVIS_GOOGLE_REFRESH_TOKEN=1//0g...
```

**Step D — paste that line into `.env`.** Done.

**Verify:** ask Jarvis "read me my unread email" and "what's on my calendar today". To prove send is
gated, say "email Anna that I'll be late" — he should read the recipient + gist back and wait for your
yes before sending.

**Troubleshooting**
- "No refresh token returned" → you re-consented; the script forces `prompt=consent` so this is rare.
  If it happens, revoke the app at https://myaccount.google.com/permissions and re-run.
- "redirect_uri_mismatch" → the URI in the Google app must match `JARVIS_GOOGLE_OAUTH_REDIRECT`
  **character-for-character** (default `http://127.0.0.1:8585/oauth2callback`).
- "access_denied / app not verified" → make sure your address is added under **Test users**.

## 5. Home Assistant — smart home (~5 min, only if you run HA)

**Why:** Phase 11 lets Jarvis read device states and control lights/scenes/climate/locks. Local-first
and private — he talks straight to your HA box, nothing via the cloud.

**Steps**
1. In Home Assistant: click your **profile** (bottom-left) → **Security** → **Long-lived access
   tokens** → **Create token** → copy it (you only see it once).
2. In `.env`:
   ```
   JARVIS_HA_URL=http://homeassistant.local:8123     # or your HA IP, e.g. http://192.168.1.20:8123
   JARVIS_HA_TOKEN=<the long-lived token>
   ```

**Verify:** "Jarvis, is the front door locked?" (`ha_state`), then "turn on the living room lights"
(`ha_call`). For a lock he'll confirm before acting. Find an entity's id in HA under
**Settings → Devices & Services → Entities** (e.g. `lock.front_door`, `light.living_room`).

**Troubleshooting**
- Nothing happens / 401 → token wrong or expired; recreate it.
- Can't reach it → use the numeric IP rather than `homeassistant.local`, and make sure the laptop is
  on the same network.

## 6. (Optional) Redis — make the cache survive restarts (~5 min)

**Why:** the L4 hot-cache (Phase 9b) already works in-process (repeat lookups are instant within a
run). Redis extends that across **brain restarts** — worth it once the brain runs 24/7, skippable
before then. Without it, nothing breaks; you just don't keep a warm cache across restarts.

**Steps** — run Redis (Docker is easiest), then point Jarvis at it:
```powershell
docker run -d --name jarvis-redis -p 6379:6379 redis:7-alpine
```
```
# .env
JARVIS_REDIS_URL=redis://127.0.0.1:6379/0
```
**Verify:** ask the same web/utility question twice across two separate runs — the second is instant,
and the logs show `L4 cache: connected to Redis`. (If Redis is down, Jarvis logs once and falls back
to the in-process cache — no failure.)

## 7. (Optional) Semantic memory — recall by meaning (~5 min, ~90 MB)

**Why:** Phase 9c lets recall match on *meaning* ("my bunnies" → your rabbit-farm note), not just
keywords. It's a no-op until you install a local embedder; recall stays keyword-only otherwise.

**Steps**
```powershell
uv pip install sentence-transformers
```
That's it — `JARVIS_MEMORY_SEMANTIC_ENABLED` is already `true`. First use downloads a small CPU model
(~90 MB) once. **Verify:** tell Jarvis "remember I keep rabbits at the farm", then later ask "what do
you know about my bunnies?" — he should surface it despite the different word.

## 8. (Optional) Turn on the proactive companion

**Why:** Phase 10 lets Jarvis *start* conversations — reminders surfacing, "you've got a standup in
10", anti-distraction nudges — within a daily budget and quiet hours so he's never noisy. It's **off
by default** because it speaks unprompted.

**Steps** — in `.env`:
```
JARVIS_PROACTIVE_ENABLED=true
JARVIS_PROACTIVE_QUIET_HOURS=23:00-07:00     # tune to your sleep
JARVIS_PROACTIVE_DAILY_BUDGET=6              # how many unprompted nudges/day, max
JARVIS_HOME_LOCATION=Yerevan                 # for weather + the morning briefing
```
It gets much more useful **after** step 4 (calendar = the richest signal). Control it live by voice:
"focus mode for an hour" (holds nudges), "lockdown" (go quiet), "normal" (resume), or ask "give me my
briefing" any time. **Verify:** with it on, leave the brain running — within a tick (5 min) of a
real signal (e.g. an imminent calendar event) he'll speak up, or push to your phone if you're away.

## 9. Phase 13 — GitHub repo + token, so Jarvis can self-improve (push) (~10 min)

**Why:** Jarvis can already read/edit his own code, run the suite, and make **reversible local
commits** (no setup needed — he has no power to reset/force-push/rewrite history; a revert is always
a new commit). To let him **push** those commits to a remote backup/repo, you give him a GitHub repo
and a scoped token. He commits to GitHub; you can roll back anything from history.

**A baseline commit already exists** — I committed the full Phase 0–13 codebase locally as the
starting point, with a hardened `.gitignore` that keeps `.env`, sessions, `voiceprint.json`,
`audit/`, `backups/` and his private memory **out** of git. Verify: `git log --oneline -1`.

**Step A — create the repo (in the browser):**
1. https://github.com/new → name it e.g. `jarvis` → **Private** (it contains personal context) →
   **don't** add a README/.gitignore (the repo already has history) → Create.

**Step B — create a fine-grained Personal Access Token:**
1. https://github.com/settings/tokens?type=beta → **Generate new token**.
2. **Resource owner** = you; **Repository access** → **Only select repositories** → pick `jarvis`.
3. **Permissions → Repository → Contents → Read and write** (that's all he needs to push). Generate,
   copy the token (starts `github_pat_…`).

**Step C — wire the remote (on the laptop, one time):**
```powershell
git -C C:\Jarvis remote add origin https://<PASTE_TOKEN>@github.com/<your-username>/jarvis.git
git -C C:\Jarvis push -u origin master
```
(Embedding the token in the remote URL is the simplest PAT push; it lives in `.git/config`, which is
never itself committed. Prefer SSH? `git remote add origin git@github.com:<you>/jarvis.git` after
adding an SSH key.)

**Step D (optional) — tell Jarvis about it** in `.env`, so his guidance is accurate:
```
JARVIS_GITHUB_REPO=<your-username>/jarvis
JARVIS_GITHUB_TOKEN=github_pat_...        # only if you want token-aware automation; push works via the remote alone
```

**What you can now do:** "Jarvis, read your self-improvement skill, then make recall faster." He'll
branch, edit, **run the tests**, read back the change, wait for your **yes**, commit, and — if you
ask — push. If a change is wrong: "revert your last commit." Everything stays recoverable.

**Verify:** ask him "what's your git status" (`git_status`), then "show me your last commits"
(`git_log`). For the full loop, ask him to make a trivial doc tweak, run tests, and commit — then
check `git log` shows a commit trailed "Made by Jarvis (self-improvement)".

**Safety recap:** he is confined to the repo (can't touch files outside it or read `.env`/secrets),
he can only add to history (no destructive git), and writes/commits/pushes are all confirm-first.

## 10. Production switch-on — what's now ON by default vs. needs you

When you move from testing to 24/7, **all capabilities are wired and enabled** except two that
genuinely need *you*:
- **Proactive companion** — now **ON by default** (`JARVIS_PROACTIVE_ENABLED=true`), respecting the
  daily budget + quiet hours. Set it `false` for a quiet test session. Set `JARVIS_HOME_LOCATION`
  for weather/briefings. It gets much smarter after the Google login (item 4 — calendar signals).
- **Speaker biometrics** — wired but inert until you **enroll your voice** (item 1). Until then he
  answers anyone; that's deliberate so he never locks *you* out.
- **Fleet consult** — left **off** on purpose (`JARVIS_FLEET_AUTHORIZED=false`): it reaches shared
  VPS infra, so it's a deliberate opt-in. Flip it `true` in `.env` when you want him to consult the
  team 24/7 without asking each time.

Nothing else is "configured but unwired" — every tool in `memory/tools.md` is registered and live;
the credential-gated ones (Gmail, Home Assistant, Spotify, Telegram, Tavily/Firecrawl, GitHub push)
simply say "not configured yet" until you complete their one-time setup above.

---

## Readiness matrix

Every capability, what it needs, and where its setup lives. Complete the **Required** rows + a green
`uv run python bench/run_all_tests.py`, and Jarvis runs; add the rest to unlock each capability.

| Capability | Needs | Tier | Step |
|---|---|---|---|
| **His voice (TTS)** | ElevenLabs key + voice id (or local Piper) | Required | §0b |
| **Speech-to-text** | Deepgram key (or local Whisper) | Required | §0c |
| **His brain (reasoning)** | freellmapi proxy reachable + key | Required | §0d |
| **L3 vault memory** | `JARVIS_VAULT_PATH` | Required | §0e |
| Responds only to your voice | enrol voiceprint + flag | Recommended | §1 |
| Recurring reminders, PC off | VPS ticker deploy | Recommended | §2 |
| Real latency / device test | AirPods + phone, live run | Recommended | §3 |
| Read/send Telegram DMs | Telethon login (+ bot token) | Recommended | §A |
| Web search & scrape | Tavily + Firecrawl keys | Recommended | §B |
| Notion read/write/comment | Notion integration + shared pages | Recommended | §C |
| Protocol passwords | set 3 passwords | Recommended (security) | §D |
| Phone push (ntfy) | ntfy topic + app subscribe | Recommended | §E |
| Gmail + Calendar | Google OAuth app + login | Recommended | §4 |
| Home Assistant | HA URL + long-lived token | Optional (if you run HA) | §5 |
| Cache across restarts | Redis | Optional | §6 |
| Recall by meaning | `sentence-transformers` | Optional | §7 |
| Proactive companion | on by default; set home location | On by default | §8 |
| Self-improvement push | GitHub repo + PAT + remote | Recommended | §9 |
| Cloud browser | Browserbase keys | Optional | §Optional |
| Spotify control | Spotify OAuth (Premium) | Optional | §Optional |
| Extra wake words | Porcupine access key + .ppn | Optional | §Optional |
| Utilities (weather/crypto/news/…) | **nothing — works now** | — | — |
| Local music (YouTube Music) | **nothing — works now** | — | — |
| Fleet consult | `JARVIS_FLEET_AUTHORIZED=true` | Optional | §10 |

**"Ready for deployment" =** the four Required rows done + Telegram/web/Notion/push as you want them
+ protocol passwords changed + `uv run python bench/run_all_tests.py` all green. Then run the brain
as a service (and the edge on your laptop) per [README → Deployment](README.md#deployment).

---

### Still parked (correctly, not actionable yet)
- **Mentra OS glasses** — not purchased. When you have them: `cd glasses && npm install`, register
  the app in the MentraOS console, and wire the SDK's transcription stream to `sendUtterance()`. The
  brain link + device routing are already done; only those SDK calls are stubbed.
- **Key hygiene (optional):** the Tavily/Firecrawl/Browserbase keys came through chat in plaintext —
  rotating them is good hygiene, not urgent.
