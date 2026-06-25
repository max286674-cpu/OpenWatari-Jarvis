"""LLM client for Jarvis's brain — freellmapi (OpenAI-compatible) with a fallback chain.

A single rate-limit or provider hiccup must never mute Jarvis, so every call walks
``settings.llm_chain`` (primary first, then ordered fallbacks) and returns the first model
that answers. Supports both plain streaming and OpenAI-style tool-calling.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from openai import AsyncOpenAI
from openai import APIError, APITimeoutError, RateLimitError

from jarvis.config import settings

# Errors that mean "this model is unavailable right now — try the next one".
_FAILOVER = (RateLimitError, APITimeoutError, APIError)

# A weaker model in the chain sometimes emits a tool call AS TEXT — '<function name="...">',
# '<tool_code ...>', '<|python_tag|>…', 'print(default_api.x(...))' — instead of using the native
# tool-calling API. If we accept that as a final answer the TOOL NEVER RUNS and the raw tag gets
# spoken aloud. We detect it (in the message lead) and treat it as an empty response, so the chain
# fails over to a model that calls tools natively. Behavioral suite found this; it was the single
# biggest correctness drag (scrape/telegram/calendar/email all silently no-op'd).
_TEXTUAL_TOOLCALL_RE = re.compile(
    r"<\s*(function|tool_call|tool_code|tool_response|invoke)\b|</\s*function\b|"
    r"\bdefault_api\s*\.\w|print\s*\(\s*default_api|<\|\s*(python_tag|tool)",
    re.IGNORECASE,
)


def _looks_like_textual_toolcall(text: str | None) -> bool:
    t = (text or "").lstrip()
    return bool(t) and bool(_TEXTUAL_TOOLCALL_RE.search(t[:160]))


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
        self._cooldown = max(0.0, settings.llm_unhealthy_cooldown_seconds)
        self._unhealthy_until: dict[str, float] = {}
        self.last_route: dict[str, Any] = {}
        self._clients: dict[str, AsyncOpenAI] = {}
        self._default = self._make_client(
            settings.freellmapi_base_url, settings.freellmapi_api_key or "freellmapi"
        )
        self._chain = settings.llm_chain

    def _make_client(self, base_url: str, api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=self._timeout, max_retries=0)

    def _resolve(self, entry: str) -> tuple[AsyncOpenAI, str]:
        """Map a chain entry to (client, model_name), honouring a ``provider:`` prefix.

        ``groq:<model>`` hits Groq directly; ``ollama:<model>`` hits a LOCAL Ollama server (no key,
        true offline fallback); unprefixed goes to the freellmapi proxy. Each provider's client is
        built once and cached."""
        for prefix, base_url, api_key in (
            ("groq:", settings.groq_base_url, settings.groq_api_key or "missing-groq-key"),
            ("ollama:", settings.ollama_base_url, "ollama"),  # Ollama ignores the key
        ):
            if entry.startswith(prefix):
                name = prefix[:-1]
                client = self._clients.get(name)
                if client is None:
                    client = self._clients[name] = self._make_client(base_url, api_key)
                return client, entry[len(prefix):]
        return self._default, entry

    @property
    def chain(self) -> list[str]:
        return self._chain

    def _candidate_chain(self) -> list[str]:
        """Return healthy entries first; if every entry is cooling down, try the full chain anyway."""
        if not self._cooldown:
            return list(self._chain)
        now = asyncio.get_running_loop().time()
        healthy = [m for m in self._chain if self._unhealthy_until.get(m, 0.0) <= now]
        if healthy:
            skipped = [m for m in self._chain if m not in healthy]
            if skipped:
                logger.debug(f"LLM skipping cooling-down models: {skipped}")
            return healthy
        return list(self._chain)

    def _mark_failure(self, model: str, err: Exception) -> None:
        if not self._cooldown:
            return
        self._unhealthy_until[model] = asyncio.get_running_loop().time() + self._cooldown
        logger.debug(f"LLM marked '{model}' unhealthy for {self._cooldown:.1f}s ({type(err).__name__})")

    def _mark_success(
        self,
        model: str,
        failures: int,
        mode: str,
        latency_ms: float | None = None,
        errors: list[dict[str, str]] | None = None,
    ) -> None:
        self._unhealthy_until.pop(model, None)
        self.last_route = {
            "mode": mode,
            "answered_by": model,
            "failed_over_count": failures,
            "latency_ms": latency_ms,
            "errors": errors or [],
        }
        logger.info(
            "LLM route: mode={} answered_by={} failed_over_count={} latency_ms={} errors={}",
            mode,
            model,
            failures,
            f"{latency_ms:.0f}" if latency_ms is not None else "n/a",
            errors or [],
        )

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
        route_started = asyncio.get_running_loop().time()
        errors: list[dict[str, str]] = []
        failures = 0
        for model in self._candidate_chain():
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
                # A textual tool-call (not a native one) means the tool wouldn't run — fail over to a
                # model that calls tools properly rather than speak the raw tag.
                if not getattr(msg, "tool_calls", None) and _looks_like_textual_toolcall(
                    getattr(msg, "content", None)
                ):
                    raise _EmptyResponse("textual tool-call instead of a native tool call")
                if model != self._chain[0]:
                    logger.warning(f"LLM primary unavailable; answered via fallback '{model}'")
                latency_ms = (asyncio.get_running_loop().time() - route_started) * 1000
                self._mark_success(model, failures, "complete", latency_ms, errors)
                return msg
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                failures += 1
                errors.append({"model": model, "error": type(e).__name__})
                self._mark_failure(model, e)
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
        route_started = asyncio.get_running_loop().time()
        errors: list[dict[str, str]] = []
        failures = 0
        for model in self._candidate_chain():
            client, model_name = self._resolve(model)
            tool_acc: dict[int, dict[str, str]] = {}
            got_any = False
            # Lead-buffer classification: hold the first chunk of CONTENT until we can tell prose
            # from a textual tool-call. Prose flushes and streams normally; a textual tool-call is
            # withheld (never spoken) so got_any stays False -> the no-content failover kicks in.
            lead = ""
            lead_state = "buffering"  # buffering -> prose | toolcall
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
                        if lead_state == "buffering":
                            lead += delta.content
                            if _looks_like_textual_toolcall(lead):
                                lead_state = "toolcall"   # withhold; never speak the tag
                            elif len(lead) >= 24:
                                lead_state = "prose"
                                got_any = True
                                yield ("text", lead)
                        elif lead_state == "prose":
                            got_any = True
                            yield ("text", delta.content)
                        # lead_state == "toolcall": swallow content (no native call -> will fail over)
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
                # Stream ended mid-buffer: flush a short prose lead (e.g. "Yes, sir."). A withheld
                # textual tool-call is intentionally NOT flushed -> stays unspoken, fails over.
                if lead_state == "buffering" and lead and not _looks_like_textual_toolcall(lead):
                    got_any = True
                    yield ("text", lead)
                if not got_any:
                    raise _EmptyResponse("stream produced no content")
                if tool_acc:
                    yield ("tools", [tool_acc[i] for i in sorted(tool_acc)])
                if model != self._chain[0]:
                    logger.warning(f"LLM streaming via fallback '{model}'")
                latency_ms = (asyncio.get_running_loop().time() - route_started) * 1000
                self._mark_success(model, failures, "stream_with_tools", latency_ms, errors)
                return
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                # A mid-stream break while still buffering committed PROSE: flush it and treat as
                # already-speaking (don't fail over / double-speak). A withheld textual tool-call is
                # NOT flushed, so it still fails over to a native-tool-calling model.
                if lead_state == "buffering" and lead and not _looks_like_textual_toolcall(lead):
                    got_any = True
                    yield ("text", lead)
                if got_any:
                    # Already speaking — don't fail over and repeat; end the utterance here.
                    logger.warning(f"LLM stream '{model}' broke mid-utterance ({type(e).__name__})")
                    latency_ms = (asyncio.get_running_loop().time() - route_started) * 1000
                    self._mark_success(model, failures, "stream_with_tools", latency_ms, errors)
                    return
                failures += 1
                errors.append({"model": model, "error": type(e).__name__})
                self._mark_failure(model, e)
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
        route_started = asyncio.get_running_loop().time()
        errors: list[dict[str, str]] = []
        failures = 0
        for model in self._candidate_chain():
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
                latency_ms = (asyncio.get_running_loop().time() - route_started) * 1000
                self._mark_success(model, failures, "stream", latency_ms, errors)
                return
            except (*_FAILOVER, _EmptyResponse) as e:
                last_err = e
                failures += 1
                errors.append({"model": model, "error": type(e).__name__})
                self._mark_failure(model, e)
                logger.warning(f"LLM stream '{model}' failed ({type(e).__name__}); trying next")
                continue
        raise RuntimeError(f"all LLM models failed; last error: {last_err}")
