"""One-shot local rebuild for the Windows edge runtime.

Run after `git pull`. It fixes the two remaining runtime blockers without requiring manual edits:
1) local Pipecat segmented STT receives WAV bytes; decode the WAV container before faster-whisper/
   Moonshine (Pipecat tracked this exact class of bug in 2026);
2) Russian confirmation is executed deterministically instead of sending "да" back through the LLM.
It also aligns the local .env with the OpenRouter/Qwen + Russian voice configuration and replaces
English progress/acknowledgements with Russian.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "jarvis"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"anchor not found in {path}: {old[:90]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_stt() -> None:
    path = SRC / "edge" / "stt.py"
    text = path.read_text(encoding="utf-8")
    if "def _decode_segment_audio" not in text:
        anchor = "from jarvis.config import STTProvider, settings\n\n\n"
        helper = '''from jarvis.config import STTProvider, settings\n\n\ndef _decode_segment_audio(audio: bytes):\n    """Decode Pipecat segmented audio correctly. SegmentedSTTService may pass a WAV container.\n\n    Never feed the RIFF/WAV header into faster-whisper or Moonshine as PCM samples: it creates a\n    loud 44-byte artifact at the start of every utterance and can make short Russian commands vanish.\n    """\n    import io\n    import wave\n    import numpy as np\n\n    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":\n        with wave.open(io.BytesIO(audio), "rb") as wf:\n            raw = wf.readframes(wf.getnframes())\n            channels = wf.getnchannels()\n        samples = np.frombuffer(raw, dtype=np.int16)\n        if channels > 1:\n            samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)\n        return samples.astype(np.float32) / 32768.0\n    return np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0\n\n\n'''
        replace_once(path, anchor, helper)
        text = path.read_text(encoding="utf-8")
    old = "audio_float = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0"
    if old in text:
        text = text.replace(old, "audio_float = _decode_segment_audio(audio)", 1)
    old2 = "samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0"
    if old2 in text:
        text = text.replace(old2, "samples = _decode_segment_audio(audio)", 1)
    # Make STT failures visible instead of silently producing no transcript frame.
    if "Whisper transcription failed:" not in text:
        needle = "            segments, info = await asyncio.to_thread(\n                self._model.transcribe, audio_float,\n"
        replacement = "            try:\n                segments, info = await asyncio.to_thread(\n                    self._model.transcribe, audio_float,\n"
        if needle in text:
            text = text.replace(needle, replacement, 1)
            marker = "                hotwords=hot,\n            )\n"
            repl = "                    hotwords=hot,\n                )\n            except Exception as e:  # noqa: BLE001\n                logger.exception(f\"Whisper transcription failed: {type(e).__name__}: {e}\")\n                await self.stop_processing_metrics()\n                return\n"
            text = text.replace(marker, repl, 1)
    path.write_text(text, encoding="utf-8")


def patch_agent() -> None:
    path = SRC / "brain" / "agent.py"
    text = path.read_text(encoding="utf-8")
    old_affirm = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new_affirm = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждаю|разрешаю|"\n    r"делай|выполняй|отправляй|продолжай|можно|давай|верно|правильно|согласен|согласна|"\n    r"yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    if old_affirm in text:
        text = text.replace(old_affirm, new_affirm, 1)
    elif "r\"^\\s*(да|ага|угу" not in text:
        raise RuntimeError("agent.py affirmation anchor not found")

    # Russian instant acknowledgements and tool progress. These are spoken directly, so translating
    # only the final LLM answer is insufficient.
    start = text.find("_TOOL_PROGRESS = {")
    end = text.find("\n}\n\n# Generic instant acknowledgements", start)
    if start >= 0 and end > start:
        block = '''_TOOL_PROGRESS = {\n    "delegate_to_fleet": "Сейчас, сэр — передаю задачу команде",\n    "search_vault": "Проверяю вашу память",\n    "read_vault_note": "Читаю заметку",\n    "write_vault": "Сохраняю это в памяти",\n    "web_search": "Ищу это в интернете",\n    "scrape_url": "Открываю страницу",\n    "browse_web": "Открываю браузер",\n    "check_telegram": "Проверяю Telegram",\n    "read_chat": "Читаю чат",\n    "send_telegram": "Отправляю сообщение",\n    "telegram_music": "Ищу это в плейлисте",\n    "play_in_music_room": "Включаю музыку",\n    "stop_music_room": "Останавливаю музыку",\n    "play_music": "Ищу композицию",\n    "stop_music": "Останавливаю музыку",\n    "open_url": "Открываю это",\n    "open_app": "Открываю приложение",\n    "file_op": "Работаю с файлами",\n    "process_op": "Работаю с процессом",\n    "run_powershell": "Выполняю команду",\n    "browser": "Работаю в браузере",\n    "run_protocol": "Запускаю протокол",\n    "set_reminder": "Ставлю напоминание",\n    "send_push": "Отправляю уведомление",\n    "get_time": "Уточняю время",\n    "weather": "Проверяю погоду",\n    "list_events": "Проверяю календарь",\n    "create_event": "Добавляю событие в календарь",\n    "read_email": "Проверяю почту",\n    "send_email": "Отправляю письмо",\n    "remember": "Запоминаю",\n    "recall": "Вспоминаю",\n    "ha_state": "Проверяю устройство",\n    "ha_call": "Выполняю команду устройства",\n    "computer_use": "Смотрю на экран и выполняю задачу",\n}'''
        text = text[:start] + block + text[end + 2:]

    text = text.replace(
        '_WORK_ACKS = ("Right away, sir.", "On it, sir.", "Of course, sir.", "Let me take care of that, sir.",\n              "Consider it done, sir.")',
        '_WORK_ACKS = ("Сейчас, сэр.", "Выполняю, сэр.", "Разумеется, сэр.", "Занимаюсь этим, сэр.")',
        1,
    )
    text = text.replace(
        '_CHAT_ACKS = ("Yes, sir.", "Certainly, sir.", "Of course, sir.", "One moment, sir.")',
        '_CHAT_ACKS = ("Да, сэр.", "Разумеется, сэр.", "Конечно, сэр.", "Секунду, сэр.")',
        1,
    )

    helper = '''\n    async def _execute_pending_confirmation(self) -> str | None:\n        """Run exactly the previously held call; never send the owner's 'да' back to the LLM."""\n        pending = self._pending_confirm\n        if not pending or not self._confirm_granted:\n            return None\n        name = str(pending.get("name") or "")\n        args = pending.get("args") if isinstance(pending.get("args"), dict) else {}\n        self._pending_confirm = None\n        self._confirm_granted = False\n        out = await self._run_one_tool(name, args, None)\n        result = str(out.get("result") or "").strip()\n        if out.get("ok"):\n            return "Готово, сэр. " + result\n        return "Не удалось выполнить действие, сэр. " + result\n\n'''
    if "async def _execute_pending_confirmation" not in text:
        anchor = "    def _refuse_catastrophic(self, user_text: str) -> str:\n"
        if anchor not in text:
            raise RuntimeError("agent.py confirmation helper anchor not found")
        text = text.replace(anchor, helper + anchor, 1)

    normal = '''        self._begin_turn(user_text)\n        if _catastrophic(user_text):'''
    normal_new = '''        self._begin_turn(user_text)\n        if _is_affirmation(user_text) and self._confirm_granted:\n            confirmed = await self._execute_pending_confirmation()\n            if confirmed is not None:\n                self._history.append({"role": "user", "content": user_text})\n                self._history.append({"role": "assistant", "content": confirmed})\n                self._trim()\n                return confirmed\n        if _catastrophic(user_text):'''
    if normal in text and normal_new not in text:
        text = text.replace(normal, normal_new, 1)

    stream = '''        self._begin_turn(user_text)\n        if _catastrophic(user_text):'''
    stream_new = '''        self._begin_turn(user_text)\n        if _is_affirmation(user_text) and self._confirm_granted:\n            confirmed = await self._execute_pending_confirmation()\n            if confirmed is not None:\n                self._history.append({"role": "user", "content": user_text})\n                self._history.append({"role": "assistant", "content": confirmed})\n                self._trim()\n                self._stream_done = True\n                yield confirmed\n                return\n        if _catastrophic(user_text):'''
    # The normal replacement consumes the first occurrence; replace the next occurrence in the stream body.
    if stream in text and stream_new not in text:
        text = text.replace(stream, stream_new, 1)

    # Update the remaining common English fallback phrases that can reach TTS.
    replacements = {
        "Sorry sir, I didn't catch that — could you say it again?": "Сэр, я не расслышал. Повторите, пожалуйста.",
        "I've done what I can on that, sir.": "Я сделал всё, что смог, сэр.",
        "Here's what I found, sir.": "Вот что я нашёл, сэр.",
        "On it": "Выполняю",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    path.write_text(text, encoding="utf-8")


def patch_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        print(".env not found: source defaults will be used; add your OpenRouter key manually if needed")
        return
    text = path.read_text(encoding="utf-8")
    # Reuse an existing unprefixed OpenRouter key if the project previously stored it that way.
    m = re.search(r"^\s*OPENROUTER_API_KEY\s*=\s*(.+?)\s*$", text, re.M)
    key = m.group(1).strip() if m else None
    def setv(name: str, value: str) -> None:
        nonlocal text
        rx = re.compile(rf"^\s*{re.escape(name)}\s*=.*$", re.M)
        line = f"{name}={value}"
        if rx.search(text):
            text = rx.sub(line, text, count=1)
        else:
            text += ("\n" if not text.endswith("\n") else "") + line + "\n"
    if key and key not in ("", '""', "''"):
        setv("JARVIS_OPENROUTER_API_KEY", key)
    setv("JARVIS_REPLY_LANGUAGE", "Russian")
    setv("JARVIS_STT_PROVIDER", "whisper")
    setv("JARVIS_WHISPER_LANGUAGE", "ru")
    setv("JARVIS_PIPER_VOICE", "ru_RU-ruslan-medium")
    setv("JARVIS_WAKE_WORD_ENABLED", "false")
    setv("JARVIS_VAD_CONFIDENCE", "0.50")
    setv("JARVIS_VAD_MIN_VOLUME", "0.05")
    setv("JARVIS_VAD_STOP_SECS", "0.45")
    setv("JARVIS_COMPUTER_VISION_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")
    setv("JARVIS_COMPUTER_MAX_STEPS", "8")
    setv("JARVIS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # If an OpenRouter key exists, make the general brain use the same OpenAI-compatible endpoint.
    if key or re.search(r"^\s*JARVIS_OPENROUTER_API_KEY\s*=\s*\S+", text, re.M):
        m2 = re.search(r"^\s*JARVIS_OPENROUTER_API_KEY\s*=\s*(\S+)\s*$", text, re.M)
        if m2:
            setv("JARVIS_FREELLMAPI_BASE_URL", "https://openrouter.ai/api/v1")
            setv("JARVIS_FREELLMAPI_API_KEY", m2.group(1))
            setv("JARVIS_LLM_PRIMARY_MODEL", "qwen/qwen3-30b-a3b-instruct-2507")
            setv("JARVIS_LLM_FALLBACK_MODELS", "qwen/qwen3-30b-a3b-instruct-2507")
    path.write_text(text, encoding="utf-8")


def validate() -> None:
    files = [SRC / "config.py", SRC / "edge" / "stt.py", SRC / "brain" / "agent.py", SRC / "brain" / "tools" / "computer_use.py", SRC / "brain" / "intent_router.py", SRC / "brain" / "tools" / "__init__.py"]
    for p in files:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    print("AST validation: OK")


def main() -> None:
    patch_stt()
    patch_agent()
    patch_env()
    validate()
    print("JARVIS local rebuild v2 applied.")
    print("Next: uv run pytest -q")


if __name__ == "__main__":
    main()
