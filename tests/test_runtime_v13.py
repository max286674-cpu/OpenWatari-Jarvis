from jarvis.brain.agent import _is_affirmation
from jarvis.brain.computer_direct import _CLOSE_RE, _OPEN_RE
from jarvis.brain.proactive import confirm_required


def test_russian_affirmations():
    for text in ("да", "ага", "угу", "ок", "подтверждаю", "разрешаю", "делай", "выполняй"):
        assert _is_affirmation(text)


def test_confirmation_only_for_consequential_actions():
    assert not confirm_required("process_op", {"action": "kill"})
    assert not confirm_required("process_op", {"action": "start"})
    assert not confirm_required("browser", {})
    assert not confirm_required("create_event", {})
    assert not confirm_required("file_op", {"action": "create_file"})
    assert confirm_required("file_op", {"action": "delete_file"})
    assert confirm_required("send_telegram", {"chat": "owner"})
    assert confirm_required("send_email", {"to": "someone@example.com"})


def test_russian_open_close_commands_are_deterministic():
    assert _OPEN_RE.match("открой Telegram")
    assert _OPEN_RE.match("запусти Chrome")
    assert _CLOSE_RE.match("закрой Telegram")
    assert _CLOSE_RE.match("выключи Discord")
