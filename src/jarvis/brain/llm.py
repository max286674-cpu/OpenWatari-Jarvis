"""LLM client for Jarvis's brain — freellmapi (OpenAI-compatible) with a fallback chain.

A single rate-limit or provider hiccup must never mute Jarvis, so every call walks
``settings.llm_chain`` (primary first, then ordered fallbacks) and returns the first model
that answers. Supports both plain streaming and OpenAI-style tool-calling.
"""

from __future__ import annotations

import asyncio
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
    """OpenAI-compatible client with model failover + per-model provider routing.

    A chain entry is a model name optionally prefixed with a provider: ``groq:<model>`` hits Groq
    directly (api.groq.com, JARVIS_GROQ_API_KEY) for a fast, consistent primary; an unprefixed name
    goes to the freellmapi proxy. Failover walks ``settings.llm_chain``; streaming also fails over if
    no FIRST token arrives within ``llm_first_token_timeout_seconds`` (a slow/hung model -> fast
    recovery instead of a full-timeout stall)."""

    def __init__(self) -> None:
        self._timeout = settings.llm_request_timeout_seconds
        self._first_token_timeout = max(0.5, settings.llm_first_token_timeout_seconds)
        self._clients: dict[str, AsyncOpenAI] = {}
        self._default = self._make_client(
            settings.freellmapi_base_url, settings.freellmapi_api_key or "freellmapi"
        )
        self._chain = settings.llm_chain

    def _make_client(self, base_url: str, api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=self._timeout, max_retries=0)

    def _resolve(self, entry: str) -> tuple[AsyncOpenAI, str]:
        """Map a chain entry to (client, model_name), honouring a ``provider:`` prefix."""
        if entry.startswith("groq:"):
            client = self._clients.get("groq")
            if client is None:
                client = self._clients["groq"] = self._make_client(
                    settings.groq_base_url, settings.groq_api_key or "missing-groq-key"
                )
            return client, entry[len("groq:"):]
        return self._default, entry

    @property
    def chain(self) -> list[str]:
        return self._chain

    async def warmup(self) -> None:
        """Pre-open a connection to EVERY distinct provider in the chain, so neither the first turn
        NOR the first failover pays a cold TLS/connection setup — a real, measurable slice of TTFT
        (fine-tuning.md Item 3 / docs/AUDIT.md). One tiny 1-token ping per distinct client, fired
        concurrently and best-effort: a provider that's down logs a debug line, never blocks startup.
        """
        seen: set[int] = set()
        pings = []
        for entry in self._chain:
            client, model_name = self._resolve(entry)
            if id(client) in seen:
                continue
            seen.add(id(client))
            pings.append(self._ping(client, model_name))
        if pings:
            await asyncio.gather(*pings, return_exceptions=True)

    async def _ping(self, client: AsyncOpenAI, model_name: str) -> None:
        try:
            await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.0,
                max_tokens=1,
            )
            logger.debug(f"warmup: primed '{model_name}'")
        except Exception as e:  # noqa: BLE001 — warmup is best-effort
            logger.debug(f"warmup ping for '{model_name}' skipped: {type(e).__name__}")

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
            client, model_name = self._resolve(model)
            try:
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                resp = await client.chat.completions.create(**kwargs)
                if not getattr(resp, "choices", None):
                    # 200 with no choices = proxy/model error object — fail over, don't crash.
                    raise _EmptyResponse(getattr(resp, "error", None) or "empty choices")
                msg = resp.choices[0].message
                # A 200 with a choice but NEITHER content NOR a tool call = the model said nothing
                # usable (congested free proxies do this intermittently). Treat it as a miss and fail
                # over to the next model rather than muting Watari with "I didn't catch that".
                if not (getattr(msg, "content", None) or getattr(msg, "tool_calls", None)):
                    raise _EmptyResponse("message had neither content nor tool_calls")
                if model != self._chain[0]:
                    logger.warning(f"LLM primary unavailable; answered via fallback '{model}'")
                return msg
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
            client, model_name = self._resolve(model)
            tool_acc: dict[int, dict[str, str]] = {}
            got_any = False
            try:
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                stream = await client.chat.completions.create(**kwargs)
                ait = stream.__aiter__()
                while True:
                    try:
                        # The FIRST token must arrive within the deadline (snappy failover off a
                        # slow/hung model); once we're streaming, later chunks aren't capped.
                        chunk = await asyncio.wait_for(
                            ait.__anext__(),
                            timeout=None if got_any else self._first_token_timeout,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as e:
                        raise _EmptyResponse(
                            f"no first token within {self._first_token_timeout}s"
                        ) from e
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
            client, model_name = self._resolve(model)
            try:
                stream = await client.chat.completions.create(
                    model=model_name,
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
