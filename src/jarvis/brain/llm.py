"""LLM client for Jarvis's brain — freellmapi (OpenAI-compatible) with a fallback chain.

A single rate-limit or provider hiccup must never mute Jarvis, so every call walks
``settings.llm_chain`` (primary first, then ordered fallbacks) and returns the first model
that answers. Supports both plain streaming and OpenAI-style tool-calling.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from openai import AsyncOpenAI
from openai import APIError, APITimeoutError, RateLimitError

from jarvis.config import settings

# Errors that mean "this model is unavailable right now — try the next one".
_FAILOVER = (RateLimitError, APITimeoutError, APIError)


class _EmptyResponse(Exception):
    """A model returned 200 but with no usable choice (some proxies wrap errors in a 200)."""


class LLMClient:
    """Thin wrapper over the freellmapi OpenAI-compatible endpoint with model failover."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.freellmapi_base_url,
            api_key=settings.freellmapi_api_key or "freellmapi",
            timeout=settings.llm_request_timeout_seconds,
            max_retries=0,  # we do our own cross-model failover, not in-model retries
        )
        self._chain = settings.llm_chain

    @property
    def chain(self) -> list[str]:
        return self._chain

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.6,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> Any:
        """Non-streaming completion (used for tool-calling turns). Returns the message.

        Walks the fallback chain on provider errors. Raises the last error if all fail.
        ``tool_choice`` is passed to the provider: "auto" (default), "required" (the model MUST
        call some tool — used to stop a weak model from *claiming* it acted without acting), or a
        ``{"type":"function","function":{"name": ...}}`` dict to force one specific tool.
        """
        last_err: Exception | None = None
        for model in self._chain:
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                resp = await self._client.chat.completions.create(**kwargs)
                if not getattr(resp, "choices", None):
                    # 200 with no choices = proxy/model error object — fail over, don't crash.
                    raise _EmptyResponse(getattr(resp, "error", None) or "empty choices")
                if model != self._chain[0]:
                    logger.warning(f"LLM primary unavailable; answered via fallback '{model}'")
                return resp.choices[0].message
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                logger.warning(f"LLM model '{model}' failed ({type(e).__name__}); trying next")
                continue
        raise RuntimeError(f"all LLM models failed; last error: {last_err}")

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.6,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream a completion that may also call tools. Yields events:

        * ``("text", delta)``  — a chunk of spoken content as it generates (feed straight to TTS).
        * ``("tools", calls)`` — emitted once at the end if the model called tools; ``calls`` is a
          list of normalised ``{"id","name","arguments"}`` dicts (arguments is a JSON string).

        This is what lets the voice path speak the first sentence while the rest is still being
        generated. Fails over to the next model ONLY before the first token — once we've started
        yielding we never silently switch mid-utterance (that would double-speak).
        """
        last_err: Exception | None = None
        for model in self._chain:
            tool_acc: dict[int, dict[str, str]] = {}
            got_any = False
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                stream = await self._client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if getattr(delta, "content", None):
                        got_any = True
                        yield ("text", delta.content)
                    for tcd in getattr(delta, "tool_calls", None) or []:
                        got_any = True
                        slot = tool_acc.setdefault(tcd.index, {"id": "", "name": "", "arguments": ""})
                        if tcd.id:
                            slot["id"] = tcd.id
                        if tcd.function:
                            if tcd.function.name:
                                slot["name"] += tcd.function.name
                            if tcd.function.arguments:
                                slot["arguments"] += tcd.function.arguments
                if not got_any:
                    raise _EmptyResponse("stream produced no content")
                if tool_acc:
                    yield ("tools", [tool_acc[i] for i in sorted(tool_acc)])
                if model != self._chain[0]:
                    logger.warning(f"LLM streaming via fallback '{model}'")
                return
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                if got_any:
                    # Already speaking — don't fail over and repeat; end the utterance here.
                    logger.warning(f"LLM stream '{model}' broke mid-utterance ({type(e).__name__})")
                    return
                logger.warning(f"LLM stream '{model}' failed ({type(e).__name__}); trying next")
                continue
        raise RuntimeError(f"all LLM models failed; last error: {last_err}")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.6,
    ) -> AsyncIterator[str]:
        """Stream text deltas from the first model that responds (no tools)."""
        last_err: Exception | None = None
        for model in self._chain:
            try:
                stream = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                if model != self._chain[0]:
                    logger.warning(f"LLM streaming via fallback '{model}'")
                got_any = False
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        got_any = True
                        yield delta
                if not got_any:
                    raise _EmptyResponse("stream produced no content")
                return
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                logger.warning(f"LLM stream '{model}' failed ({type(e).__name__}); trying next")
                continue
        raise RuntimeError(f"all LLM models failed; last error: {last_err}")
