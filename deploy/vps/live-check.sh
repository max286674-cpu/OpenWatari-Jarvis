#!/usr/bin/env bash
# Weekly credential-rot check: run the live integration suite on the VPS; alert Telegram on fail.
# Installed by a systemd user timer (see install-live-check.sh). Safe to run by hand.
set -u
cd "$HOME/jarvis" || exit 1

OUT=$(.venv/bin/python bench/test_live_integrations.py 2>&1)
STATUS=$?
echo "$OUT" | tail -20

if [ $STATUS -ne 0 ]; then
  TOKEN=$(grep -oP '^JARVIS_TELEGRAM_BOT_TOKEN=\K.+' .env || true)
  CHAT=$(grep -oP '^JARVIS_TELEGRAM_DEFAULT_CHAT=\K.+' .env || true)
  if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
    SUMMARY=$(echo "$OUT" | tail -6 | head -c 800)
    curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${CHAT}" \
      --data-urlencode "text=⚠️ Watari weekly live-integration check FAILED:
${SUMMARY}" > /dev/null
  fi
fi
exit $STATUS
