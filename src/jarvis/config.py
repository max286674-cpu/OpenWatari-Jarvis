"""Central configuration for Jarvis (edge + brain).

All secrets and provider choices come from environment / a local `.env` file.
Nothing here is hard-coded so the same codebase runs CPU-local-only or cloud-quality
just by flipping provider flags. See `.env.example` for the full surface.
"""

from __future__ import annotations

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class STTProvider(str, Enum):
    deepgram = "deepgram"      # cloud, streaming, best accuracy (default for "understands me well")
    whisper = "whisper"        # local faster-whisper int8 (offline fallback)
    moonshine = "moonshine"    # local, CPU-fast (lowest-latency offline)


class TTSProvider(str, Enum):
    elevenlabs = "elevenlabs"  # cloud, streaming — the chosen "Jarvis voice" (default)
    piper = "piper"            # local, fastest on CPU (offline fallback)
    kokoro = "kokoro"          # local, higher quality than Piper, still CPU-runnable


class LLMBackend(str, Enum):
    """The model that powers Jarvis's OWN brain / reasoning.

    OpenClaw is deliberately NOT in this enum: it is an external team Jarvis can
    consult, not the engine of his mind. Jarvis always thinks and speaks as himself.
    """

    freellmapi = "freellmapi"  # default — free OpenAI-compatible proxy (on the VPS)
    ollama = "ollama"          # fully-offline local model
    openai = "openai"          # any OpenAI-compatible endpoint


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="JARVIS_"
    )

    # --- Provider selection (the three knobs that define a deployment) -------------------
    # Whisper (local faster-whisper) by default: understands ALL six of Vazghen's languages
    # (English/French/German/Armenian/Russian/Ukrainian) via auto-detect, free + offline. Deepgram
    # is faster but can't do Armenian/Ukrainian — switch with JARVIS_STT_PROVIDER=deepgram.
    stt_provider: STTProvider = STTProvider.whisper
    tts_provider: TTSProvider = TTSProvider.elevenlabs
    llm_backend: LLMBackend = LLMBackend.freellmapi   # Jarvis's OWN reasoning model

    # --- Wake word ----------------------------------------------------------------------
    wake_word_enabled: bool = True
    wake_word_engine: str = "openwakeword"   # openwakeword (now) | porcupine (custom phrases)
    # Vazghen's required wake set. Only phrases with a pretrained openWakeWord model load today
    # (currently just "jarvis"); the rest are pending the Porcupine path (see README).
    wake_words: str = "jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine"
    wake_word_threshold: float = 0.5
    wake_listen_window_s: float = 8.0     # how long the mic stays open after a wake/reply
    porcupine_access_key: str | None = None  # Picovoice key, for the custom-phrase engine
    half_duplex: bool = True              # mute mic while Jarvis speaks (no self-hearing);
    #                                       set false only with AEC (Krisp) or headphones

    # --- VAD & barge-in (Phase 1) -------------------------------------------------------
    # Silero VAD (CPU, bundled) detects speech start/stop. Barge-in lets you interrupt
    # Jarvis mid-sentence by speaking. Barge-in requires the mic NOT to hear Jarvis's own
    # voice, so it only works on HEADPHONES (or with AEC) — never enable it with half_duplex
    # on open speakers, or Jarvis's own playback interrupts himself. See README audio notes.
    vad_enabled: bool = True
    barge_in_enabled: bool = False        # interrupt Jarvis mid-speech on detected speech
    # Smart barge-in: 'auto' detects the live output device and enables barge-in ONLY when
    # you're on a private endpoint (headphones / AirPods / smart-glasses / phone-with-earbuds),
    # where the mic can't re-hear Jarvis's TTS — and keeps it OFF on open speakers. 'on'/'off'
    # force it. See edge/device_profile.py. (barge_in_enabled above is the legacy hard switch
    # honoured when mode='auto' can't tell — e.g. a forced True still wins for AEC setups.)
    barge_in_mode: str = "auto"           # auto | on | off
    # For remote transports (Mentra glasses, iPhone client) the local audio device name says
    # nothing about how YOU hear Jarvis, so the client declares it: 'glasses', 'phone-headphones',
    # 'phone-speaker', 'headphones', 'speakers'. Blank = classify the local output device.
    device_hint: str | None = None
    vad_confidence: float = 0.6           # Silero speech-probability threshold (0..1)
    vad_start_secs: float = 0.2           # speech must persist this long to count as "started"
    vad_stop_secs: float = 0.6            # silence this long ends the turn
    vad_min_volume: float = 0.5           # gate out very quiet room noise

    # --- ElevenLabs (the Jarvis voice) --------------------------------------------------
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None          # the specific voice you want Jarvis to have
    elevenlabs_model: str = "eleven_flash_v2_5"     # lowest-latency streaming model
    elevenlabs_streaming: bool = True               # WebSocket streaming on by default

    # --- Deepgram (cloud STT for accurate, streaming recognition) -----------------------
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"
    # 'multi' = nova-3 multilingual code-switching: understands English, French, German, Russian
    # (+ Spanish/Hindi/Portuguese/Italian/Dutch/Japanese). Deepgram does NOT support Armenian, and
    # Ukrainian isn't in 'multi' — for those use the Whisper provider (stt_provider=whisper), which
    # auto-detects and transcribes ALL of Vazghen's six languages. Jarvis always replies in English.
    deepgram_language: str = "multi"

    # --- Audio routing (speakers <-> headphones / AirPods) ------------------------------
    # Output target: a name fragment or alias ("speakers", "headphones", "airpods") or a
    # numeric device index. None = OS default. A saved voice-command preference overrides
    # this at startup (see edge/audio_devices.py). Input stays on the laptop mic by default
    # so Bluetooth stays in high-quality A2DP output mode (using AirPods as mic forces HFP).
    audio_output_device: str | None = None
    audio_input_device: str | None = None
    # Auto-route to a connected private endpoint (AirPods Pro Max / headphones) when no explicit
    # output is set: "if they're connected to the laptop, send everything to my headphones".
    auto_route_headphones: bool = True

    # --- Local engine assets (used when provider == local) ------------------------------
    whisper_model: str = "base"           # faster-whisper size; "small" for more accuracy
    piper_voice: str = "en_US-ryan-high"
    kokoro_voice: str = "am_adam"

    # --- Brain / orchestrator -----------------------------------------------------------
    # brain_mode: "local" = run the agent in-process on the edge (fastest, no network dep);
    # "remote" = the edge is a thin client to the 24/7 VPS brain over brain_ws_url (ONE shared
    # Watari + memory across all devices); "auto" = try remote, fall back to local if unreachable.
    brain_mode: str = "local"
    brain_ws_url: str = "ws://127.0.0.1:8765/voice"   # edge -> brain socket
    brain_host: str = "127.0.0.1"                     # set 0.0.0.0 to reach from phone/glasses
    brain_port: int = 8765
    client_http_port: int = 8766                      # serves clients/iphone/ over HTTP
    api_auth_token: str | None = None                 # empty = loopback-only, no auth

    # Self-improvement loop (Hermes-style background_review): after every N turns a background pass
    # extracts durable facts about Vazghen into L1 learned memory. Off the hot path; never slows a turn.
    self_improve_enabled: bool = True
    self_improve_every_turns: int = 6

    # DEDICATED inbound bot for the 24/7 Telegram bridge (DM Watari from any device). MUST be a
    # SEPARATE bot from telegram_bot_token — that one is OpenClaw's, and two pollers fighting over
    # getUpdates steal each other's messages. The bridge only runs if this is set.
    telegram_bridge_bot_token: str | None = None

    # PC-control executor: the laptop runs edge/pc_agent.py, which connects to this control URL so
    # the (VPS) brain can run files/processes/PowerShell/open-app on the laptop. Defaults to the
    # brain_ws_url host with the /control path. Set to the VPS for laptop->VPS control.
    pc_control_url: str | None = None

    # OpenClaw Gateway (existing fleet) — an EXTERNAL team Jarvis can DELEGATE to, by
    # messaging ispir through the gateway. It is ONE of Jarvis's tools, not his brain.
    openclaw_delegation_enabled: bool = True
    # Whether Jarvis may CONSULT the fleet (via ispir) without a per-session OK. Default OFF: the
    # fleet touches shared VPS infra, so it stays a deliberate opt-in. Set JARVIS_FLEET_AUTHORIZED=
    # true in .env to arm it for a 24/7 deployment. (Jarvis still always re-voices results as himself.)
    fleet_authorized: bool = False
    openclaw_gateway_url: str = "http://100.107.141.83:3200"
    openclaw_token: str | None = None
    openclaw_remote_token: str | None = None
    openclaw_gateway_password: str | None = None
    openclaw_router_agent: str = "ispir"
    openclaw_request_timeout_seconds: int = 30
    openclaw_cli_path: str = "/home/openclaw/.npm-global/bin/openclaw"
    openclaw_cli_ssh_target: str | None = "openclaw@100.107.141.83"

    # freellmapi proxy — Jarvis's OWN reasoning LLM (runs on the VPS, tunneled to localhost).
    freellmapi_base_url: str = "http://localhost:3001/v1"
    freellmapi_api_key: str | None = None
    # Primary + ordered fallbacks (rate-limit/error -> next model). See bench/llm_bench.py.
    # Primary is the FASTEST quality-correct model (TTFT is what a voice turn feels like —
    # fine-tuning.md Item 3): 8b-instant benched ~300-700ms faster than 70b and still correct.
    # 70b-versatile is the first fallback for quality escalation when 8b errors/rate-limits.
    llm_primary_model: str = "llama-3.1-8b-instant"
    llm_fallback_models: str = "llama-3.3-70b-versatile,groq/compound,mistral-small-latest,openai/gpt-oss-20b:free"
    llm_request_timeout_seconds: int = 60

    # --- Channels & knowledge -----------------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_allowed_users: str | None = None
    vault_path: str | None = None
    audit_log_dir: str | None = None

    # --- Phase 3: knowledge & channel tools ---------------------------------------------
    # Every Phase 3 tool degrades gracefully: when its credentials are absent it returns a
    # short "not configured yet" note that Jarvis re-voices, so the brain never crashes on a
    # missing integration. Flip a key in .env to light each one up.
    http_timeout_seconds: int = 20

    # Obsidian vault (read/search the LOCAL mirror). vault_path is defined above.
    vault_search_max_results: int = 6
    vault_read_max_chars: int = 4000
    # Writing into the vault is OFF by default because on the laptop the vault is a one-way
    # VPS->local sync target (local edits get clobbered). On the AUTHORITATIVE host (the VPS that
    # owns the vault) set JARVIS_VAULT_WRITABLE=true and the write_vault tool can save notes there.
    vault_writable: bool = False

    # --- Session hygiene: smart reset ----------------------------------------------------------
    # When the gap since the last turn exceeds this many minutes, the brain SOFT-RESETS working
    # memory: it journals the prior conversation (L2) and clears the rolling history, so a new
    # conversation hours later doesn't drag stale context/anaphora ("set it back" pointing at a
    # 'it' from this morning). Durable memory (L1/L2/L3) is untouched. 0 disables.
    session_idle_reset_minutes: int = 180

    # --- Phase 9: persistent memory (learned facts L1 + daily journal L2) ----------------
    # Markdown-backed long-term memory under memory/learned and memory/journal. The vault
    # (above) is L3 and should ALWAYS be configured so he can read it; it's validated at start.
    memory_enabled: bool = True
    memory_recall_limit: int = 5        # facts returned by the recall tool
    memory_digest_max: int = 12         # recent learned facts injected into the system prompt
    #                                     (capped so a full digest keeps the prompt <=2000 tok)
    redis_url: str | None = None        # L4 hot-cache (Phase 9b); blank = no cache (graceful)
    # L5 semantic recall (Phase 9c): rank learned facts by meaning, not just keywords. Only takes
    # effect if a local embedder (`sentence-transformers`) is installed; otherwise recall stays
    # keyword-only (graceful no-op). semantic_weight scales the cosine score blended into recall.
    memory_semantic_enabled: bool = True
    memory_semantic_model: str = "all-MiniLM-L6-v2"
    memory_semantic_weight: float = 4.0

    # Web search (Tavily) + page scrape (Jina Reader) + headless interactive browse (Browserbase).
    tavily_api_key: str | None = None
    # Page scraping uses Jina Reader (https://r.jina.ai) — free and KEYLESS. This optional key only
    # raises rate limits; leave blank and scraping still works.
    jina_api_key: str | None = None
    browserbase_api_key: str | None = None
    browserbase_project_id: str | None = None

    # Telegram: a Telethon USER client is required to READ unread DMs (the Bot API cannot);
    # sending uses the simpler Bot API. telegram_bot_token is defined above.
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str = "jarvis"            # Telethon session name (one-time login)
    telegram_default_chat: str | None = None    # default recipient/chat_id for "send a telegram"
    telegram_phone: str | None = None           # your number, intl format (+...), for the one-time login
    giphy_api_key: str | None = None             # for "@gif <query>" search; falls back to Giphy's public key
    # Personal music: a Telegram chat/group where you keep audio tracks ("my playlist"). Jarvis
    # finds a track there (by name, or random) and delivers it to telegram_music_target so it
    # surfaces on your PHONE Telegram (one tap to play). id / @username / exact title all work.
    telegram_playlist_chat: str | None = None
    telegram_music_target: str = "me"            # where the chosen track is sent ('me' = Saved Messages → phone)
    # "Jarvis Music Room" group: Jarvis streams tracks into its voice chat (via pytgcalls) so they
    # play LIVE on your phone when you join that voice chat. Telethon marked id (-100…).
    telegram_music_room_chat: str | None = None

    # Default music backend for "play X". 'ytmusic' = YouTube Music (free, music-tuned search,
    # no account). 'telegram' = your personal Telegram playlist. 'youtube' = plain YouTube.
    music_source: str = "ytmusic"

    # --- Phase 11: Gmail + Calendar (one Google OAuth app) + Home Assistant -------------
    # Vazghen runs the one-time consent (bench/google_login.py) -> a refresh token below. The same
    # app/token serves Gmail (read/draft/send) and Calendar (list/create). All degrade to a spoken
    # "not configured" note until set. send_email + create_event are confirm-gated (outward-facing).
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_oauth_redirect: str = "http://127.0.0.1:8585/oauth2callback"  # must match the Google app
    gmail_address: str = "me"            # 'me' = the authorized account; or an explicit address
    # Home Assistant — local-first smart home. A long-lived access token from your HA profile, and
    # the base URL of your HA instance (e.g. http://homeassistant.local:8123). Locks/alarms confirm.
    ha_url: str | None = None
    ha_token: str | None = None

    # Notion — internal integration token (https://www.notion.so/my-integrations). SHARE the pages
    # you want Jarvis to touch with the integration (Notion is deny-by-default). read/append/comment/
    # create; writes are confirm-gated. Degrades until set.
    notion_token: str | None = None
    notion_version: str = "2022-06-28"

    # --- System control (files / processes / PowerShell) --------------------------------
    # Jarvis can manage the local machine: create/delete files & folders, list/kill/start
    # processes, and run PowerShell (optionally elevated, which raises a Windows UAC prompt).
    # These are powerful — the persona rule is to confirm anything destructive first.
    system_tools_enabled: bool = True
    # Paths under these roots are refused for deletion (defence against catastrophic rm).
    system_protected_paths: str = "C:\\Windows,C:\\Program Files,C:\\Program Files (x86)"

    # --- Phase 13: coding & self-improvement (Git + GitHub) -----------------------------
    # Jarvis can read/write his own source, run the test suite, lint, and make REVERSIBLE git
    # commits (never force-push / reset / rewrite history). Secrets (.env, sessions, voiceprint,
    # audit/, backups/) are hard-blocked from read/write. Commits + pushes are confirm-gated.
    coding_tools_enabled: bool = True
    skills_enabled: bool = True
    github_token: str | None = None              # a fine-grained PAT (Contents: read/write on the repo)
    github_repo: str | None = None               # "owner/name" — used for push guidance + status
    git_author_name: str = "Watari"              # the author on Watari's own (self-improvement) commits
    git_author_email: str = "watari@vazghen.local"

    # --- Local interactive browser (visible window, persistent login) -------------------
    # A real Chromium Jarvis drives with Playwright: open windows, click, type (incl.
    # passwords/email when you ask him to log in), navigate. Visible by default so you can
    # watch and complete anything he hands back. Persistent profile keeps you logged in.
    browser_tools_enabled: bool = True
    browser_headless: bool = False
    browser_profile_dir: str | None = None       # default: <repo>/.jarvis-browser
    browser_nav_timeout_ms: int = 30000

    # --- Protocols (password-gated executable routines, FRIDAY/JARVIS-style) -------------
    # Named programs Jarvis runs ONLY when given the matching password. CHANGE these defaults.
    protocols_enabled: bool = True
    protocol_goodnight_password: str = "morpheus"   # stops Jarvis
    protocol_phoenix_password: str = "icarus"       # restarts Jarvis
    protocol_ragnarok_password: str = "valhalla"    # restarts the laptop
    protocol_backup_password: str = "atlas"         # backs up Jarvis memory
    protocol_ping_password: str = "hermes"          # sends a phone push test
    protocol_diagnostics_password: str = "ani"      # writes a local diagnostics report
    protocol_auditpack_password: str = "artashat"   # archives audit logs
    protocol_checkpoint_password: str = "vagharshapat"  # archives key non-secret context

    # --- Phase 4: proactivity & notifications -------------------------------------------
    scheduler_db_path: str | None = None          # default: <repo>/jarvis_jobs.sqlite
    ntfy_topic: str | None = None                 # ntfy.sh topic for push when voice is unavailable
    ntfy_server: str = "https://ntfy.sh"
    # Phase 4b — always-on VPS ticker (deploy/vps/) that owns RECURRING (daily) reminders so they
    # push even with the PC off. Optional: when set, set_reminder(daily=…) also registers there.
    ticker_url: str | None = None                 # e.g. http://127.0.0.1:8770 (on the VPS host)
    ticker_token: str | None = None               # optional bearer secret matching the ticker

    # --- Phase 10: proactive engine (initiate, interrupt, clarify, confirm) -------------
    # A background tick gathers signals (routine, calendar, unread, open threads, self-health)
    # and decides whether to say something *unprompted* — helpful, never noisy. OFF by default
    # because it speaks on its own; flip JARVIS_PROACTIVE_ENABLED=true to switch the companion on.
    # ON by default for the 24/7 production companion (he initiates within budget + quiet hours).
    # For a quiet testing session, set JARVIS_PROACTIVE_ENABLED=false.
    proactive_enabled: bool = True
    proactive_tick_seconds: int = 300            # how often the tick evaluates signals
    proactive_quiet_hours: str = "23:00-07:00"   # no unprompted voice in this window (local time)
    proactive_daily_budget: int = 6              # max unprompted interjections per day
    proactive_relevance_threshold: float = 0.6   # only speak when a signal's urgency clears this
    proactive_repeat_suppress_minutes: int = 120  # don't repeat the same interjection within this
    # An exceptionally urgent signal (>= this) may still reach him in quiet hours — as a silent
    # phone push, never spoken aloud. Everything below it waits until quiet hours end.
    proactive_quiet_override_urgency: float = 0.95
    # Where "what's the weather" and the morning briefing default to when no place is named.
    home_location: str | None = None

    # --- Phase 5: speaker biometrics (respond only to Vazghen's voice) ------------------
    speaker_id_enabled: bool = False      # gate commands by speaker match (off until enrolled)
    speaker_profile_path: str | None = None  # default: <repo>/voiceprint.json
    speaker_threshold: float = 0.25       # ECAPA cosine-similarity accept threshold (~EER point)

    # --- Latency / behaviour ------------------------------------------------------------
    directed_only: bool = True            # ignore ambient speech & own playback
    aec_enabled: bool = True              # acoustic echo cancellation (don't hear self)
    ttfw_target_ms: int = 1200            # Time-To-First-Word goal, surfaced in the TUI

    @property
    def duplex_mode(self) -> str:
        """'full' = mic open while Jarvis speaks (barge-in, needs headphones/AEC);
        'half' = mic muted while Jarvis speaks (speakers-safe, no barge-in)."""
        return "full" if self.barge_in_enabled else "half"

    @property
    def using_cloud_voice(self) -> bool:
        return (
            self.stt_provider == STTProvider.deepgram
            or self.tts_provider == TTSProvider.elevenlabs
        )

    @property
    def wake_words_list(self) -> list[str]:
        return [w.strip() for w in self.wake_words.split(",") if w.strip()]

    @property
    def llm_chain(self) -> list[str]:
        """Primary model first, then ordered fallbacks (deduped, blanks dropped)."""
        chain = [self.llm_primary_model] + [
            m.strip() for m in self.llm_fallback_models.split(",") if m.strip()
        ]
        seen: set[str] = set()
        return [m for m in chain if not (m in seen or seen.add(m))]


settings = Settings()
