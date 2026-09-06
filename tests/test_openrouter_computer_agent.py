from jarvis.config import settings
from jarvis.brain.tools import tool_handlers, tool_names


def test_openrouter_model_chains_are_configured():
    assert settings.llm_chain
    assert settings.llm_chain[0] == "qwen/qwen3-30b-a3b-instruct-2507"
    assert settings.vision_chain
    assert settings.vision_chain[0] == "qwen/qwen3-vl-30b-a3b-instruct"


def test_computer_use_is_registered():
    assert "computer_use" in tool_names()
    assert "computer_use" in tool_handlers()


def test_computer_agent_is_enabled_by_default():
    assert settings.desktop_tools_enabled is True
    assert 1 <= settings.computer_max_steps <= 10
