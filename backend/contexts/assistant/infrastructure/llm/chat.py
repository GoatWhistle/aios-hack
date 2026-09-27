from __future__ import annotations

from typing import Iterator, Protocol, Sequence

from backend.contexts.assistant.domain.cancellation import CancellationToken
from backend.contexts.assistant.infrastructure.llm.chat_events import (
    ChatEvent,
    ChatMessage,
    ToolSpec,
)


class ChatClient(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        system: str,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[ChatEvent]: ...
