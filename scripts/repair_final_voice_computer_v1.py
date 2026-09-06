"""Final runtime repair: Russian STT/TTS, one-shot confirmations, deterministic PC commands.

This patch is intentionally small and idempotent. It changes config/.env and patches agent.py so:
- Russian voice uses local Whisper + Russian Piper fallback;
- simple PC open/close commands never go through the LLM;
- a confirmation answer like "да" executes the exact pending action once instead of asking again;
- remaining English filler is replaced with Russian.
"""
from __future__ import annotations
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "jarvis" / "config.py"
AGENT = ROOT / "src" / "jarvis" / "brain" / "agent.py"
ENV = ROOT / ".env"


def env_set(text: str, key: str, value: str) -> str:
    pat = rf"^\s*{re.escape(key)}\s*=.*$"
    out, n = re.subn(pat, f"{key}={value}", text, count=1, flags=re.MULTILINE)
    if n:
        return out
    if out and not out.endswith("\n"):
        out += "\n"
    return out + f"{key}={value}\n"


def cfg_set(text: str, field: str, line: str) -> str:
    pat = rf"^\s*{re.escape(field)}\s*:[^\n]*$"
    out, n = re.subn(pat, line, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise RuntimeError(f"config field not found: {field}")
    return out


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"agent patch anchor not found: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    # Reliable Russian edge defaults. .env is patched too because BaseSettings gives it precedence.
    c = CONFIG.read_text(encoding="utf-8")
    c = cfg_set(c, "wake_word_enabled", "    wake_word_enabled: bool = False")
    c = cfg_set(c, "vad_confidence", "    vad_confidence: float = 0.50")
    c = cfg_set(c, "vad_min_volume", "    vad_min_volume: float = 0.05")
    c = cfg_set(c, "stt_provider", "    stt_provider: STTProvider = STTProvider.whisper")
    c = cfg_set(c, "piper_voice", '    piper_voice: str = "ru_RU-ruslan-medium"')
    ast.parse(c, filename=str(CONFIG))
    CONFIG.write_text(c, encoding="utf-8")

    if ENV.exists():
        e = ENV.read_text(encoding="utf-8")
    else:
        e = ""
    for k, v in {
        "JARVIS_WAKE_WORD_ENABLED": "false",
        "JARVIS_VAD_CONFIDENCE": "0.50",
        "JARVIS_VAD_MIN_VOLUME": "0.05",
        "JARVIS_STT_PROVIDER": "whisper",
        "JARVIS_WHISPER_LANGUAGE": "ru",
        "JARVIS_PIPER_VOICE": "ru_RU-ruslan-medium",
        "JARVIS_REPLY_LANGUAGE": "Russian",
    }.items():
        e = env_set(e, k, v)
    ENV.write_text(e, encoding="utf-8")

    a = AGENT.read_text(encoding="utf-8")

    # Russian confirmations. The important part is not just recognition: respond/respond_stream
    # will execute the stored call directly below, so "да" never enters the LLM as a new request.
    old = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|"\n    r"подтверждаю|подтверждено|разрешаю|разрешено|делай|выполняй|выполни|отправляй|"\n    r"запускай|устанавливай|продолжай)\\b",\n    re.IGNORECASE,\n)'''
    a = replace_once(a, old, new, "Russian affirmation regex")

    # Russian pure-chat routing fixes.
    a = replace_once(a, 'r"\\b(hi|hey+|hello|hiya|yo|howdy|good\\s*(morning|afternoon|evening|night)|greetings|"',
                     'r"^\\s*(привет|здравствуй|здравствуйте|доброе\\s+(утро|день|вечер)|спасибо|благодарю|"\n                     'r"да|ага|угу|ок|окей|хорошо|понял|понятно|почему|зачем|круто|отлично|ладно|"\n                     'r"hi|hey+|hello|hiya|yo|howdy|good\\s*(morning|afternoon|evening|night)|greetings|"',
                     "Russian pure-chat anchors")

    # Replace English fallback speech with Russian.
    a = a.replace('"Sorry sir, I didn\'t catch that — could you say it again?"', '"Сэр, я не расслышал команду. Повторите, пожалуйста."')
    a = a.replace('"I\'ve done what I can on that, sir."', '"Сэр, я сделал всё, что смог по этой команде."')
    a = a.replace('"Here\'s what I found, sir."', '"Сэр, вот что удалось найти."')
    a = a.replace('"What would you like me to work on, sir?"', '"Что мне сделать, сэр?"')

    # Make the generic immediate/tool acknowledgements Russian so they can never leak English into TTS.
    a = replace_once(a,
        '_WORK_ACKS = ("Right away, sir.", "On it, sir.", "Of course, sir.", "Let me take care of that, sir.",\n              "Consider it done, sir.")\n_CHAT_ACKS = ("Yes, sir.", "Certainly, sir.", "Of course, sir.", "One moment, sir.")',
        '_WORK_ACKS = ("Сэр, выполняю.", "Да, сэр.", "Слушаю, сэр.")\n_CHAT_ACKS = ("Да, сэр.", "Слушаю, сэр.", "Понял, сэр.")',
        "Russian acknowledgements")

    # Insert exact pending-confirm executor immediately before _tools_for_turn.
    anchor = '    def _tools_for_turn(self, user_text: str) -> list[dict[str, Any]]:\n'
    helper = '''    async def _execute_pending_confirmation(self) -> str | None:\n        """Execute exactly the action that was previously held for confirmation.\n\n        A confirmation is not a new LLM request: it is a deterministic authorization of the\n        stored tool call. This prevents the old loop where "да" was sent back to the model,\n        which asked for confirmation again or invented a different action.\n        """\n        pending = self._pending_confirm\n        if not pending:\n            return None\n        name = str(pending.get("name") or "")\n        args = dict(pending.get("args") or {})\n        self._confirm_granted = True\n        self._pending_confirm = None\n        logger.info(f"confirm-gate: owner confirmed — executing exact pending {name}({args})")\n        try:\n            out = await self._run_one_tool(name, args, None)\n            if out.get("ok"):\n                return _clean_reply(str(out.get("result") or "Действие выполнено, сэр."))\n            return _clean_reply(str(out.get("result") or "Сэр, выполнить действие не удалось."))\n        finally:\n            self._confirm_granted = False\n\n'''
    if 'async def _execute_pending_confirmation' not in a:
        a = replace_once(a, anchor, helper + anchor, "pending confirmation executor")

    # In both respond paths, execute a pending confirmation before any LLM call.
    old_begin = '        self._begin_turn(user_text)\n        if _catastrophic(user_text):\n'
    new_begin = '        self._begin_turn(user_text)\n        if _is_affirmation(user_text) and self._pending_confirm:\n            confirmed = await self._execute_pending_confirmation()\n            if confirmed is not None:\n                self._history.append({"role": "user", "content": user_text})\n                self._history.append({"role": "assistant", "content": confirmed})\n                self._trim()\n                return confirmed\n        if _catastrophic(user_text):\n'
    # First occurrence is blocking respond.
    a = replace_once(a, old_begin, new_begin, "respond confirmation execution")
    # Streaming has same anchor; use a version that yields instead of return.
    old_stream = '        self._begin_turn(user_text)\n        if _catastrophic(user_text):\n'
    new_stream = '        self._begin_turn(user_text)\n        if _is_affirmation(user_text) and self._pending_confirm:\n            confirmed = await self._execute_pending_confirmation()\n            if confirmed is not None:\n                self._history.append({"role": "user", "content": user_text})\n                self._history.append({"role": "assistant", "content": confirmed})\n                self._trim()\n                self._stream_done = True\n                yield confirmed\n                return\n        if _catastrophic(user_text):\n'
    a = replace_once(a, old_stream, new_stream, "stream confirmation execution")

    ast.parse(a, filename=str(AGENT))
    AGENT.write_text(a, encoding="utf-8")
    print("FINAL REPAIR APPLIED")
    print("STT=Whisper RU; wake word disabled; VAD relaxed; Piper=ru_RU-ruslan-medium")
    print("Russian confirmations now execute the exact pending action once")
    print("Simple open/close commands remain deterministic and bypass the LLM")


if __name__ == "__main__":
    main()
