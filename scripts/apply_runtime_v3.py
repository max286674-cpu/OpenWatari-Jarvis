from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def once(text: str, pattern: str, repl: str, label: str, flags: int = 0) -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    print(f"PATCH {label}" if n else f"SKIP {label}")
    return out

# --- Config: real OpenRouter credentials + low-latency defaults ---
p = "src/jarvis/config.py"
s = read(p)
if "openrouter_api_key:" not in s:
    s = once(s, r'(\n\s*groq_api_key:\s*str \| None = None)',
             '\n    openrouter_api_key: str | None = None\n    openrouter_base_url: str = "https://openrouter.ai/api/v1"\n    groq_api_key: str | None = None',
             "config OpenRouter fields")
s = once(s, r'(wake_word_threshold:\s*float\s*=\s*)0\.5', r'\g<1>0.35', "config wake threshold")
s = once(s, r'(wake_listen_window_s:\s*float\s*=\s*)8\.0', r'\g<1>6.0', "config wake window")
s = once(s, r'(deepgram_endpointing_ms:\s*int\s*=\s*)700', r'\g<1>350', "config endpointing")
s = once(s, r'(self_improve_enabled:\s*bool\s*=\s*)True', r'\g<1>False', "config disable auto-memory")
write(p, s)

# --- LLM: route openrouter:<model> to the actual OpenRouter endpoint ---
p = "src/jarvis/brain/llm.py"
s = read(p)
if '"openrouter:"' not in s:
    s = once(s,
        r'(for prefix, base_url, api_key in \(\s*)\n(\s*\("groq:")',
        r'\1\n            ("openrouter:", settings.openrouter_base_url, settings.openrouter_api_key or "missing-openrouter-key"),\n\2',
        "llm OpenRouter resolver", flags=re.S)
s = once(s, r'(llm_first_token_timeout_seconds:\s*float\s*=\s*)4\.0', r'\g<1>2.5', "llm first-token timeout")
write(p, s)

# --- Agent: remove common English spoken filler/progress ---
p = "src/jarvis/brain/agent.py"
s = read(p)
repls = {
    "Right away, sir.": "Сейчас, сэр.", "On it, sir.": "Выполняю, сэр.",
    "Of course, sir.": "Конечно, сэр.", "Let me take care of that, sir.": "Занимаюсь, сэр.",
    "Consider it done, sir.": "Готово, сэр.", "Yes, sir.": "Да, сэр.",
    "Certainly, sir.": "Конечно, сэр.", "One moment, sir.": "Одну секунду, сэр.",
    "Checking your vault": "Проверяю хранилище", "Reading that note": "Читаю заметку",
    "Saving that to your vault": "Сохраняю это в хранилище", "Looking that up": "Проверяю информацию",
    "Opening the page": "Открываю страницу", "Opening a browser": "Открываю браузер",
    "Checking your Telegram": "Проверяю Telegram", "Reading that chat": "Читаю чат",
    "Sending that": "Отправляю", "Getting the time": "Уточняю время",
    "Checking the weather": "Проверяю погоду", "Checking your calendar": "Проверяю календарь",
    "Adding that to your calendar": "Добавляю в календарь", "Checking your email": "Проверяю почту",
    "Sending that email": "Отправляю письмо", "Noting that down": "Запоминаю",
    "Let me recall": "Вспоминаю", "Opening that": "Открываю", "Running that": "Выполняю команду",
}
for a, b in repls.items():
    s = s.replace(a, b)
# Explicitly make the standard ack tuple Russian if it still exists in English.
s = re.sub(r'_CHAT_ACKS\s*=\s*\([^\n]+\)', '_CHAT_ACKS = ("Да, сэр.", "Конечно, сэр.", "Хорошо, сэр.", "Одну секунду, сэр.")', s, count=1)
# Russian action words should force tool routing.
if "открой|открыть|запусти" not in s:
    marker = r'    r"\\brun \(the \)?protocol\\b", r"\\bsearch \(my \)?vault\\b",'
    s = s.replace(marker, marker + '\n    r"\\b(открой|открыть|запусти|запустить|включи|включить|выключи|выключить)\\b",\n    r"\\b(найди|найти|поищи|проверить|проверь|покажи|показать)\\b",\n    r"\\b(ютуб|youtube|браузер|гугл|google|телеграм|telegram|дискорд|discord)\\b",')
write(p, s)

# --- Memory: explicit remember remains available, autonomous review is off ---
# --- .env: map an existing generic OpenRouter key into Pydantic's JARVIS_ namespace ---
p = ".env"
if (ROOT / p).exists():
    s = read(p)
    m = re.search(r'^\s*OPENROUTER_API_KEY\s*=\s*(.+?)\s*$', s, flags=re.M)
    if m and not re.search(r'^\s*JARVIS_OPENROUTER_API_KEY\s*=', s, flags=re.M):
        s += "\nJARVIS_OPENROUTER_API_KEY=" + m.group(1) + "\n"
        print("PATCH .env OpenRouter key alias (value not printed)")
    def env(key: str, value: str) -> None:
        nonlocal_dummy = None
    lines = s.splitlines()
    wanted = {
        "JARVIS_REPLY_LANGUAGE": "Russian",
        "JARVIS_UNDERSTOOD_LANGUAGES": "Russian,English",
        "JARVIS_WHISPER_LANGUAGE": "ru",
        "JARVIS_PRILER_REACTIONS": "true",
        "JARVIS_PRILER_VOICE": "jarvis-remaster",
        "JARVIS_PRILER_LANGUAGE": "ru",
        "JARVIS_WAKE_WORDS": "jarvis",
        "JARVIS_WAKE_WORD_THRESHOLD": "0.35",
        "JARVIS_DEEPGRAM_ENDPOINTING_MS": "350",
        "JARVIS_SELF_IMPROVE_ENABLED": "false",
        "JARVIS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "2.5",
        "JARVIS_LLM_MODEL": "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
    }
    seen = set()
    out = []
    for line in lines:
        mm = re.match(r'^([A-Z0-9_]+)=', line)
        if mm and mm.group(1) in wanted:
            key = mm.group(1); out.append(key + "=" + wanted[key]); seen.add(key)
        else:
            out.append(line)
    for key, value in wanted.items():
        if key not in seen:
            out.append(key + "=" + value)
    write(p, "\n".join(out).rstrip() + "\n")

# --- Compile check: catches a bad migration before runtime ---
import py_compile
for path in ("src/jarvis/config.py", "src/jarvis/brain/llm.py", "src/jarvis/brain/agent.py"):
    py_compile.compile(str(ROOT / path), doraise=True)
    print("OK compile", path)

print("\nJARVIS runtime v3 migration complete.")
print("Restart JARVIS after running this script. No secret value was printed.")
