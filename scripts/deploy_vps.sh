#!/usr/bin/env bash
# Deploy the brain to the VPS — but ONLY if the test suite is green. Codifies the safe deploy:
# no more scp-then-discover-it-was-broken. Run from the repo root: scripts/deploy_vps.sh
set -euo pipefail

VPS="${JARVIS_VPS:-openclaw@100.107.141.83}"
REMOTE="${JARVIS_VPS_DIR:-/home/openclaw/jarvis}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> running the test suite (deploy gate)"
.venv/Scripts/python.exe -m pytest -q || { echo "TESTS FAILED — not deploying."; exit 1; }

echo "==> syncing src/jarvis + skills -> $VPS:$REMOTE (excludes pycache; never touches .env/secrets)"
# scp the source tree + skill playbooks. .env, voiceprint, sessions live only on the target.
tar --exclude='__pycache__' -czf - src/jarvis skills | ssh "$VPS" "tar -xzf - -C '$REMOTE'"

echo "==> restarting the brain + health check"
ssh "$VPS" "systemctl --user restart jarvis-brain && sleep 5 && systemctl --user is-active jarvis-brain && curl -s localhost:8766/healthz"
echo
echo "==> deployed."
