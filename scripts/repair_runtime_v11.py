from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


CATASTROPHIC_BLOCK = '''# Catastrophic system-destruction commands are refused before any model/tool call.
_CATASTROPHIC_RE = re.compile(
    r"(?:\\b(?:delete|remove|wipe|erase|destroy|format|nuke|del|rm)\\b[^.?!]*\\b(?:"
    r"system32|c:\\\\?\\s*windows|windows\\s+(?:folder|directory)|system\\s+drive|c[:\\s]+drive|"
    r"boot\\s+(?:partition|sector)|registry|program\\s+files|"
    r"everything\\s+(?:on|in)\\s+(?:my|the)\\s+(?:pc|computer|laptop|c\\s*drive|system|hard\\s*drive))\\b)"
    r"|\\brm\\s+-rf\\s+/(?:\\s|$|\\*)|\\bformat\\s+c:|\\bdel\\s+/[fsq]\\b[^.?!]*\\bc:\\\\?\\s*windows",
    re.IGNORECASE,
)
_CATASTROPHIC_REFUSAL = (
    "Нет, сэр. Я не буду стирать систему: это необратимо и уничтожит данные. "
    "Если вы имели в виду конкретный файл или папку, укажите их точно."
)


def _catastrophic(user_text: str) -> bool:
    return bool(_CATASTROPHIC_RE.search(user_text or ""))


'''

AFFIRM_BLOCK = '''# Russian and English confirmations. A confirmation executes the exact pending tool call once.
_AFFIRM_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"
    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that's right|correct|fine|"
    r"absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|"
    r"подтверждай|разрешаю|разрешено|делай|делайте|выполняй|выполняйте|выполни|выполнить|"
    r"запускай|запускайте|устанавливай|устанавливайте|установи|установить|продолжай|продолжайте|"
    r"можно|добро|верно|точно|давай|давай делай)[\\s,.!?;:]*$",
    re.IGNORECASE,
)


def _is_affirmation(text: str) -> bool:
    t = re.sub(r"[\\s,.!?;:]+", " ", (text or "").strip().lower()).strip()
    return bool(_AFFIRM_RE.fullmatch(t))

'''


def patch_catastrophic(s: str) -> str:
    if "def _catastrophic(user_text: str) -> bool:" in s:
        return s
    anchor = "# Background-work intent (Phase 4.1 / Autonomy):"
    if anchor not in s:
        raise RuntimeError("cannot restore _catastrophic: background-work anchor missing")
    return s.replace(anchor, CATASTROPHIC_BLOCK + anchor, 1)


def patch_affirmation(s: str) -> str:
    """Replace the entire affirmation section without depending on its old comment text."""
    marker = "def _is_affirmation(text: str) -> bool:"
    pos = s.find(marker)
    if pos < 0:
        raise RuntimeError("cannot repair affirmation helper: function not found")

    # Find the beginning of the affirmation section. Prefer the immediately preceding
    # _AFFIRM_RE assignment; fall back to the nearest top-level comment/blank block.
    regex_pos = s.rfind("_AFFIRM_RE = re.compile(", 0, pos)
    if regex_pos < 0:
        # If the regex was lost too, start at the closest top-level comment before the function.
        line_start = s.rfind("\n", 0, pos) + 1
        section_start = s.rfind("\n\n", 0, line_start) + 2
    else:
        section_start = s.rfind("\n", 0, regex_pos) + 1
        # Include a preceding comment line when it is directly attached to the section.
        comment_start = s.rfind("\n", 0, section_start - 1) + 1
        candidate = s[comment_start:section_start]
        if candidate.lstrip().startswith("#"):
            section_start = comment_start

    # Find the next top-level definition after _is_affirmation.
    after = s.find("\n\ndef ", pos)
    if after < 0:
        # There is normally a top-level section after this helper; if not, replace to EOF.
        section_end = len(s)
    else:
        section_end = after + 2

    return s[:section_start] + AFFIRM_BLOCK + s[section_end:]


def patch_spoken_english(s: str) -> str:
    replacements = {
        "Right away, sir — putting that to the team lead": "Сделаю, сэр — передаю задачу",
        "Checking your vault": "Проверяю хранилище",
        "Reading that note": "Читаю заметку",
        "Saving that to your vault": "Сохраняю в хранилище",
        "Looking that up": "Проверяю информацию",
        "Opening the page": "Открываю страницу",
        "Opening a browser": "Открываю браузер",
        "Checking your Telegram": "Проверяю Telegram",
        "Reading that chat": "Читаю чат",
        "Sending that": "Отправляю",
        "Pulling that from your playlist": "Ищу в вашем списке",
        "Cueing it up in your music room": "Запускаю музыку",
        "Leaving the music room": "Останавливаю музыку",
        "Finding that song": "Ищу композицию",
        "Stopping the music": "Останавливаю музыку",
        "Working on your files": "Работаю с файлами",
        "Running that": "Выполняю",
        "In the browser": "Работаю в браузере",
        "Authorizing the protocol": "Авторизую протокол",
        "Setting that reminder": "Устанавливаю напоминание",
        "Pinging your phone": "Отправляю уведомление",
        "Getting the time": "Уточняю время",
        "Checking the weather": "Проверяю погоду",
        "Checking your calendar": "Проверяю календарь",
        "Adding that to your calendar": "Добавляю в календарь",
        "Checking your email": "Проверяю почту",
        "Sending that email": "Отправляю письмо",
        "Noting that down": "Запоминаю",
        "Let me recall": "Вспоминаю",
        "Right away, sir.": "Сделаю, сэр.",
        "On it, sir.": "Занимаюсь этим, сэр.",
        "Of course, sir.": "Конечно, сэр.",
        "Let me take care of that, sir.": "Сейчас займусь этим, сэр.",
        "Consider it done, sir.": "Будет сделано, сэр.",
        "Yes, sir.": "Да, сэр.",
        "Certainly, sir.": "Разумеется, сэр.",
        "One moment, sir.": "Одну секунду, сэр.",
        '"On it"': '"Занимаюсь этим"',
        '"Opening that"': '"Открываю"',
        '"On it"': '"Занимаюсь этим"',
    }
    for old, new in sorted(replacements.items(), key=lambda kv: len(kv[0]), reverse=True):
        s = s.replace(old, new)

    s = s.replace(
        'I wasn\'t able to pull that up just now, sir — let me try again in a moment rather than guess.',
        "Не удалось получить эти данные, сэр. Я не буду гадать и попробую ещё раз.",
    )
    s = s.replace(
        "This request has MORE THAN ONE part. Complete EVERY part — use the right tool for each, one after another — and do not give your final reply until all parts are done or you've said which part you can't do and why.",
        "В запросе несколько частей. Выполни каждую часть подходящим инструментом. Не сообщай о завершении, пока все части не выполнены.",
    )
    s = s.replace('    "define_word", "wiki_lookup", "news_brief",\n', '    "define_word", "wiki_lookup",\n')
    return s


def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)
    s = patch_catastrophic(s)
    s = patch_affirmation(s)
    s = patch_spoken_english(s)
    write(p, s)


def patch_tests() -> None:
    p = "tests/test_runtime_v8.py"
    s = read(p)
    extra = '''\n\ndef test_catastrophic_guard_exists_and_is_narrow():\n    from jarvis.brain.agent import _catastrophic\n    assert callable(_catastrophic)\n    assert _catastrophic("удали всё с диска C")\n    assert not _catastrophic("удали файл report.txt")\n\n\ndef test_spoken_ack_sets_are_not_english():\n    from jarvis.brain.agent import _WORK_ACKS, _CHAT_ACKS, _TOOL_PROGRESS\n    spoken = list(_WORK_ACKS) + list(_CHAT_ACKS) + list(_TOOL_PROGRESS.values())\n    forbidden = ("Right away", "On it", "Of course", "Yes, sir", "Certainly", "One moment")\n    assert not any(any(x.lower() in phrase.lower() for x in forbidden) for phrase in spoken)\n'''
    if "test_catastrophic_guard_exists_and_is_narrow" not in s:
        s += extra
    write(p, s)


def main() -> None:
    patch_agent()
    patch_tests()
    print("runtime v11 repair applied")


if __name__ == "__main__":
    main()
