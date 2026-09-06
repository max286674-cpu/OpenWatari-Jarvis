from jarvis.brain.agent import _is_affirmation
from jarvis.brain.intent_router import forced_tools


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
    for text in ("открой Telegram", "запусти калькулятор", "открой Chrome"):
        assert forced_tools(text) == ["open_app"]
