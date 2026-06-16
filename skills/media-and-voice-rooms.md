# Music & voice rooms — streaming into Telegram, voice notes

## Music
- `play_music` default source `ytmusic` opens YouTube Music in the browser (free, plays out loud on
  whatever host has the browser).
- **The Music Room (his phone, live):** source `telegram` now STREAMS the track into the Telegram
  Music Room **voice chat** via pytgcalls (`play_in_music_room`) — NOT a file. He joins that group's
  voice chat once and hears every track you stream. Use this when he says "play X in the music room /
  on my phone / in Telegram." `stop_music_room` leaves the call.
- Pick a track by name, `latest` for the newest, or blank for a random/shuffle from his playlist.
- Only a **user account** (your Telethon session) can join a Telegram voice chat — the bot cannot.
  The stream lives in the long-running brain process, so it persists 24/7.
- `local=true` on the telegram source plays it OUT LOUD on the desktop instead of streaming.

## Voice notes & proactive voice (the phone)
- Telegram replies go out as **voice notes** (OGG/Opus) by the dedicated bridge bot, never the
  OpenClaw bot. Text is only a fallback if synthesis fails.
- Proactive/unprompted lines: if a live voice device is connected you speak there; otherwise you push
  a **Telegram voice note** to his authorized chat (`send_proactive`), with an ntfy text push as the
  last resort. So a nudge or a fired reminder reaches his phone as your voice, laptop or not.
- The iPhone Siri Shortcut hits `POST /talk`: dictation in → your spoken reply out. Same shared
  brain/memory as voice and Telegram.
