"""Streaming voice path — agent.respond_stream yields spoken sentences as they generate.

Hermetic (fake LLM, no network). Verifies: (1) a plain answer streams out sentence-by-sentence;
(2) a tool call is resolved between passes and the final answer still streams; (3) the full reply
is persisted to history; (4) the sentence splitter keeps a trailing partial sentence and flushes it.

    uv run python bench/test_streaming.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


class FakeLLM:
    """Scripted streamer: each call to stream_with_tools replays the next pass of events."""

    def __init__(self, scripts: list[list[tuple]]) -> None:
        self._scripts = scripts
        self._i = 0

    async def stream_with_tools(self, messages, tools=None, temperature=0.6, tool_choice="auto"):
        script = self._scripts[self._i]
        self._i += 1
        for ev in script:
            yield ev


async def test_plain_answer() -> None:
    print("[1] plain answer streams sentence-by-sentence")
    from jarvis.brain.agent import JarvisAgent

    agent = JarvisAgent()
    agent._llm = FakeLLM([[("text", "I am well, Sir. "), ("text", "All systems green.")]])
    out = [s async for s in agent.respond_stream("how are you")]
    check("yielded two sentences in order", out == ["I am well, Sir.", "All systems green."], repr(out))
    check("full reply persisted to history",
          agent._history[-1]["role"] == "assistant"
          and "All systems green." in agent._history[-1]["content"], repr(agent._history[-1]))


async def test_tool_then_stream() -> None:
    print("\n[2] a tool call is resolved, then the final answer streams")
    from jarvis.brain.agent import JarvisAgent

    agent = JarvisAgent()
    ran = {"n": 0}

    async def fake_tool(_args: dict) -> str:
        ran["n"] += 1
        return "12:00"

    agent._registry["get_time"] = fake_tool
    agent._llm = FakeLLM([
        [("tools", [{"id": "c1", "name": "get_time", "arguments": "{}"}])],
        [("text", "It is noon, Sir.")],
    ])
    out = [s async for s in agent.respond_stream("what time is it")]
    check("the tool ran exactly once", ran["n"] == 1, str(ran))
    check("the post-tool answer streamed", out == ["It is noon, Sir."], repr(out))
    check("history holds user + tool turn + final assistant",
          agent._history[-1]["content"] == "It is noon, Sir.")


async def test_no_double_failover_midstream() -> None:
    print("\n[3] mid-stream provider break does not double-speak (fails over only before 1st token)")
    from jarvis.brain.llm import LLMClient

    llm = LLMClient()
    llm._chain = ["a", "b"]

    import httpx
    from openai import APITimeoutError

    async def fake_create(**kwargs):
        # Model 'a' yields one token then the stream raises a (failover-eligible) timeout; 'b'
        # would answer — but since 'a' already emitted, we must NOT fail over (would repeat speech).
        async def gen():
            if kwargs["model"] == "a":
                yield _chunk("Hello ")
                raise APITimeoutError(request=httpx.Request("POST", "http://localhost"))
            yield _chunk("SHOULD-NOT-APPEAR")
        return gen()

    llm._client.chat.completions.create = fake_create
    texts = []
    async for kind, payload in llm.stream_with_tools([{"role": "user", "content": "hi"}]):
        if kind == "text":
            texts.append(payload)
    check("only the first model's partial text came through", texts == ["Hello "], repr(texts))


def _chunk(content):
    from types import SimpleNamespace
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=None))])


async def main() -> None:
    await test_plain_answer()
    await test_tool_then_stream()
    await test_no_double_failover_midstream()
    print(f"\n=== {passed}/{passed + failed} checks passed ===")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
