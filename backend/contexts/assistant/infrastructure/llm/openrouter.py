from __future__ import annotations

from backend.contexts.assistant.domain.errors import (
    UpstreamError,
)

import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Iterator, Sequence

from backend.contexts.assistant.domain.cancellation import CancellationToken
from backend.contexts.assistant.infrastructure.llm.chat_events import (
    ChatEvent,
    ChatMessage,
    Done,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from backend.contexts.assistant.infrastructure.llm.tools_format import (
    to_openai_messages,
    to_openai_tools,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_MAX_TOKENS = 2400
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT = 60.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _abort_response(response: Any) -> None:
    try:
        sock = response.fp.raw._sock
        sock.shutdown(socket.SHUT_RDWR)
    except (AttributeError, OSError, ValueError):
        pass
    try:
        response.close()
    except (OSError, ValueError):
        pass


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("provider stream exceeded its total time budget")
    return remaining


def _response_lines(response: Any, deadline: float) -> Iterator[str]:
    while True:
        remaining = _remaining_time(deadline)
        try:
            response.fp.raw._sock.settimeout(remaining)
        except AttributeError:
            # Test doubles and alternate response implementations may not expose
            # the urllib socket. Production urllib responses do.
            pass
        line = response.readline()
        if not line:
            return
        yield line.decode("utf-8", errors="replace")


def _wait_before_retry(
    deadline: float, cancellation: CancellationToken | None
) -> None:
    try:
        pause = min(0.5, _remaining_time(deadline))
    except TimeoutError as error:
        raise UpstreamError(
            "openrouter did not respond within its total time budget",
            code="provider-timeout",
        ) from error
    if cancellation is not None:
        if cancellation.wait(pause):
            raise UpstreamError("request cancelled", code="cancelled")
    else:
        time.sleep(pause)


class _ToolCallBuffer:
    def __init__(self) -> None:
        self._slots: dict[int, dict[str, str]] = {}

    def absorb(self, deltas: Sequence[dict[str, Any]]) -> None:
        for delta in deltas:
            index = int(delta.get("index", 0))
            slot = self._slots.setdefault(index, {"id": "", "name": "", "args": ""})
            identifier = delta.get("id")
            if isinstance(identifier, str) and identifier:
                slot["id"] = identifier
            function = delta.get("function") or {}
            name = function.get("name")
            if isinstance(name, str) and name:
                slot["name"] = name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                slot["args"] += arguments

    def drain(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for index in sorted(self._slots):
            slot = self._slots[index]
            if not slot["name"]:
                continue
            raw = slot["args"].strip() or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                raise UpstreamError(
                    f"tool call arguments for {slot['name']} arrived as "
                    f"incomplete JSON and do not parse: {error}"
                ) from error
            if not isinstance(parsed, dict):
                raise UpstreamError(
                    f"tool call arguments for {slot['name']} are not a JSON object"
                )
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    args=parsed,
                )
            )
        self._slots.clear()
        return calls


def parse_sse_lines(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            return
        try:
            yield json.loads(payload)
        except json.JSONDecodeError as error:
            raise UpstreamError(
                f"the provider sent an SSE line that does not parse as JSON: {error}"
            ) from error


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set: the OpenRouter client does not "
                "work without a key and the project ships no stub clients"
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._ssl_context = ssl.create_default_context()
        try:
            import certifi
        except ImportError:
            pass
        else:
            self._ssl_context.load_verify_locations(cafile=certifi.where())

    @property
    def provider(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return self._model

    def _body(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        system: str,
    ) -> bytes:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": True,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": system},
                *to_openai_messages(messages),
            ],
        }
        if tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _open(
        self,
        body: bytes,
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
    ) -> Any:
        deadline = deadline or (time.monotonic() + self._timeout)
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "X-Title": "AIOS Jarvis",
            },
        )
        attempts = 0
        while True:
            if cancellation is not None and cancellation.cancelled:
                raise UpstreamError("request cancelled", code="cancelled")
            try:
                remaining = _remaining_time(deadline)
            except TimeoutError as error:
                raise UpstreamError(
                    f"{self.provider} did not respond within {self._timeout:g} seconds",
                    code="provider-timeout",
                ) from error
            attempts += 1
            try:
                response = urllib.request.urlopen(
                    request, timeout=remaining, context=self._ssl_context,
                )
                if cancellation is not None and cancellation.cancelled:
                    _abort_response(response)
                    raise UpstreamError("request cancelled", code="cancelled")
                return response
            except urllib.error.HTTPError as error:
                if error.code in RETRY_STATUSES and attempts == 1:
                    _wait_before_retry(deadline, cancellation)
                    continue
                detail = error.read().decode("utf-8", errors="replace")
                detail = detail.replace(self._api_key, "[REDACTED]")[:400]
                if error.code == 401:
                    code = "provider-auth"
                elif error.code == 429:
                    code = "provider-rate-limit"
                elif error.code >= 500:
                    code = "provider-server-error"
                else:
                    code = "provider-http-error"
                raise UpstreamError(
                    f"{self.provider} answered {error.code}: {detail or error.reason}",
                    code=code,
                    http_status=error.code,
                ) from error
            except urllib.error.URLError as error:
                if attempts == 1:
                    _wait_before_retry(deadline, cancellation)
                    continue
                if isinstance(error.reason, TimeoutError):
                    code = "provider-timeout"
                else:
                    code = "provider-unreachable"
                raise UpstreamError(
                    f"{self.provider} is unreachable: {error.reason}", code=code
                ) from error
            except TimeoutError as error:
                raise UpstreamError(
                    f"{self.provider} did not respond within {self._timeout:g} seconds",
                    code="provider-timeout",
                ) from error

    def stream(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        system: str,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[ChatEvent]:
        deadline = time.monotonic() + self._timeout
        response = self._open(self._body(messages, tools, system), cancellation, deadline)
        deadline_expired = threading.Event()

        def expire_stream() -> None:
            # Socket inactivity timeouts reset whenever a byte arrives. A
            # partial SSE line can therefore hold readline past the wall
            # budget even though _response_lines sets the socket timeout.
            deadline_expired.set()
            _abort_response(response)

        watchdog = threading.Timer(max(0.0, deadline - time.monotonic()), expire_stream)
        watchdog.daemon = True
        watchdog.start()
        unregister = (
            cancellation.register(lambda: _abort_response(response))
            if cancellation is not None
            else lambda: None
        )
        buffer = _ToolCallBuffer()
        stop = "end_turn"
        usage: dict[str, int] = {}
        try:
            with response:
                for chunk in parse_sse_lines(_response_lines(response, deadline)):
                    if cancellation is not None and cancellation.cancelled:
                        raise UpstreamError("request cancelled", code="cancelled")
                    reported = chunk.get("usage")
                    if isinstance(reported, dict):
                        usage = {
                            key: int(value)
                            for key, value in reported.items()
                            if isinstance(value, int)
                        }
                    error = chunk.get("error")
                    if isinstance(error, dict):
                        raise UpstreamError(
                            f"{self.provider} returned an error inside the stream: "
                            f"{str(error.get('message', 'no description given')).replace(self._api_key, '[REDACTED]')}"
                        )
                    for choice in chunk.get("choices", ()):
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield TextDelta(text=content)
                        calls = delta.get("tool_calls")
                        if isinstance(calls, list) and calls:
                            buffer.absorb(calls)
                        reason = choice.get("finish_reason")
                        if isinstance(reason, str) and reason:
                            stop = reason
            if deadline_expired.is_set():
                raise TimeoutError("provider stream exceeded its total time budget")
            for call in buffer.drain():
                yield call
            yield Done(stop=stop, usage=usage)
        except TimeoutError as error:
            if cancellation is not None and cancellation.cancelled:
                raise UpstreamError("request cancelled", code="cancelled") from error
            raise UpstreamError(
                f"{self.provider} did not respond within {self._timeout:g} seconds",
                code="provider-timeout",
            ) from error
        except Exception as error:
            if cancellation is not None and cancellation.cancelled:
                raise UpstreamError("request cancelled", code="cancelled")
            if deadline_expired.is_set():
                raise UpstreamError(
                    f"{self.provider} did not respond within {self._timeout:g} seconds",
                    code="provider-timeout",
                ) from error
            raise
        finally:
            watchdog.cancel()
            unregister()
