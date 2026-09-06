import asyncio

from jarvis.brain.agent import _is_affirmation
from jarvis.brain.computer_control import direct_command
from jarvis.brain.intent_router import forced_tools
from jarvis.brain.proactive import confirm_required
from jarvis.brain.tools import tool_names


def test_basic_computer_commands_are_recognized():
    async def run():
        import jarvis.brain.computer_control as cc
        old_open, old_close, old_find = cc.open_target, cc.close_target, cc.find_on_computer
        try:
            cc.open_target = lambda x: asyncio.sleep(0, result=f"OPEN:{x}")
            cc.close_target = lambda x: asyncio.sleep(0, result=f"CLOSE:{x}")
            cc.find_on_computer = lambda x: asyncio.sleep(0, result=f"FIND:{x}")
            assert await direct_command("открой Telegram") == "OPEN:Telegram"
            assert await direct_command("запусти калькулятор") == "OPEN:калькулятор"
            assert await direct_command("закрой Chrome") == "CLOSE:Chrome"
            assert await direct_command("выключи Discord") == "CLOSE:Discord"
            assert await direct_command("найди report.xlsx") == "FIND:report.xlsx"
        finally:
            cc.open_target, cc.close_target, cc.find_on_computer = old_open, old_close, old_find
    asyncio.run(run())


def test_routine_process_control_needs_no_confirmation():
    assert not confirm_required("process_op", {"action": "start", "command": "notepad.exe"})
    assert not confirm_required("process_op", {"action": "kill", "name": "Telegram.exe"})
    assert not confirm_required("process_op", {"action": "list", "name": "Telegram"})


def test_russian_confirmations_are_recognized():
    for text in ("да", "ага", "угу", "подтверждаю", "разрешаю", "делай", "выполняй", "окей"):
        assert _is_affirmation(text)


def test_russian_screen_routes_to_vision_agent():
    for text in ("посмотри что у меня на экране", "нажми на кнопку", "сделай это на компьютере", "управляй компьютером"):
        assert forced_tools(text) == ["computer_use"]


def test_computer_use_is_registered():
    assert "computer_use" in set(tool_names())


def test_unrelated_text_is_not_direct_computer_command():
    async def run():
        assert await direct_command("почему не открывается Telegram") is None
        assert await direct_command("расскажи про Telegram") is None
    asyncio.run(run())
