# Jarvis VPS ticker — true 24/7 recurring reminders (Phase 4b)

Jarvis already delivers **one-shot / `at`** reminders to your phone even when the PC is off:
`set_reminder` hands those to **ntfy.sh**, which holds them server-side and pushes at the right
time (window: ~10s to 3 days out). No VPS needed for those.

**Recurring** reminders ("every day at 08:00") are the one case ntfy can't hold — a repeating
schedule needs a process that is itself always on. This tiny daemon is that process. It runs on
the VPS you already have (`openclaw@100.107.141.83`), owns the daily jobs, and pushes them to the
**same ntfy topic** the edge uses. It's fully decoupled from the OpenClaw fleet/gateway — it only
knows ntfy + a local JSON file.

## What's here
- `jarvis_ticker.py` — the daemon (APScheduler + a tiny HTTP API; deps: `apscheduler`, `httpx`).
- `jarvis-ticker.service` — systemd unit template.
- `install.sh` — one-command deploy (venv + env file + service).

## Deploy (run ON the VPS)
```bash
# from this directory, copied to the VPS:
JARVIS_NTFY_TOPIC=jarvis-vaz-619-7f3k9q2 bash install.sh
```
Use the **same** `JARVIS_NTFY_TOPIC` as your edge `.env`. The script makes a venv, writes
`ticker.env`, installs+enables the systemd service, and prints a health check.

Optional env: `JARVIS_TICKER_PORT` (8770), `JARVIS_TICKER_HOST` (127.0.0.1),
`JARVIS_TICKER_TOKEN` (shared bearer secret), `JARVIS_TICKER_TZ` (Europe/Berlin).

## Point the edge at it
In the edge `.env`:
```
JARVIS_TICKER_URL=http://127.0.0.1:8770
JARVIS_TICKER_TOKEN=        # match the ticker if you set one
```
After that, `set_reminder(daily="08:00", ...)` on the PC **also** registers the reminder on the
ticker, so it fires from the VPS even with the laptop off. `cancel_reminder` removes it from both.
If `JARVIS_TICKER_URL` is unset/unreachable, nothing breaks — the local scheduler still speaks it
when the PC is on (graceful degradation).

> The ticker binds `127.0.0.1` by default. The edge must reach it over the same host/tunnel you
> use for the gateway (e.g. Tailscale `100.107.141.83`, or an SSH tunnel). Bind `0.0.0.0` only
> behind a firewall, and set `JARVIS_TICKER_TOKEN` if you do.

## Verify
```bash
curl -s http://127.0.0.1:8770/health                # {"ok":true,"jobs":N}
curl -s -XPOST http://127.0.0.1:8770/reminders \
  -d '{"message":"test","daily":"09:00"}'           # schedules + persists
curl -s http://127.0.0.1:8770/reminders             # lists it
journalctl -u jarvis-ticker -f                      # watch it fire/push
```
