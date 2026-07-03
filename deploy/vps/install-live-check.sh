#!/usr/bin/env bash
# Install the weekly live-integration check (systemd user timer). Run ON the VPS, once.
set -euo pipefail
mkdir -p ~/.config/systemd/user
cp "$(dirname "$0")/live-check.sh" "$HOME/jarvis/live-check.sh"
chmod +x "$HOME/jarvis/live-check.sh"

cat > ~/.config/systemd/user/jarvis-live-check.service <<'EOF'
[Unit]
Description=Watari weekly live-integration check (credential rot)

[Service]
Type=oneshot
ExecStart=%h/jarvis/live-check.sh
EOF

cat > ~/.config/systemd/user/jarvis-live-check.timer <<'EOF'
[Unit]
Description=Run the Watari live-integration check weekly

[Timer]
OnCalendar=Mon 07:30
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now jarvis-live-check.timer
systemctl --user list-timers jarvis-live-check.timer --no-pager
