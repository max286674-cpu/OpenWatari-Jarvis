from jarvis.brain.agent import _catastrophic, _is_affirmation, _is_pure_chat
from jarvis.brain.intent_router import forced_tools
from jarvis.brain.tools import tool_names


def test_russian_confirmation_is_recognized():
    for text in ("да", "ага", "подтверждаю", "делай", "выполняй", "устанавливай", "разрешаю"):
        assert _is_affirmation(text)


def test_non_confirmation_is_not_granted():
    for text in ("нет", "не надо", "отмена", "потом", "что ты делаешь"):
        assert not _is_affirmation(text)


def test_russian_close_routes_to_process_tool():
    for text in ("закрой Telegram", "закрой хром", "выключи Discord", "останови Spotify"):
        assert forced_tools(text) == ["process_op"]


def test_russian_open_routes_to_open_app():
    for text in ("открой Telegram", "запусти калькулятор", "включи Chrome"):
        assert forced_tools(text) == ["open_app"]


def test_pure_chat_dependency_exists():
    for text in ("Почему?", "Привет", "Спасибо", "hi", "ok"):
        assert _is_pure_chat(text)


def test_catastrophic_guard_is_narrow():
    assert _catastrophic("удали всё с диска C")
    assert _catastrophic("удали всё с диска C:")
    assert not _catastrophic("удали файл report.txt")
    assert not _catastrophic("удали папку C:\\Projects")


def test_computer_agent_tools_are_registered():
    names = set(tool_names())
    assert {"desktop_action", "desktop_screenshot"}.issubset(names)
