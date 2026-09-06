from __future__ import annotations

"""One-shot migration to a Russian-first, fast OpenRouter runtime.

This script intentionally contains no PowerShell/Cyrillic parsing tricks. Python source is UTF-8,
so it is safe to execute from Windows PowerShell 5.1 as well as newer PowerShell versions.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {rel}")
    return p.read_text(encoding="utf-8")


def write_if_changed(rel: str, text: str) -> None:
    p = ROOT / rel
    old = p.read_text(encoding="utf-8")
    if old == text:
        print(f"UNCHANGED {rel}")
    else:
        p.write_text(text, encoding="utf-8", newline="")
        print(f"UPDATED {rel}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Patch target not found: {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------
t = read("src/jarvis/config.py")
repls = {
    'understood_languages: str = "English"': 'understood_languages: str = "Russian,English"',
    'reply_language: str = "English"': 'reply_language: str = "Russian"',
    'wake_words: str = "jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine"': 'wake_words: str = "jarvis"',
    'wake_word_threshold: float = 0.5': 'wake_word_threshold: float = 0.45',
    'wake_ack_phrase: str = "Yes, sir?|I\'m listening, sir.|Sir?|Go ahead, sir."': 'wake_ack_phrase: str = "Слушаю, сэр.|Да, сэр?|Я здесь, сэр."',
    'listening_pulse: bool = True': 'listening_pulse: bool = False',
    'deepgram_language: str = "multi"': 'deepgram_language: str = "ru"',
    'deepgram_endpointing_ms: int = 700': 'deepgram_endpointing_ms: int = 500',
    'whisper_language: str = "en"': 'whisper_language: str = "ru"',
    'piper_voice: str = "en_US-ryan-high"': 'piper_voice: str = "ru_RU-ruslan-medium"',
    'llm_fast_model: str | None = None': 'llm_fast_model: str | None = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"',
    'llm_primary_model: str = "minimax:MiniMax-Text-01"': 'llm_primary_model: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"',
}
for a, b in repls.items():
    t = t.replace(a, b)

if "openrouter_api_key:" not in t:
    anchor = '    minimax_base_url: str = "https://api.minimax.io/v1"'
    insertion = (
        anchor
        + '\n    # OpenRouter: OpenAI-compatible access to the fast multilingual voice/chat model.\n'
        + '    openrouter_api_key: str | None = None\n'
        + '    openrouter_base_url: str = "https://openrouter.ai/api/v1"'
    )
    t = replace_once(t, anchor, insertion, "OpenRouter settings in config.py")
write_if_changed("src/jarvis/config.py", t)


# ---------------------------------------------------------------------------
# llm.py — add OpenRouter provider resolver
# ---------------------------------------------------------------------------
t = read("src/jarvis/brain/llm.py")
provider_line = '            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),'
if provider_line not in t:
    anchor = '            ("minimax:", settings.minimax_base_url, settings.minimax_api_key or "missing-minimax-key"),'
    t = replace_once(t, anchor, provider_line + "\n" + anchor, "OpenRouter provider tuple in llm.py")
    t = t.replace(
        '``minimax:<model>`` hits MiniMax directly',
        '``openrouter:<model>`` hits OpenRouter directly; ``minimax:<model>`` hits MiniMax directly',
        1,
    )
write_if_changed("src/jarvis/brain/llm.py", t)


# ---------------------------------------------------------------------------
# agent.py — remove English spoken fillers and raw news direct-TTS path
# ---------------------------------------------------------------------------
t = read("src/jarvis/brain/agent.py")
spoken = {
    '"Right away, sir — putting that to the team lead"': '"Сразу займусь — передаю задачу команде"',
    '"Checking your vault"': '"Проверяю хранилище"',
    '"Reading that note"': '"Читаю заметку"',
    '"Saving that to your vault"': '"Сохраняю в хранилище"',
    '"Looking that up"': '"Проверяю информацию"',
    '"Opening the page"': '"Открываю страницу"',
    '"Opening a browser"': '"Открываю браузер"',
    '"Checking your Telegram"': '"Проверяю Telegram"',
    '"Reading that chat"': '"Читаю чат"',
    '"Sending that"': '"Отправляю"',
    '"Pulling that from your playlist"': '"Беру это из вашего плейлиста"',
    '"Cueing it up in your music room"': '"Ставлю это в музыкальной комнате"',
    '"Leaving the music room"': '"Выключаю музыку"',
    '"Finding that song"': '"Ищу эту композицию"',
    '"Stopping the music"': '"Останавливаю музыку"',
    '"Opening that"': '"Открываю"',
    '"Working on your files"': '"Работаю с файлами"',
    '"On it"': '"Занимаюсь"',
    '"Running that"': '"Выполняю команду"',
    '"In the browser"': '"Работаю в браузере"',
    '"Authorizing the protocol"': '"Запускаю протокол"',
    '"Setting that reminder"': '"Ставлю напоминание"',
    '"Pinging your phone"': '"Отправляю уведомление на телефон"',
    '"Getting the time"': '"Уточняю время"',
    '"Checking the weather"': '"Проверяю погоду"',
    '"Checking your calendar"': '"Проверяю календарь"',
    '"Adding that to your calendar"': '"Добавляю в календарь"',
    '"Checking your email"': '"Проверяю почту"',
    '"Sending that email"': '"Отправляю письмо"',
    '"Noting that down"': '"Запоминаю"',
    '"Let me recall"': '"Сейчас вспомню"',
    '"Right away, sir."': '"Сразу, сэр."',
    '"On it, sir."': '"Занимаюсь, сэр."',
    '"Of course, sir."': '"Конечно, сэр."',
    '"Let me take care of that, sir."': '"Сейчас займусь, сэр."',
    '"Consider it done, sir."': '"Считайте, что сделано, сэр."',
    '"Yes, sir."': '"Да, сэр."',
    '"Certainly, sir."': '"Разумеется, сэр."',
    '"One moment, sir."': '"Одну секунду, сэр."',
}
for a, b in spoken.items():
    t = t.replace(a, b)

# The news tool is allowed to return English. It must be re-voiced by the LLM, not dumped into TTS.
t = t.replace('"define_word", "wiki_lookup", "news_brief",', '"define_word", "wiki_lookup",', 1)
t = t.replace('"news_brief",', '', 1)

# Known catastrophic/fabrication spoken strings.
t = t.replace(
    '"I wasn\'t able to pull that up just now, sir — let me try again in a moment rather than guess."',
    '"Сейчас не удалось получить эти данные, сэр. Я не буду гадать и попробую снова."',
)
t = t.replace(
    '"No, sir — I won\'t do that. Wiping that would destroy your system and it can\'t be undone, so I\'ve refused it. If you meant a specific file or folder, tell me exactly which and I\'ll confirm first."',
    '"Нет, сэр. Я не буду этого делать: команда уничтожит систему без возможности восстановления. Если вы имели в виду конкретный файл или папку, назовите их, и я сначала запрошу подтверждение."',
)
write_if_changed("src/jarvis/brain/agent.py", t)


# ---------------------------------------------------------------------------
# Persona — hard Russian TTS contract
# ---------------------------------------------------------------------------
t = read("personality/jarvis.md")
contract = """

## Russian speech contract
- All spoken replies MUST be in Russian unless the owner explicitly asks for another language.
- Never send raw tool, browser, web, news, email, or search output directly to TTS.
- Foreign-language results MUST be translated and briefly summarized in Russian before speech.
- English text may be preserved only for proper names, URLs, model names, commands, code, or when explicitly requested.
- Never use English acknowledgement, filler, progress, or transition phrases in a Russian conversation.
"""
if "## Russian speech contract" not in t:
    t += contract
write_if_changed("personality/jarvis.md", t)


# ---------------------------------------------------------------------------
# .env.example — documentation only, no secret
# ---------------------------------------------------------------------------
t = read(".env.example")
for a, b in {
    "JARVIS_UNDERSTOOD_LANGUAGES=English": "JARVIS_UNDERSTOOD_LANGUAGES=Russian,English",
    "JARVIS_REPLY_LANGUAGE=English": "JARVIS_REPLY_LANGUAGE=Russian",
    "JARVIS_DEEPGRAM_LANGUAGE=multi": "JARVIS_DEEPGRAM_LANGUAGE=ru",
    "JARVIS_WAKE_WORDS=jarvis,alfred,robbin,assist,time to work,wake up,six-one-nine": "JARVIS_WAKE_WORDS=jarvis",
    "JARVIS_WAKE_WORD_THRESHOLD=0.5": "JARVIS_WAKE_WORD_THRESHOLD=0.45",
}.items():
    t = t.replace(a, b)
if "JARVIS_OPENROUTER_API_KEY=" not in t:
    anchor = "JARVIS_FREELLMAPI_API_KEY="
    addition = (
        anchor
        + "\n\n# ---- OpenRouter fast multilingual LLM -----------------------------------------------\n"
        + "JARVIS_OPENROUTER_API_KEY=\n"
        + "JARVIS_LLM_PRIMARY_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507\n"
        + "JARVIS_LLM_FAST_MODEL=openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    )
    if anchor in t:
        t = t.replace(anchor, addition, 1)
write_if_changed(".env.example", t)


# ---------------------------------------------------------------------------
# Local .env — preserve secrets, change only runtime switches.
# ---------------------------------------------------------------------------
env_path = ROOT / ".env"
if env_path.exists():
    t = env_path.read_text(encoding="utf-8")
    settings = {
        "JARVIS_REPLY_LANGUAGE": "Russian",
        "JARVIS_UNDERSTOOD_LANGUAGES": "Russian,English",
        "JARVIS_WHISPER_LANGUAGE": "ru",
        "JARVIS_DEEPGRAM_LANGUAGE": "ru",
        "JARVIS_DEEPGRAM_ENDPOINTING_MS": "500",
        "JARVIS_PIPER_VOICE": "ru_RU-ruslan-medium",
        "JARVIS_PRILER_REACTIONS": "true",
        "JARVIS_PRILER_VOICE": "jarvis-remaster",
        "JARVIS_PRILER_LANGUAGE": "ru",
        "JARVIS_WAKE_WORDS": "jarvis",
        "JARVIS_WAKE_WORD_THRESHOLD": "0.45",
        "JARVIS_LISTENING_PULSE": "false",
        "JARVIS_LLM_PRIMARY_MODEL": "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        "JARVIS_LLM_FAST_MODEL": "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        "JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "3.0",
    }

    for key, value in settings.items():
        pattern = rf"(?m)^{re.escape(key)}=.*$"
        line = f"{key}={value}"
        if re.search(pattern, t):
            t = re.sub(pattern, line, t, count=1)
        else:
            if not t.endswith("\n"):
                t += "\n"
            t += line + "\n"

    # If a generic OPENROUTER_API_KEY is already exported in the shell, copy it without printing it.
    generic = __import__("os").environ.get("OPENROUTER_API_KEY")
    key_pattern = r"(?m)^JARVIS_OPENROUTER_API_KEY=.*$"
    if not re.search(key_pattern, t):
        t += "JARVIS_OPENROUTER_API_KEY=" + (generic or "") + "\n"
    elif generic and re.search(r"(?m)^JARVIS_OPENROUTER_API_KEY=\s*$", t):
        t = re.sub(key_pattern, "JARVIS_OPENROUTER_API_KEY=" + generic, t, count=1)

    env_path.write_text(t, encoding="utf-8", newline="")
    print("UPDATED .env (secrets preserved; key value never printed)")
else:
    print("SKIPPED .env (file does not exist)")

print("\nRussian runtime migration completed.")
print("Model: openrouter:qwen/qwen3-30b-a3b-instruct-2507")
print("Voice fallback: ru_RU-ruslan-medium")
print("Wake: jarvis / threshold 0.45")
