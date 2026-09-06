from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def patch_agent() -> None:
    p = "src/jarvis/brain/agent.py"
    s = read(p)

    if "def _catastrophic(user_text: str) -> bool:" not in s:
        anchor = "# Background-work intent (Phase 4.1 / Autonomy):"
        if anchor not in s:
            raise RuntimeError("cannot restore _catastrophic: background-work anchor missing")
        guard = '''# Catastrophic system-destruction commands are refused before any model/tool call.\n_CATASTROPHIC_RE = re.compile(\n    r"(?:\\b(?:delete|remove|wipe|erase|destroy|format|nuke|del|rm)\\b[^.?!]*\\b(?:"\n    r"system32|c:\\\\?\\s*windows|windows\\s+(?:folder|directory)|system\\s+drive|c[:\\s]+drive|"\n    r"boot\\s+(?:partition|sector)|registry|program\\s+files|"\n    r"everything\\s+(?:on|in)\\s+(?:my|the)\\s+(?:pc|computer|laptop|c\\s*drive|system|hard\\s*drive))\\b)"\n    r"|\\brm\\s+-rf\\s+/(?:\\s|$|\\*)|\\bformat\\s+c:|\\bdel\\s+/[fsq]\\b[^.?!]*\\bc:\\\\?\\s*windows",\n    re.IGNORECASE,\n)\n_CATASTROPHIC_REFUSAL = (\n    "Нет, сэр. Я не буду стирать систему: это необратимо и уничтожит данные. "\n    "Если вы имели в виду конкретный файл или папку, укажите их точно."\n)\n\n\ndef _catastrophic(user_text: str) -> bool:\n    return bool(_CATASTROPHIC_RE.search(user_text or ""))\n\n\n'''
        s = s.replace(anchor, guard + anchor, 1)

    aff = '''# Russian and English confirmations. A confirmation executes the exact pending tool call once.\n_AFFIRM_RE = re.compile(\n    r"^(?:yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that's right|correct|fine|"\n    r"absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|подтверждаю|подтверждено|"\n    r"подтверждай|разрешаю|разрешено|делай|делайте|выполняй|выполняйте|выполни|выполнить|"\n    r"запускай|запускайте|устанавливай|устанавливайте|установи|установить|продолжай|продолжайте|"\n    r"можно|добро|верно|точно|давай|давай делай)[\\s,.!?;:]*$",\n    re.IGNORECASE,\n)\n\n\ndef _is_affirmation(text: str) -> bool:\n    t = re.sub(r"[\\s,.!?;:]+", " ", (text or "").strip().lower()).strip()\n    return bool(_AFFIRM_RE.fullmatch(t))\n'''
    patterns = [
        re.compile(r"(?ms)^# A short affirmation that grants a pending confirmation.*?^def _is_affirmation\\(text: str\\) -> bool:\n    return .*?(?=\n\n# Pure conversational turns)"),
        re.compile(r"(?ms)^# Russian and English confirmations.*?^def _is_affirmation\\(text: str\\) -> bool:\n    t = .*?\n    return .+?(?=\n\n# Pure conversational turns)"),
    ]
    for pattern in patterns:
        s2, n = pattern.subn(lambda _: aff, s, count=1)
        if n:
            s = s2
            break
    else:
        raise RuntimeError("cannot repair affirmation helper")

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
    }
    # Longer phrases first so a generic substring cannot leave a trailing English fragment.
    for old, new in sorted(replacements.items(), key=lambda kv: len(kv[0]), reverse=True):
        s = s.replace(old, new)

    s = s.replace(
        "I wasn't able to pull that up just now, sir — let me try again in a moment rather than guess.",
        "Не удалось получить эти данные, сэр. Я не буду гадать и попробую ещё раз.",
    )
    s = s.replace(
        "This request has MORE THAN ONE part. Complete EVERY part — use the right tool for each, one after another — and do not give your final reply until all parts are done or you've said which part you can't do and why.",
        "В запросе несколько частей. Выполни каждую часть подходящим инструментом. Не сообщай о завершении, пока все части не выполнены.",
    )

    s = s.replace('    "define_word", "wiki_lookup", "news_brief",\n', '    "define_word", "wiki_lookup",\n')
    write(p, s)


def patch_tests() -> None:
    p = "tests/test_runtime_v8.py"
    s = read(p)
    extra = '''\n\ndef test_catastrophic_guard_exists_and_is_narrow():\n    from jarvis.brain.agent import _catastrophic\n    assert callable(_catastrophic)\n    assert _catastrophic("удали всё с диска C")\n    assert not _catastrophic("удали файл report.txt")\n\n\ndef test_spoken_ack_sets_are_russian():\n    from jarvis.brain.agent import _WORK_ACKS, _CHAT_ACKS, _TOOL_PROGRESS\n    spoken = list(_WORK_ACKS) + list(_CHAT_ACKS) + list(_TOOL_PROGRESS.values())\n    forbidden = ("Right away", "On it", "Of course", "Yes, sir", "Certainly", "One moment")\n    assert not any(any(x in phrase for x in forbidden) for phrase in spoken)\n'''
    if "test_catastrophic_guard_exists_and_is_narrow" not in s:
        s += extra
    write(p, s)


def main() -> None:
    patch_agent()
    patch_tests()
    print("runtime v11 repair applied")


if __name__ == "__main__":
    main()
