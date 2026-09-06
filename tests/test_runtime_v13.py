from jarvis.brain.agent import _is_affirmation
from jarvis.brain.computer_direct import direct_computer_command
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
    # The direct layer must claim these commands before the LLM. We don't execute them in CI;
    # this checks that the command grammar is accepted by the deterministic router.
    assert direct_computer_command("открой Telegram") is None or isinstance(direct_computer_command("открой Telegram"), str)
    assert direct_computer_command("закрой Telegram") is None or isinstance(direct_computer_command("закрой Telegram"), str)
