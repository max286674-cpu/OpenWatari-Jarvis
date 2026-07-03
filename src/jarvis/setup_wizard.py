"""Interactive terminal setup wizard for forking Jarvis into your own voice assistant.

Run it once after cloning:  ``uv run jarvis-setup``  (or ``uv run python -m jarvis.setup_wizard``).

It walks you through the choices that matter — what to call your assistant, cloud vs local voice,
your LLM backend, whether this is a single machine or a 24/7 VPS brain serving multiple devices —
asks only for the keys those choices need, auto-generates the security tokens and protocol
passwords, and writes a ready ``.env`` (backing up any existing one). Everything you skip stays at
its documented default in ``.env.example`` and degrades gracefully at runtime.

The wizard never prints a secret back to the screen and never commits anything. It only writes
``.env`` (git-ignored). Re-run it any time to reconfigure.

It uses `rich` for a nicer UI when available, and falls back to plain text so it also runs on a
bare ``uv sync`` (base deps only).
"""

from __future__ import annotations

import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / ".env.example"
OUT = REPO_ROOT / ".env"
PERSONA = REPO_ROOT / "personality" / "jarvis.md"
PERSONA_EXAMPLE = REPO_ROOT / "personality" / "persona.example.md"
MEMORY_DIR = REPO_ROOT / "memory"
# (example template -> user's private file) seeded on first run so the user edits private copies,
# not the shipped templates. These targets are gitignored.
PROFILE_SEEDS = [
    ("about-you.example.md", "about-you.md"),
    ("projects.example.md", "projects.md"),
    ("environment.example.md", "environment.md"),
]

# Wake phrases openWakeWord ships pre-trained (free, CPU). Anything else needs Porcupine + a
# Picovoice key — we surface that rather than silently accept an unsupported phrase.
OPENWW_PHRASES = ["hey jarvis", "alexa", "hey mycroft", "hey rhasspy"]

# The eight password-gated protocols (brain/protocols.py). The wizard generates a strong password
# for each so a fork is never shipped with the placeholder passwords from .env.example.
PROTOCOL_KEYS = [
    "JARVIS_PROTOCOL_GOODNIGHT_PASSWORD",
    "JARVIS_PROTOCOL_PHOENIX_PASSWORD",
    "JARVIS_PROTOCOL_RAGNAROK_PASSWORD",
    "JARVIS_PROTOCOL_BACKUP_PASSWORD",
    "JARVIS_PROTOCOL_PING_PASSWORD",
    "JARVIS_PROTOCOL_DIAGNOSTICS_PASSWORD",
    "JARVIS_PROTOCOL_AUDITPACK_PASSWORD",
    "JARVIS_PROTOCOL_CHECKPOINT_PASSWORD",
]


# --------------------------------------------------------------------------------------------------
# UI layer — rich if present, plain otherwise. Kept tiny so the wizard reads top-to-bottom.
# --------------------------------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    _c = Console()

    def banner(title: str, body: str) -> None:
        _c.print(Panel(body, title=title, border_style="cyan", expand=False))

    def say(msg: str) -> None:
        _c.print(msg)

    def ask(q: str, default: str | None = None, secret: bool = False,
            choices: list[str] | None = None) -> str:
        return Prompt.ask(q, default=default, password=secret, choices=choices)

    def yes(q: str, default: bool = False) -> bool:
        return Confirm.ask(q, default=default)

except ImportError:  # bare install — no rich yet
    def banner(title: str, body: str) -> None:
        print(f"\n=== {title} ===\n{body}\n")

    def say(msg: str) -> None:
        print(re.sub(r"\[/?[a-z0-9 ._-]+\]", "", msg))  # strip rich markup

    def ask(q: str, default: str | None = None, secret: bool = False,
            choices: list[str] | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        if choices:
            suffix = f" ({'/'.join(choices)})" + suffix
        if secret:
            import getpass
            val = getpass.getpass(f"{q}{suffix}: ").strip()
        else:
            val = input(f"{q}{suffix}: ").strip()
        return val or (default or "")

    def yes(q: str, default: bool = False) -> bool:
        d = "Y/n" if default else "y/N"
        val = input(f"{q} ({d}): ").strip().lower()
        return default if not val else val.startswith("y")


def seed_if_missing(src: Path, dst: Path) -> bool:
    """Copy a shipped template to the user's private file only if it doesn't exist yet. Never clobbers."""
    if dst.exists() or not src.exists():
        return False
    shutil.copy2(src, dst)
    return True


def mask(value: str) -> str:
    if not value:
        return "(blank)"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}...{value[-2:]} ({len(value)} chars)"


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines of an existing .env → dict, so a re-run offers current values as defaults."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


# --------------------------------------------------------------------------------------------------
# Live key validation — a wrong key today fails silently at runtime; probe it while the user is
# still at the keyboard. Every probe is a cheap authenticated GET; network-down never blocks setup.
# --------------------------------------------------------------------------------------------------
def _http_ok(url: str, headers: dict[str, str] | None = None) -> bool | None:
    """True/False = key checked; None = couldn't reach the API (offline / no httpx)."""
    try:
        import httpx

        return httpx.get(url, headers=headers or {}, timeout=8).status_code < 400
    except Exception:  # noqa: BLE001
        return None


PROBES = {
    "deepgram": lambda k: _http_ok("https://api.deepgram.com/v1/projects",
                                   {"Authorization": f"Token {k}"}),
    "elevenlabs": lambda k: _http_ok("https://api.elevenlabs.io/v1/user", {"xi-api-key": k}),
    "notion": lambda k: _http_ok("https://api.notion.com/v1/users/me",
                                 {"Authorization": f"Bearer {k}", "Notion-Version": "2022-06-28"}),
    "telegram-bot": lambda k: _http_ok(f"https://api.telegram.org/bot{k}/getMe"),
}


def ask_key(label: str, probe=None, keep: str = "") -> str:
    """Secret prompt: Enter keeps the existing value (masked); a typed key is live-validated."""
    hint = f" (Enter = keep {mask(keep)})" if keep else ""
    while True:
        val = ask(f"{label}{hint}", secret=True) or keep
        if not val or probe is None or val == keep:
            return val
        say("  checking the key against the live API…")
        ok = probe(val)
        if ok:
            say("  [green]key OK[/green]")
            return val
        if ok is None:
            say("  [yellow]couldn't reach the API — keeping the key; verify once online.[/yellow]")
            return val
        if not yes("  That key did NOT validate. Re-enter?", default=True):
            return val


# --------------------------------------------------------------------------------------------------
# .env rendering — copy .env.example line-by-line, swapping only the values we collected, so every
# inline comment / default the forker didn't touch is preserved verbatim.
# --------------------------------------------------------------------------------------------------
def render_env(template_text: str, overrides: dict[str, str]) -> str:
    out_lines: list[str] = []
    seen: set[str] = set()
    for line in template_text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m and m.group(1) in overrides:
            key = m.group(1)
            out_lines.append(f"{key}={overrides[key]}")
            seen.add(key)
        else:
            out_lines.append(line)
    # Any override not present in the template (shouldn't happen) gets appended so nothing is lost.
    extra = [k for k in overrides if k not in seen]
    if extra:
        out_lines.append("\n# ---- added by setup wizard ----")
        out_lines += [f"{k}={overrides[k]}" for k in extra]
    return "\n".join(out_lines) + "\n"


# --------------------------------------------------------------------------------------------------
# The guided flow.
# --------------------------------------------------------------------------------------------------
def run() -> None:
    if not TEMPLATE.is_file():
        say(f"[red]Could not find {TEMPLATE}. Run this from a Jarvis checkout.[/red]")
        raise SystemExit(1)

    banner("Jarvis setup wizard", (
        "This configures your own voice assistant and writes [bold].env[/bold].\n"
        "Press Enter to accept the [dim][default][/dim] shown for any question.\n"
        "Secrets are typed hidden and never printed back."
    ))

    cur: dict[str, str] = {}
    if OUT.exists():
        if not yes(f".env already exists at {OUT}. Reconfigure? Your current values become the "
                   "defaults — Enter keeps them (a backup is made).", default=False):
            say("Nothing changed. Bye.")
            return
        cur = parse_env(OUT.read_text(encoding="utf-8"))

    ov: dict[str, str] = {}

    # 1) Identity ---------------------------------------------------------------------------------
    banner("1 · Identity", "Make it YOUR assistant — these fill the persona template, no code edits.")
    name = ask("What should your assistant call itself?",
               default=cur.get("JARVIS_ASSISTANT_NAME") or "Watari")
    ov["JARVIS_ASSISTANT_NAME"] = name
    ov["JARVIS_USER_NAME"] = ask("Your name (blank = it won't use a name)",
                                 default=cur.get("JARVIS_USER_NAME", "")) or ""
    ov["JARVIS_USER_ADDRESS"] = ask(
        'How should it address you? ("sir", "boss", your name, or blank)',
        default=cur.get("JARVIS_USER_ADDRESS", "")) or ""
    ov["JARVIS_UNDERSTOOD_LANGUAGES"] = ask(
        "Languages it should UNDERSTAND (comma-separated)",
        default=cur.get("JARVIS_UNDERSTOOD_LANGUAGES") or "English")
    ov["JARVIS_REPLY_LANGUAGE"] = ask("Language it should always REPLY in",
                                      default=cur.get("JARVIS_REPLY_LANGUAGE") or "English")
    # Ensure a persona template exists (fresh clone → copy the generic example), then seed the user's
    # PRIVATE profile files from their examples so they edit private copies, not the shipped templates.
    if seed_if_missing(PERSONA_EXAMPLE, PERSONA):
        say(f"  Created [bold]personality/jarvis.md[/bold] from the template — edit it to shape "
            f"{name}'s voice. The identity above fills its tokens automatically.")
    else:
        say(f"  Persona at [bold]personality/jarvis.md[/bold] — edit the prose to shape {name}'s "
            "voice; the identity above fills its tokens automatically.")
    seeded = [dst for src, dst in PROFILE_SEEDS if seed_if_missing(MEMORY_DIR / src, MEMORY_DIR / dst)]
    if seeded:
        say("  Seeded your private profile files (fill them with your details): "
            + ", ".join(f"memory/{p}" for p in seeded))
    say(f"  Pre-trained wake phrases (free, on-device): {', '.join(OPENWW_PHRASES)}.")
    say("  Custom phrases (e.g. your assistant's own name): train a FREE openWakeWord model "
        "(no API key) and list the .onnx path here alongside phrases — see the docs site "
        "(Personalize → custom wake words). Porcupine (Picovoice key) also works.")
    wake = ask("Wake phrase(s) and/or .onnx paths, comma-separated",
               default=cur.get("JARVIS_WAKE_WORDS") or "hey jarvis")
    ov["JARVIS_WAKE_WORDS"] = wake

    # 2) Voice providers --------------------------------------------------------------------------
    banner("2 · Voice", "Cloud = best quality (needs keys). Local = private + free (CPU, heavier).")
    voice_now = "local" if cur.get("JARVIS_STT_PROVIDER") in ("whisper", "moonshine") else "cloud"
    voice = ask("Voice stack", default=voice_now, choices=["cloud", "local"])
    if voice == "cloud":
        ov["JARVIS_STT_PROVIDER"] = "deepgram"
        ov["JARVIS_TTS_PROVIDER"] = "elevenlabs"
        ov["JARVIS_ELEVENLABS_API_KEY"] = ask_key(
            "ElevenLabs API key (TTS)", PROBES["elevenlabs"], cur.get("JARVIS_ELEVENLABS_API_KEY", ""))
        ov["JARVIS_ELEVENLABS_VOICE_ID"] = ask(
            "ElevenLabs voice ID", default=cur.get("JARVIS_ELEVENLABS_VOICE_ID", "")) or ""
        ov["JARVIS_DEEPGRAM_API_KEY"] = ask_key(
            "Deepgram API key (STT)", PROBES["deepgram"], cur.get("JARVIS_DEEPGRAM_API_KEY", ""))
        say("  Tip: for Armenian/Ukrainian set JARVIS_STT_PROVIDER=whisper (local) later.")
    else:
        ov["JARVIS_STT_PROVIDER"] = ask("Local STT", default="whisper",
                                        choices=["whisper", "moonshine"])
        ov["JARVIS_TTS_PROVIDER"] = ask("Local TTS", default="piper", choices=["piper", "kokoro"])
        say("  No voice keys needed. Models download on first use.")

    # 3) Brain LLM --------------------------------------------------------------------------------
    banner("3 · Brain (the LLM that thinks)", "Jarvis runs his own reasoning model + tool loop.")
    backend = ask("LLM backend", default=cur.get("JARVIS_LLM_BACKEND") or "freellmapi",
                  choices=["freellmapi", "openai", "ollama"])
    ov["JARVIS_LLM_BACKEND"] = backend
    if backend == "freellmapi":
        base = ask("freellmapi base URL",
                   default=cur.get("JARVIS_FREELLMAPI_BASE_URL") or "http://127.0.0.1:3001/v1")
        ov["JARVIS_FREELLMAPI_BASE_URL"] = base
        ov["JARVIS_FREELLMAPI_API_KEY"] = ask_key(
            "freellmapi API key",
            lambda k: _http_ok(f"{base.rstrip('/')}/models", {"Authorization": f"Bearer {k}"}),
            cur.get("JARVIS_FREELLMAPI_API_KEY", ""))
    elif backend == "openai":
        base = ask("OpenAI-compatible base URL",
                   default=cur.get("JARVIS_FREELLMAPI_BASE_URL") or "https://api.openai.com/v1")
        ov["JARVIS_FREELLMAPI_BASE_URL"] = base
        ov["JARVIS_FREELLMAPI_API_KEY"] = ask_key(
            "OpenAI API key",
            lambda k: _http_ok(f"{base.rstrip('/')}/models", {"Authorization": f"Bearer {k}"}),
            cur.get("JARVIS_FREELLMAPI_API_KEY", ""))
        ov["JARVIS_LLM_PRIMARY_MODEL"] = ask(
            "Model id", default=cur.get("JARVIS_LLM_PRIMARY_MODEL") or "gpt-4o-mini")
        # The default fallback chain is freellmapi-proxy model ids — meaningless against a plain
        # OpenAI-compatible endpoint, so keep only a user-curated chain.
        ov["JARVIS_LLM_FALLBACK_MODELS"] = cur.get("JARVIS_LLM_FALLBACK_MODELS", "")
    else:
        ov["JARVIS_FREELLMAPI_BASE_URL"] = ask(
            "Ollama base URL",
            default=cur.get("JARVIS_FREELLMAPI_BASE_URL") or "http://127.0.0.1:11434/v1")
        ov["JARVIS_LLM_PRIMARY_MODEL"] = ask(
            "Local model", default=cur.get("JARVIS_LLM_PRIMARY_MODEL") or "llama3.1")
        ov["JARVIS_LLM_FALLBACK_MODELS"] = cur.get("JARVIS_LLM_FALLBACK_MODELS", "")

    # 4) Knowledge (vault) ------------------------------------------------------------------------
    banner("4 · Knowledge", "An Obsidian/Markdown folder is the assistant's long-term L3 memory.")
    vault = ask("Path to your notes folder (Obsidian vault)",
                default=cur.get("JARVIS_VAULT_PATH")
                or str(Path.home() / "Documents" / "Obsidian Vault"))
    ov["JARVIS_VAULT_PATH"] = vault

    # 5) Deployment shape -------------------------------------------------------------------------
    banner("5 · Deployment", (
        "[bold]single[/bold] = one machine, loopback only.\n"
        "[bold]vps[/bold] = 24/7 brain reachable by your phone / other devices (binds 0.0.0.0,\n"
        "       protected by an auth token the wizard generates)."
    ))
    shape_now = "vps" if cur.get("JARVIS_BRAIN_HOST") == "0.0.0.0" else "single"
    shape = ask("Deployment", default=shape_now, choices=["single", "vps"])
    if shape == "vps":
        ov["JARVIS_BRAIN_HOST"] = "0.0.0.0"
        # Keep an existing token across re-runs — rotating it here would silently strand every
        # already-configured device. Rotate deliberately by blanking it in .env first.
        ov["JARVIS_API_AUTH_TOKEN"] = cur.get("JARVIS_API_AUTH_TOKEN") or secrets.token_urlsafe(36)
        m = re.match(r"ws://([^:/]+)", cur.get("JARVIS_BRAIN_WS_URL", ""))
        host = ask("Public/Tailscale host or IP devices will connect to (for the edge URL)",
                   default=m.group(1) if m else "127.0.0.1")
        ov["JARVIS_BRAIN_WS_URL"] = f"ws://{host}:8765/voice"
        say("  [green]Brain API auth token set[/green] (saved to .env, shown masked at the "
            "end). Remote clients must send it as a Bearer token / ?token=.")
    else:
        ov["JARVIS_BRAIN_HOST"] = "127.0.0.1"

    # 6) Security: protocol passwords (generated once, kept across re-runs) -----------------------
    banner("6 · Security", "Strong passwords for the 8 privileged protocols (kept if already set).")
    for k in PROTOCOL_KEYS:
        ov[k] = cur.get(k) or secrets.token_urlsafe(12)
    say("  [green]Done[/green] — goodnight / phoenix / ragnarok / backup / ping / diagnostics / "
        "auditpack / checkpoint are now uniquely gated. (Saved to .env; ask the assistant to read "
        "them back is refused by design — keep your .env safe.)")

    # 7) Optional integrations --------------------------------------------------------------------
    banner("7 · Optional integrations", "Add now or leave blank and wire later via TODO-NOW.md.")
    if yes("Configure any optional integrations now?", default=False):
        if yes("Telegram (read + send messages, voice notes)?", default=False):
            ov["JARVIS_TELEGRAM_API_ID"] = ask("Telegram api_id (my.telegram.org)",
                                               default=cur.get("JARVIS_TELEGRAM_API_ID", "")) or ""
            ov["JARVIS_TELEGRAM_API_HASH"] = ask_key(
                "Telegram api_hash", None, cur.get("JARVIS_TELEGRAM_API_HASH", ""))
            ov["JARVIS_TELEGRAM_BOT_TOKEN"] = ask_key(
                "Bot token (optional, for sending)", PROBES["telegram-bot"],
                cur.get("JARVIS_TELEGRAM_BOT_TOKEN", ""))
            ov["JARVIS_TELEGRAM_PHONE"] = ask("Your phone (+countrycode) for one-time login",
                                              default=cur.get("JARVIS_TELEGRAM_PHONE", "")) or ""
            say("  Then run: uv run python bench/telegram_login.py (one-time interactive sign-in).")
        if yes("Web search (Tavily)?", default=False):
            ov["JARVIS_TAVILY_API_KEY"] = ask_key(
                "Tavily API key", None, cur.get("JARVIS_TAVILY_API_KEY", ""))
        if yes("Gmail + Google Calendar (one OAuth app)?", default=False):
            ov["JARVIS_GOOGLE_CLIENT_ID"] = ask("Google client id",
                                                default=cur.get("JARVIS_GOOGLE_CLIENT_ID", "")) or ""
            ov["JARVIS_GOOGLE_CLIENT_SECRET"] = ask_key(
                "Google client secret", None, cur.get("JARVIS_GOOGLE_CLIENT_SECRET", ""))
            say("  Then run: uv run python bench/google_login.py and paste the refresh token.")
        if yes("Notion (read/write/comment)?", default=False):
            ov["JARVIS_NOTION_TOKEN"] = ask_key(
                "Notion integration token", PROBES["notion"], cur.get("JARVIS_NOTION_TOKEN", ""))
        if yes("Phone push (ntfy)?", default=False):
            ov["JARVIS_NTFY_TOPIC"] = ask("ntfy topic (pick an unguessable string)",
                                          default=f"jarvis-{secrets.token_hex(4)}")

    # 8) Proactivity + fleet ----------------------------------------------------------------------
    banner("8 · Behaviour", "Whether the assistant may speak unprompted, and the fleet consult.")
    ov["JARVIS_PROACTIVE_ENABLED"] = "true" if yes(
        "Allow proactive (unprompted) reminders/nudges? Respects quiet hours + a daily budget.",
        default=(shape == "vps")) else "false"
    ov["JARVIS_FLEET_AUTHORIZED"] = "false"  # always off by default — opt in by editing .env

    # Write it ------------------------------------------------------------------------------------
    # Re-runs render over the EXISTING .env (not the template) so every value the user didn't
    # revisit — extra keys, hand edits, comments — survives untouched. Fresh runs use the template.
    base_text = OUT.read_text(encoding="utf-8") if OUT.exists() else TEMPLATE.read_text(encoding="utf-8")
    if OUT.exists():
        backup = OUT.with_suffix(f".bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(OUT, backup)
        say(f"  Backed up existing .env → {backup.name}")
    OUT.write_text(render_env(base_text, ov), encoding="utf-8")

    # Summary (masked) ----------------------------------------------------------------------------
    secretish = re.compile(r"KEY|TOKEN|SECRET|HASH|PASSWORD")
    lines = []
    for k, v in ov.items():
        lines.append(f"  {k} = {mask(v) if secretish.search(k) else (v or '(blank)')}")
    banner("Wrote .env", "\n".join(lines))

    banner("Next steps", (
        "1. Install the stack you chose, e.g.:\n"
        "   [bold]uv sync --extra edge --extra cloud-voice --extra brain "
        "--extra channels --extra identity --extra dev[/bold]\n"
        "   (drop cloud-voice and add local-voice for a fully local stack)\n"
        "2. Verify:  [bold]uv run python bench/run_all_tests.py[/bold]\n"
        "3. Talk locally:  [bold]uv run python -m jarvis.edge.assistant[/bold]\n"
        "   or run the shared brain:  [bold]uv run python -m jarvis.brain.server[/bold]\n"
        "4. Finish credential logins + the device test plan in [bold]TODO-NOW.md[/bold].\n"
        f"5. Personalise [bold]personality/jarvis.md[/bold] to make it truly \"{name}\"."
    ))


def main() -> None:
    try:
        run()
    except (KeyboardInterrupt, EOFError):
        say("\nCancelled — no changes written.")


if __name__ == "__main__":
    main()
