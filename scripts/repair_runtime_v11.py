"""Safe runtime consistency repair.

This script is intentionally boring: restore two files from known-good repository history, then apply
small exact patches and validate Python syntax. It never slices arbitrary source sections, so running it
repeatedly cannot delete helpers such as _PURE_CHAT_RE.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CONFIG = "88d5c6d3c0a310dc74e04642142849ab630622b8"
CANONICAL_TOOLS = "f3def13a623ed737a6128c32cba0776e2b222d9f"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write_if_changed(rel: str, text: str) -> bool:
    p = ROOT / rel
    old = p.read_text(encoding="utf-8")
    if old == text:
        return False
    p.write_text(text, encoding="utf-8")
    return True


def git_file(commit: str, rel: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{rel}"], cwd=ROOT, text=True, encoding="utf-8"
        )
    except Exception as e:
        raise RuntimeError(f"cannot restore canonical {rel}: {e}") from e


def restore_canonical_files() -> bool:
    changed = False
    for rel, commit in (
        ("src/jarvis/config.py", CANONICAL_CONFIG),
        ("src/jarvis/brain/tools/__init__.py", CANONICAL_TOOLS),
    ):
        changed = write_if_changed(rel, git_file(commit, rel)) or changed
    return changed


def patch_agent() -> bool:
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
    for old, new in {
        '"Right away, sir.",': '"Сделаю, сэр.",', '"On it, sir.",': '"Занимаюсь этим, сэр.",',
        '"Of course, sir.",': '"Конечно, сэр.",', '"Let me take care of that, sir.",': '"Сейчас займусь этим, сэр.",',
        '"Consider it done, sir.",': '"Будет сделано, сэр.",', '"Yes, sir.",': '"Да, сэр.",',
        '"Certainly, sir.",': '"Разумеется, сэр.",', '"One moment, sir.",': '"Одну секунду, сэр.",',
        '"Right away, sir — putting that to the team lead"': '"Сделаю, сэр — передаю задачу"',
        '"Checking your vault"': '"Проверяю хранилище"', '"Reading that note"': '"Читаю заметку"',
        '"Saving that to your vault"': '"Сохраняю в хранилище"', '"Looking that up"': '"Проверяю информацию"',
        '"Opening the page"': '"Открываю страницу"', '"Opening a browser"': '"Открываю браузер"',
        '"Checking your Telegram"': '"Проверяю Telegram"', '"Reading that chat"': '"Читаю чат"',
        '"Sending that"': '"Отправляю"', '"Working on your files"': '"Работаю с файлами"',
        '"Running that"': '"Выполняю"', '"In the browser"': '"Работаю в браузере"',
        '"Setting that reminder"': '"Устанавливаю напоминание"', '"Pinging your phone"': '"Отправляю уведомление"',
        '"Getting the time"': '"Уточняю время"', '"Checking the weather"': '"Проверяю погоду"',
        '"Checking your calendar"': '"Проверяю календарь"', '"Adding that to your calendar"': '"Добавляю в календарь"',
        '"Checking your email"': '"Проверяю почту"', '"Sending that email"': '"Отправляю письмо"',
        '"Noting that down"': '"Запоминаю"', '"Let me recall"': '"Вспоминаю"',
        '"Sorry sir, I didn\'t catch that — could you say it again?"': '"Не расслышал, сэр. Повторите, пожалуйста."',
    }.items():
        s = s.replace(old, new)
    ast.parse(s, filename=rel)
    return write_if_changed(rel, s) if s != original else False


def patch_config() -> bool:
    rel = "src/jarvis/config.py"
    s = read(rel)
    original = s
    s = s.replace('understood_languages: str = "English"', 'understood_languages: str = "Russian,English"')
    s = s.replace('reply_language: str = "English"', 'reply_language: str = "Russian"')
    s = s.replace('wake_word_threshold: float = 0.5', 'wake_word_threshold: float = 0.32')
    s = s.replace('hot_mic_after_wake: bool = False', 'hot_mic_after_wake: bool = True')
    s = s.replace('wake_ack_phrase: str = "Yes, sir?|I\'m listening, sir.|Sir?|Go ahead, sir."', 'wake_ack_phrase: str = "Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю."')
    anchor = '    mic_gain: float = 1.0\n'
    if 'desktop_tools_enabled:' not in s:
        s = s.replace(anchor, anchor + '    desktop_tools_enabled: bool = True\n', 1)
    ast.parse(s, filename=rel)
    return write_if_changed(rel, s) if s != original else False


def patch_tools_registry() -> bool:
    rel = "src/jarvis/brain/tools/__init__.py"
    s = read(rel)
    original = s
    if '    desktop,' not in s:
        s = s.replace('    documents,\n', '    desktop,\n    documents,\n', 1)
    if 'system, desktop, browser' not in s:
        s = s.replace('system, browser,', 'system, desktop, browser,', 1)
    # Screen turns activate desktop controls as well as multimodal vision.
    if '"screen": [multimodal, desktop]' not in s:
        s = s.replace('"screen": [multimodal],', '"screen": [multimodal, desktop],', 1)
    ast.parse(s, filename=rel)
    return write_if_changed(rel, s) if s != original else False


def validate() -> None:
    checks = {
        "src/jarvis/brain/agent.py": ("_PURE_CHAT_RE = re.compile(", "def _is_pure_chat(", "def _is_affirmation(", "def _execute_calls("),
        "src/jarvis/brain/intent_router.py": ("def forced_tools(",),
        "src/jarvis/brain/tools/desktop.py": ("desktop_action", "desktop_screenshot"),
    }
    for rel, needles in checks.items():
        s = read(rel)
        for needle in needles:
            if needle not in s:
                raise RuntimeError(f"runtime invariant missing: {rel}: {needle}")
        ast.parse(s, filename=rel)


def main() -> None:
    changed = restore_canonical_files()
    changed = patch_agent() or changed
    changed = patch_config() or changed
    changed = patch_tools_registry() or changed
    validate()
    print("runtime repair: OK (canonical restore + idempotent patches)" + ("; files updated" if changed else "; already clean"))


if __name__ == "__main__":
    main()
