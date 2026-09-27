from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from backend.contexts.assistant.application.answer import marker_position
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore, RunStore
from backend.contexts.assistant.infrastructure.docs_index import DocsIndex
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.infrastructure.prompt import build_system_prompt
from backend.contexts.assistant.domain.session import (
    Session,
    SessionStore,
    check_question,
)
from backend.contexts.assistant.infrastructure.session_store import SessionDisk
from backend.contexts.assistant.infrastructure.system_map import SystemMap
from backend.contexts.assistant.application.orchestrator_compose import (
    call_tool,
    compose,
    live_status,
)
from backend.contexts.assistant.application.orchestrator_events import (
    BRIEFING_QUESTION_EN,
    BRIEFING_QUESTION_RU,
    BRIEFING_TOOLS,
    DEFAULT_TIMEOUT,
    MAX_TOOL_ROUNDS,
    Cancelled,
    Event,
    stamp,
)
from backend.contexts.assistant.application.tools import tool_specs
from backend.contexts.assistant.application.tools.context import (
    Card,
    ConsoleContext,
    ToolContext,
)
from backend.contexts.assistant.infrastructure.llm.chat import ChatClient
from backend.contexts.assistant.infrastructure.llm.chat_events import (
    ChatMessage,
    Done,
    TextDelta,
    ToolCall,
)


_NEIGHBOR_REFERENCE = re.compile(r"(?:соседн\w*|neighbou?r\w*)", re.IGNORECASE)
_EARLIER_REFERENCE = re.compile(
    r"(?:раньше|предыдущ\w*\s+шаг|на\s+шаг\s+раньше|earlier|previous\s+step|one\s+step\s+back)",
    re.IGNORECASE,
)
_HERE_FOLLOW_UP = re.compile(
    r"^\s*(?:а\s+)?(?:(?:что|what)\s+)?(?:здесь|тут|here)\s*[?!.,\s]*$",
    re.IGNORECASE,
)
_NAMED_WELL = re.compile(
    r"(?:скважин[а-яё]*|wells?)\s*(?:№|#)?\s*(\d+)", re.IGNORECASE
)
_NAMED_NEIGHBOR = re.compile(
    r"(?:соседн\w*|neighbou?r\w*)\s+(?:скважин[а-яё]*\s*)?(?:№|#)?\s*(\d+)",
    re.IGNORECASE,
)


def _contextual_tool_preset(
    question: str, console: ConsoleContext, session: Session | None = None
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Resolve clear contextual follow-ups using the active scene's data."""
    selected = console.selected_well
    if selected and _HERE_FOLLOW_UP.fullmatch(question):
        arguments: dict[str, Any] = {"well": selected}
        if console.step is not None:
            arguments["step"] = console.step
        return (("well_snapshot", arguments),)
    if (
        selected
        and console.step is not None
        and console.step > 0
        and _EARLIER_REFERENCE.search(question)
        and session is not None
        and session.history
        and "well" in session.history[-1].card_types
    ):
        previous_question = session.history[-1].question
        named = _NAMED_WELL.search(previous_question)
        if not named or named.group(1) == selected:
            return (("well_snapshot", {"well": selected, "step": console.step - 1}),)
    if not selected or not _NEIGHBOR_REFERENCE.search(question):
        return ()
    explicit = set(_NAMED_WELL.findall(question))
    named_neighbour = _NAMED_NEIGHBOR.search(question)
    if named_neighbour:
        explicit.add(named_neighbour.group(1))
    if any(well != selected for well in explicit):
        return ()
    return (("connectivity", {"well": selected}),)


class Orchestrator:
    def __init__(
        self,
        client: ChatClient,
        store: ArtifactStore,
        knowledge: Knowledge,
        sessions: SessionStore | None = None,
        max_rounds: int = MAX_TOOL_ROUNDS,
        timeout: float = DEFAULT_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
        runs: RunStore | None = None,
        docs: DocsIndex | None = None,
        system: SystemMap | None = None,
        disk: SessionDisk | None = None,
        capabilities: Callable[[], dict[str, Any]] | None = None,
        now: Callable[[], str] = stamp,
    ) -> None:
        self._now = now
        self._client = client
        self._store = store
        self._knowledge = knowledge
        self._runs = runs
        self._docs = docs
        self._system = system
        self._disk = disk
        self._capabilities = capabilities
        self._sessions = (
            sessions
            if sessions is not None
            else SessionStore(disk=disk)
        )
        self._max_rounds = max_rounds
        self._timeout = timeout
        self._clock = clock

    @property
    def sessions(self) -> SessionStore:
        return self._sessions

    @property
    def disk(self) -> SessionDisk | None:
        return self._disk

    @property
    def docs(self) -> DocsIndex | None:
        return self._docs

    @property
    def system(self) -> SystemMap | None:
        return self._system

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    def ask(
        self, session_id: str, question: str, console: ConsoleContext
    ) -> Iterator[Event]:
        text = check_question(question)
        session, generation = self._sessions.start(session_id, console)
        started = self._clock()
        wall_deadline = time.monotonic() + self._timeout
        self._record(
            session_id,
            {
                "type": "ask",
                "question": text,
                "context": console.as_dict(),
                "ts": self._now(),
            },
            console.lang,
        )
        try:
            for event in self._run(
                session,
                text,
                console,
                started,
                generation,
                wall_deadline=wall_deadline,
                preset=_contextual_tool_preset(text, console, session),
            ):
                self._record(session_id, event.as_dict(), console.lang)
                yield event
        except Cancelled:
            yield Event(
                "error",
                {
                    "code": "cancelled",
                    "message": (
                        "generation cancelled: a newer request arrived on the "
                        "same session or the client closed the connection"
                    ),
                },
            )
        finally:
            self._sessions.finish(session_id, generation)

    def briefing(
        self, session_id: str, console: ConsoleContext
    ) -> Iterator[Event]:
        session, generation = self._sessions.start(session_id, console)
        started = self._clock()
        wall_deadline = time.monotonic() + self._timeout
        question = (
            BRIEFING_QUESTION_EN if console.lang == "en" else BRIEFING_QUESTION_RU
        )
        try:
            yield from self._run(
                session,
                question,
                console,
                started,
                generation,
                wall_deadline=wall_deadline,
                preset=BRIEFING_TOOLS,
            )
        except Cancelled:
            yield Event(
                "error",
                {"code": "cancelled", "message": "briefing cancelled"},
            )
        finally:
            self._sessions.finish(session_id, generation)

    def _record(
        self, session_id: str, body: Mapping[str, Any], lang: str
    ) -> None:
        if self._disk is None:
            return
        if body.get("type") in ("caption_delta", "answer_delta", "status"):
            return
        try:
            self._disk.append(session_id, body, lang)
        except Exception:
            return

    def _checkpoint(self, session: Session, generation: int, started: float) -> None:
        if self._sessions.is_cancelled(session.session_id, generation):
            raise Cancelled(session.session_id)
        if self._clock() - started > self._timeout:
            raise TimeoutError(
                f"Jarvis exceeded the {self._timeout:.0f} s budget for a single "
                "answer: the upstream model or a tool did not finish in time"
            )

    def _messages(self, session: Session, question: str) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        memory = session.summary()
        if memory:
            messages.append(
                ChatMessage(
                    role="user", content=f"Earlier in this session:\n{memory}"
                )
            )
        messages.append(ChatMessage(role="user", content=question))
        return messages

    def _context(
        self,
        console: ConsoleContext,
        cancellation=None,
        deadline: float | None = None,
    ) -> ToolContext:
        return ToolContext(
            store=self._store,
            console=console,
            knowledge=self._knowledge,
            runs=self._runs,
            docs=self._docs,
            system=self._system,
            cancellation=cancellation,
            deadline=deadline,
        )

    def _live(self, context: ToolContext) -> dict[str, Any] | None:
        return live_status(context)

    def _run(
        self,
        session: Session,
        question: str,
        console: ConsoleContext,
        started: float,
        generation: int,
        wall_deadline: float,
        preset: Sequence[tuple[str, Mapping[str, Any]]] = (),
    ) -> Iterator[Event]:
        scene_id = session.next_scene_id()
        yield Event(
            "scene",
            {
                "scene_id": scene_id,
                "question": question,
                "context": console.as_dict(),
                "ts": self._now(),
                "session_id": session.session_id,
            },
            generation=generation,
        )
        if self._capabilities is not None:
            try:
                yield Event("capabilities", self._capabilities())
            except Exception:
                pass
        context = self._context(console, session.cancellation, wall_deadline)
        system = build_system_prompt(
            console,
            console.lang,
            system=self._system,
            live=self._live(context),
            memory=session.summary_text,
        )
        messages = self._messages(session, question)
        specs = tool_specs()
        cards: list[Card] = []
        order = 0
        rounds = 0
        deltas: list[str] = []
        for name, arguments in preset:
            self._checkpoint(session, generation, started)
            yield Event("status", {"state": "tool", "tool": name})
            order += 1
            card, result = call_tool(context, ToolCall(id=f"p{order}", name=name, args=arguments))
            cards.append(card)
            yield Event(
                "card",
                {
                    "scene_id": scene_id,
                    "card_id": f"c-{order:02d}",
                    "order": order,
                    "tool": name,
                    "args": dict(arguments),
                    "card": card.as_dict(),
                },
            )
            messages.append(
                ChatMessage(
                    role="user",
                    content=f"Tool {name} returned: "
                    + json.dumps(result, ensure_ascii=False),
                )
            )
        while True:
            self._checkpoint(session, generation, started)
            yield Event("status", {"state": "thinking"})
            calls: list[ToolCall] = []
            deltas = []
            in_answer = False
            final = rounds >= self._max_rounds
            try:
                stream = self._client.stream(
                    messages, specs, system, session.cancellation
                )
                for event in stream:
                    self._checkpoint(session, generation, started)
                    if isinstance(event, TextDelta):
                        deltas.append(event.text)
                        if in_answer:
                            continue
                        joined = "".join(deltas)
                        if marker_position(joined) is None:
                            continue
                        in_answer = True
                    elif isinstance(event, ToolCall):
                        calls.append(event)
                    elif isinstance(event, Done):
                        break
            except Exception:
                self._checkpoint(session, generation, started)
                raise
            if not calls or final:
                break
            rounds += 1
            messages.append(
                ChatMessage(role="assistant", content=None, tool_calls=tuple(calls))
            )
            for call in calls:
                self._checkpoint(session, generation, started)
                yield Event("status", {"state": "tool", "tool": call.name})
                order += 1
                card, result = call_tool(context, call)
                self._checkpoint(session, generation, started)
                cards.append(card)
                yield Event(
                    "card",
                    {
                        "scene_id": scene_id,
                        "card_id": f"c-{order:02d}",
                        "order": order,
                        "tool": call.name,
                        "args": dict(call.args),
                        "card": card.as_dict(),
                    },
                )
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=call.id,
                    )
                )
        yield from compose(
            self._client,
            self._store,
            self._disk,
            context,
            console,
            session,
            scene_id,
            question,
            messages,
            system,
            cards,
            deltas,
            rounds,
            int((self._clock() - started) * 1000),
        )
