#!/data/data/com.termux/files/usr/bin/bash
# Launch Watari edge-lite (push-to-talk) on Android/Termux.
set -euo pipefail

REPO="${WATARI_REPO:-$HOME/OpenWatari}"
cd "$REPO"

# Load local secrets if present (JARVIS_BRAIN_WS_URL, JARVIS_API_AUTH_TOKEN, JARVIS_GROQ_API_KEY).
[ -f "$HOME/.watari.env" ] && set -a && . "$HOME/.watari.env" && set +a

# Keep the CPU awake while the loop runs so the mic/link don't sleep (needs termux-api).
termux-wake-lock 2>/dev/null || true
trap 'termux-wake-unlock 2>/dev/null || true' EXIT

exec uv run python -m jarvis.edge.edge_lite
