"""Safe runtime consistency repair.

The old version performed structural regex slicing in agent.py. That could delete unrelated helpers.
This version only performs exact, idempotent replacements and validates invariants. It must be safe to
run repeatedly.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write_if_changed(rel: str, text: str) -> bool:
    p = ROOT / rel
    old = p.read_text(encoding="utf-8")
    if old == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True


def repair_agent() -> bool:
    rel = "src/jarvis/brain/agent.py"
    s = read(rel)
    original = s

    old = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new = '''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|"\n    r"подтверждаю|подтверждено|разрешаю|разрешено|делай|делайте|выполняй|выполняйте|"\n    r"выполни|выполнить|запускай|запускайте|устанавливай|устанавливайте|установи|"\n    r"установить|продолжай|продолжайте|можно|добро|верно|точно|давай|давай делай)\\b",\n    re.IGNORECASE,\n)'''
    if old in s:
        s = s.replace(old, new)

    if "_PURE_CHAT_RE = re.compile(" not in s:
        marker = "def _is_pure_chat(text: str) -> bool:"
        pos = s.find(marker)
        if pos < 0:
            raise RuntimeError("agent.py is missing _PURE_CHAT_RE and _is_pure_chat")
        block = '''_PURE_CHAT_RE = re.compile(\n    r"^\\s*(привет|здравствуй|здрасьте|доброе утро|добрый день|добрый вечер|спасибо|"\n    r"пожалуйста|класс|отлично|понял|понятно|хорошо|ага|угу|да|нет|почему|зачем|"\n    r"hi|hey+|hello|thanks|thank you|good job|nice|great|cool|got it|okay|ok)"\n    r"[\\s,.!?]*(джарвис|jarvis|сэр|sir)?[\\s,.!?]*$",\n    re.IGNORECASE,\n)\n\n\n'''
        s = s[:pos] + block + s[pos:]

    replacements = {
        '"Right away, sir.",': '"Сделаю, сэр.",',
        '"On it, sir.",': '"Занимаюсь этим, сэр.",',
        '"Of course, sir.",': '"Конечно, сэр.",',
        '"Let me take care of that, sir.",': '"Сейчас займусь этим, сэр.",',
        '"Consider it done, sir.",': '"Будет сделано, сэр.",',
        '"Yes, sir.",': '"Да, сэр.",',
        '"Certainly, sir.",': '"Разумеется, сэр.",',
        '"One moment, sir.",': '"Одну секунду, сэр.",',
        '"Right away, sir — putting that to the team lead"': '"Сделаю, сэр — передаю задачу"',
        '"Checking your vault"': '"Проверяю хранилище"',
        '"Reading that note"': '"Читаю заметку"',
        '"Saving that to your vault"': '"Сохраняю в хранилище"',
        '"Looking that up"': '"Проверяю информацию"',
        '"Opening the page"': '"Открываю страницу"',
        '"Opening a browser"': '"Открываю браузер"',
        '"Checking your Telegram"': '"Проверяю Telegram"',
        '"Reading that chat"': '"Читаю чат"',
        '"Sending that"': '"Отправляю"',
        '"Working on your files"': '"Работаю с файлами"',
        '"Running that"': '"Выполняю"',
        '"In the browser"': '"Работаю в браузере"',
        '"Setting that reminder"': '"Устанавливаю напоминание"',
        '"Pinging your phone"': '"Отправляю уведомление"',
        '"Getting the time"': '"Уточняю время"',
        '"Checking the weather"': '"Проверяю погоду"',
        '"Checking your calendar"': '"Проверяю календарь"',
        '"Adding that to your calendar"': '"Добавляю в календарь"',
        '"Checking your email"': '"Проверяю почту"',
        '"Sending that email"': '"Отправляю письмо"',
        '"Noting that down"': '"Запоминаю"',
        '"Let me recall"': '"Вспоминаю"',
        '"I wasn\'t able to pull that up just now, sir — let me try again in a moment rather than guess."': '"Не удалось получить эти данные, сэр. Я не буду гадать и попробую ещё раз."',
        '"Sorry sir, I didn\'t catch that — could you say it again?"': '"Не расслышал, сэр. Повторите, пожалуйста."',
        '"I\'ve done what I can on that, sir."': '"Я сделал всё, что смог, сэр."',
        '"Here\'s what I found, sir."': '"Вот что я нашёл, сэр."',
    }
    for old, new in replacements.items():
        s = s.replace(old, new)

    ast.parse(s, filename=rel)
    return write_if_changed(rel, s) if s != original else False


def repair_config() -> bool:
    rel = "src/jarvis/config.py"
    s = read(rel)
    original = s
    for old, new in (
        ('wake_word_threshold: float = 0.5', 'wake_word_threshold: float = 0.32'),
        ('hot_mic_after_wake: bool = False', 'hot_mic_after_wake: bool = True'),
        ('reply_language: str = "English"', 'reply_language: str = "Russian"'),
        ('understood_languages: str = "English"', 'understood_languages: str = "Russian,English"'),
    ):
        s = s.replace(old, new)
    return write_if_changed(rel, s) if s != original else False


def repair_wake() -> bool:
    rel = "src/jarvis/edge/wake_word.py"
    s = read(rel)
    original = s
    s = s.replace('threshold: float = 0.5,', 'threshold: float = 0.32,')
    return write_if_changed(rel, s) if s != original else False


def validate() -> None:
    checks = {
        "src/jarvis/brain/agent.py": ("_PURE_CHAT_RE = re.compile(", "def _is_pure_chat(", "def _is_affirmation(", "def _execute_calls("),
        "src/jarvis/brain/intent_router.py": ("def forced_tools(",),
    }
    for rel, needles in checks.items():
        s = read(rel)
        for needle in needles:
            if needle not in s:
                raise RuntimeError(f"runtime invariant missing: {rel}: {needle}")
        ast.parse(s, filename=rel)


def main() -> None:
    changed = repair_agent()
    changed = repair_config() or changed
    changed = repair_wake() or changed
    validate()
    state = "files updated" if changed else "already clean"
    print(f"runtime repair: OK (idempotent, non-destructive); {state}")


if __name__ == "__main__":
    main()
