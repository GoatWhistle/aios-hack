from __future__ import annotations

import importlib
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
from backend.contexts.assistant.domain.errors import UpstreamError
from backend.contexts.assistant.infrastructure.llm.tools_format import (
    to_anthropic_messages,
    to_anthropic_tools,
)

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_TOKENS = 2400
DEFAULT_TEMPERATURE = 0.2
SDK_MODULE = "anthropic"


def _sdk(api_key: str, timeout: float = DEFAULT_TIMEOUT) -> Any:
    try:
        module = importlib.import_module(SDK_MODULE)
    except ImportError as error:
        raise RuntimeError(
            "the anthropic package is not installed: the Jarvis fallback "
            "provider needs it, while the primary path is OpenRouter over urllib"
        ) from error
    return module.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)


class AnthropicChatClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: float = DEFAULT_TIMEOUT,
        sdk: Any | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set: the Jarvis fallback provider does "
                "not work without a key and the project ships no stub clients"
            )
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._client = sdk if sdk is not None else _sdk(api_key, timeout)

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def stream(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        system: str,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[ChatEvent]:
        if cancellation is not None and cancellation.cancelled:
            raise UpstreamError("request cancelled", code="cancelled")
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": system,
            "messages": to_anthropic_messages(messages),
        }
        if tools:
            request["tools"] = to_anthropic_tools(tools)
        request["timeout"] = self._timeout
        try:
            response = self._client.messages.create(**request)
        except Exception as error:
            status = getattr(error, "status_code", None)
            if status == 401:
                code = "provider-auth"
            elif status == 429:
                code = "provider-rate-limit"
            elif isinstance(status, int) and status >= 500:
                code = "provider-server-error"
            elif "timeout" in type(error).__name__.lower():
                code = "provider-timeout"
            else:
                code = "provider-unreachable"
            details = f" (HTTP {status})" if isinstance(status, int) else ""
            raise UpstreamError(
                f"anthropic request failed{details}",
                code=code,
                **({"http_status": status} if isinstance(status, int) else {}),
            ) from error
        if cancellation is not None and cancellation.cancelled:
            raise UpstreamError("request cancelled", code="cancelled")
        calls: list[ToolCall] = []
        for block in response.content:
            kind = getattr(block, "type", None)
            if kind == "text":
                yield TextDelta(text=block.text)
            elif kind == "tool_use":
                calls.append(
                    ToolCall(id=block.id, name=block.name, args=dict(block.input))
                )
        for call in calls:
            yield call
        usage_source = getattr(response, "usage", None)
        usage: dict[str, int] = {}
        if usage_source is not None:
            for key in ("input_tokens", "output_tokens"):
                value = getattr(usage_source, key, None)
                if isinstance(value, int):
                    usage[key] = value
        yield Done(stop=str(getattr(response, "stop_reason", "end_turn")), usage=usage)
