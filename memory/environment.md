# Environment & infrastructure (no secrets - those live in .env)

- **Local PC** - Windows 11, **no GPU** (CPU-only); runs `jarvis-edge` (voice). Project dir `C:\Jarvis`.
- **VPS** - `100.107.141.83` (user `openclaw`), always-on; hosts the OpenClaw fleet, the freellmapi
  proxy, and `jarvis-brain`.
- **freellmapi** - OpenAI-compatible proxy at `http://localhost:3001/v1`; Jarvis's brain primary
  model `llama-3.1-8b-instant` (fast TTFT) with a fallback chain.
- **OpenClaw Gateway** - `http://100.107.141.83:3200` (router: ispir).
- **Obsidian vault** - `C:\Users\iamva\Documents\Obsidian Vault` (one-way mirror of the VPS vault;
  **VPS authoritative** - write there, not local). Audit log dir: vault `40-Logs/`.
- **Current home location** - stored in `runtime_prefs.json` (currently Cologne, Germany), not as a
  permanent `.env` constant. Jarvis can change it with `set_home_location` whenever Vazghen moves or
  says he is spending time somewhere else.
- **Hardware not owned yet** - Mentra OS glasses and Home Assistant hardware are final-roadmap
  integrations. Leave those integrations parked until the devices exist.
