# Security

Jarvis is a high-trust agent: he runs shell commands, drives a real browser, sends messages and
email, controls smart-home devices, and edits and commits his own source code. This document
describes the safety model that makes that trustworthy, what is kept out of version control, and how
to report a problem.

> **Design principle: least surprise, full reversibility, deny-by-default.** Every consequential
> action is either confirmed first, reversible, scoped, or all three. A missing credential degrades
> to a spoken "not configured" note — never a crash and never a silent failure.

---

## 1. Secrets & credentials

**Secrets never live in code and never enter version control.**

- All secrets are read from environment variables (prefix `JARVIS_`) via a local **`.env`** file,
  which is **git-ignored**. Only `.env.example` (no values) is committed.
- The following are explicitly excluded from git (see [`.gitignore`](.gitignore)):
  `.env` and any `.env.*` (except the example), `*.session` / `*.session-journal` (Telegram/Telethon
  logins), `voiceprint.json` (your biometric template), `jarvis_jobs.sqlite`, `audit/`, `backups/`,
  `.jarvis-browser/` (the persistent browser profile, which holds login cookies), and Jarvis's
  private memory (`memory/learned/`, `memory/journal/`).
- The **audit log redacts secrets**: any tool argument whose key looks like a password / token /
  secret / api_key / auth / credential is written as `***redacted***`. Protocol passwords are never
  logged or spoken.
- If you publish this repo, make it **private** — the committed context (`memory/*.md`,
  `personality/jarvis.md`) is personal, and host/service details may be sensitive.

**Token scopes.** Use the narrowest credential that works:
- GitHub: a **fine-grained PAT** limited to the one repo, **Contents: read/write** only.
- Notion: an **internal integration**, and **share only the specific pages** you want Jarvis to
  touch (Notion is deny-by-default — the integration sees nothing else).
- Google: the OAuth app is yours; keep yourself as the only test user.

---

## 2. Confirmation tier (outward-facing & destructive actions)

Jarvis **confirms before acting** on anything outward-facing or hard to undo. The persona reads back
what it's about to do and waits for an explicit yes. Enforced as a policy
(`brain/proactive.py::CONFIRM_TIER` + `confirm_required`) and reinforced in the system prompt:

- Messaging/outbound: `send_telegram`, `send_email`, `send_push`.
- Machine: `file_op` (deletes), `process_op` (kill/start), `run_powershell`, `browser`.
- Calendar/home/Notion: `create_event`, `ha_call` (locks/alarms/covers especially),
  `notion_append`, `notion_comment`, `notion_create_page`.
- Self-improvement: `write_source`, `git_commit`, `git_push`, `git_revert`.
- Protocols: `run_protocol`.

Reads and lookups (recall, web/vault search, weather, `read_email`, `read_chat`, `git_status`, …)
need no confirmation — they have no side effects.

**Clarify before guessing.** An ambiguous request ("do it", a bare pronoun) triggers a clarifying
question instead of a risky guess (`needs_clarification`).

---

## 3. Filesystem & system guardrails

- **Destructive file ops refuse protected paths.** `file_op` deletes are blocked under
  `JARVIS_SYSTEM_PROTECTED_PATHS` (default `C:\Windows`, `C:\Program Files`,
  `C:\Program Files (x86)`) and drive roots.
- **Elevation is explicit.** `run_powershell(as_admin=true)` raises a Windows UAC prompt you must
  accept; Jarvis cannot silently elevate.
- **The browser is visible by default** (`JARVIS_BROWSER_HEADLESS=false`) so you can watch what it
  does and complete logins yourself.

---

## 4. Self-improvement guardrails (Phase 13)

Letting an agent edit its own code is safe here because the capability is deliberately constrained:

- **Repo-scoped.** `read_source` / `write_source` / `list_source` resolve paths and **refuse
  anything outside the repository** (no path traversal) and **refuse secrets** (`.env`, `*.session`,
  `voiceprint.json`, `audit/`, `backups/`, `.git/`).
- **Reversible-only git.** The git tools are `status`, `diff`, `log`, `new_branch`, `commit`,
  `push`, `revert`. There is **no** `reset`, `force-push`, `rebase`, `amend`, `clean`, or
  branch-delete tool — by design. History can be added to, never rewritten or destroyed; a revert is
  always a new commit.
- **Verify-then-commit.** He has `run_tests` and `lint`, and the self-improvement playbook instructs
  him to commit only green code, on a branch, after your confirmation.
- **Confirm-gated.** Writes, commits, and pushes are all in the confirmation tier.

Net effect: the worst case is an uncommitted bad edit (caught by tests) or a committed change you can
`git_revert`. Your work cannot be lost.

---

## 5. Protocols (privileged routines)

`goodnight` (stop), `phoenix` (restart Jarvis), and `ragnarok` (restart the machine) are
**password-gated**. Jarvis asks for the password first; it's compared in constant time
(`hmac.compare_digest`); a wrong or missing password runs nothing. **Change the default passwords**
in `.env` (`JARVIS_PROTOCOL_*_PASSWORD`) before deploying. Passwords are never spoken or logged.

The non-privileged routines (`briefing`, `focus`, `lockdown`, `guest`, `commute`, `panic`, `backup`,
`normal`) change *behaviour*, not the system, and need no password.

---

## 6. Speaker biometrics (optional)

With `JARVIS_SPEAKER_ID_ENABLED=true` and an enrolled voiceprint, Jarvis obeys **only your voice**
and ignores the TV or a guest. It's **off until you enroll** — and deliberately fails *open* (accepts
all) rather than risk locking you out if no profile exists. The voiceprint (`voiceprint.json`) is
git-ignored.

---

## 7. The OpenClaw fleet is gated

Jarvis can *consult* an external multi-agent fleet, but it touches shared infrastructure, so it is
**off by default** (`fleet_authorized=False`). Arm it deliberately per session, or for a deployment
via `JARVIS_FLEET_AUTHORIZED=true`. Until armed, `delegate_to_fleet` returns a safe sentinel and
performs no network action. Jarvis always re-voices any fleet result as himself.

---

## 8. Audit trail

Every tool call is appended (best-effort, fail-quiet) to `audit/<date>.jsonl` with a timestamp, the
tool name, **redacted** arguments, success flag, and a clipped result. This is the trust-and-debug
record: you can see exactly what Jarvis did. The audit directory is git-ignored (it can contain
personal context).

---

## 9. Network & privacy posture

- **Local-first.** Audio capture, wake-word, VAD, and (optionally) STT/TTS run on your machine.
  Cloud STT/TTS (Deepgram/ElevenLabs) are opt-in quality choices behind provider flags.
- **Loopback by default.** The brain WebSocket binds `127.0.0.1`. To reach it from a phone/glasses,
  bind `0.0.0.0` **and set `JARVIS_API_AUTH_TOKEN`** — remote clients must then present
  `Authorization: Bearer <token>`. Don't expose it without the token.
- **Graceful degradation** means an unconfigured integration makes **no** network calls at all.

---

## 10. Reporting a vulnerability

This is a personal project, not a service. If you find a security issue in the code (e.g. a way to
bypass the path/secret guards, the confirmation tier, or the protocol password check), please open a
**private** report (a private issue or direct contact with the repository owner) rather than a public
issue. Include reproduction steps and the affected file/function.

---

## 11. Operator responsibilities

- Keep the repository **private**; rotate any key that has ever been shared in plaintext.
- Change the default protocol passwords.
- Review `TODO-NOW.md` before enabling outward-facing integrations.
- Treat the host running the brain as a trusted machine — it holds the tokens that let Jarvis act on
  your behalf.
