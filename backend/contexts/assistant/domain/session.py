from __future__ import annotations

from backend.contexts.assistant.domain.errors import (
    SessionError,
)

import json
import threading
import re
from dataclasses import dataclass, field
from typing import Sequence

from backend.contexts.assistant.domain.ports import SessionRecordStore
from backend.contexts.assistant.domain.session_events import restore_exchanges
from backend.contexts.assistant.domain.console_context import ConsoleContext
from backend.contexts.assistant.domain.cancellation import CancellationToken

HISTORY_LIMIT = 6
MAX_QUESTION_LENGTH = 600
ANSWER_EXCERPT = 300
SUMMARY_LIMIT = 1200
MEMORY_PREFIX = "Recorded exchange excerpts; omissions marked …; not new evidence:\n"


@dataclass(frozen=True, slots=True)
class Exchange:
    question: str
    card_types: tuple[str, ...]
    caption: str
    answer: str = ""

    def as_text(self) -> str:
        cards = ", ".join(self.card_types) if self.card_types else "none"
        lines = [f"Q: {_memory_excerpt(self.question, MAX_QUESTION_LENGTH)}",
                 f"Cards: {_memory_excerpt(cards, 180)}",
                 f"A: {_memory_excerpt(self.caption, ANSWER_EXCERPT)}"]
        if self.answer:
            lines.append(f"Detail: {_memory_excerpt(self.answer, ANSWER_EXCERPT)}")
        return "\n".join(lines)


@dataclass
class Session:
    session_id: str
    console: ConsoleContext = field(default_factory=ConsoleContext)
    history: list[Exchange] = field(default_factory=list)
    scene_serial: int = 0
    generation: int = 0
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    cancelled: bool = False
    running: bool = False
    summary_text: str = ""
    overflowed: list[Exchange] = field(default_factory=list)
    restored: bool = False

    def remember(self, exchange: Exchange) -> None:
        self.history.append(exchange)
        while len(self.history) > HISTORY_LIMIT:
            self.overflowed.append(self.history.pop(0))

    def next_scene_id(self) -> str:
        self.scene_serial += 1
        return f"s-{self.scene_serial:02d}"

    def questions(self) -> tuple[str, ...]:
        return tuple(
            exchange.question for exchange in (*self.overflowed, *self.history)
        )

    def summary(self) -> str:
        parts: list[str] = []
        if self.summary_text:
            parts.append(f"Summary of older exchanges: {self.summary_text}")
        parts.extend(exchange.as_text() for exchange in self.history)
        return "\n\n".join(parts)

    def pending_summary(self) -> tuple[Exchange, ...]:
        return tuple(self.overflowed)

    def compact_memory(self) -> None:
        """Keep bounded verbatim excerpts, never ask a model to rewrite facts.

        Full exchanges remain in the event archive; this is a prompt index, not
        an exhaustive factual summary. Whole JSON records prevent joining the
        ending of one observation to an unrelated later sentence.
        """
        if not self.overflowed:
            return
        records: list[str] = []
        if self.summary_text.startswith(MEMORY_PREFIX):
            records = self.summary_text[len(MEMORY_PREFIX):].splitlines()
        elif self.summary_text:
            records = [json.dumps({"legacy_summary": _memory_excerpt(self.summary_text, 800)}, ensure_ascii=False)]
        for exchange in self.overflowed:
            records.append(json.dumps({
                "question": _memory_excerpt(exchange.question, 180),
                "cards": _memory_excerpt(", ".join(exchange.card_types), 120),
                "caption": _memory_excerpt(exchange.caption, 300),
                "answer_excerpt": _memory_excerpt(exchange.answer, 250),
            }, ensure_ascii=False))
        retained: list[str] = []
        remaining = SUMMARY_LIMIT - len(MEMORY_PREFIX)
        for record in reversed(records):
            cost = len(record) + (1 if retained else 0)
            if cost > remaining:
                break
            retained.append(record)
            remaining -= cost
        self.summary_text = MEMORY_PREFIX + "\n".join(reversed(retained))
        self.overflowed.clear()

    def absorb_summary(self, text: str) -> None:
        cleaned = text.strip()[:SUMMARY_LIMIT]
        if cleaned:
            self.summary_text = cleaned
        self.overflowed.clear()


class SessionStore:
    def __init__(
        self,
        history_limit: int = HISTORY_LIMIT,
        disk: SessionRecordStore | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._history_limit = history_limit
        self._disk = disk

    @property
    def disk(self) -> SessionRecordStore | None:
        return self._disk

    def get(self, session_id: str, console: ConsoleContext | None = None) -> Session:
        if not session_id:
            raise SessionError(
                "session_id is empty: Jarvis keeps the console context and the "
                "recent exchanges per session and cannot serve a request without it"
            )
        expired = self._disk is not None and self._disk.meta(session_id) is None
        with self._lock:
            session = self._sessions.get(session_id)
            if (
                expired
                and session is not None
                and session.restored
                and (session.history or session.overflowed or session.summary_text)
            ):
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
            if session is None:
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
            if console is not None:
                session.console = console
        if not session.restored:
            session.restored = True
            self._restore(session)
        return session

    def _restore(self, session: Session) -> None:
        if self._disk is None:
            return
        meta = self._disk.meta(session.session_id)
        if meta is None:
            return
        session.summary_text = meta.summary
        # The archive watermark survives bounded event replay and unanswered
        # requests. Exchange count is not the identity of the last scene.
        session.scene_serial = max(session.scene_serial, int(getattr(meta, "scenes", 0)))
        try:
            events = self._disk.events(session.session_id)
        except Exception:
            return
        restored_rows = restore_exchanges(events)
        serials = [
            int(match.group(1))
            for event in events
            if (match := re.fullmatch(r"s-(\d+)", str(event.get("scene_id", ""))))
        ]
        session.scene_serial = max(session.scene_serial, len(restored_rows), *serials)
        for row in restored_rows:
            session.remember(
                Exchange(
                    question=str(row["question"]),
                    card_types=tuple(row["card_types"]),
                    caption=str(row["caption"]),
                    answer=str(row["answer"]),
                )
            )
        session.overflowed.clear()

    def start(self, session_id: str, console: ConsoleContext) -> tuple[Session, int]:
        session = self.get(session_id, console)
        with self._lock:
            previous_token = session.cancellation
            cancel_previous = session.running
            session.generation += 1
            session.cancelled = False
            session.running = True
            session.cancellation = CancellationToken()
            generation = session.generation
        if cancel_previous:
            previous_token.cancel()
        return session, generation

    def finish(self, session_id: str, generation: int | None = None) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and (
                generation is None or session.generation == generation
            ):
                session.running = False

    def cancel(self, session_id: str, generation: int | None = None) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or (
                generation is not None and session.generation != generation
            ):
                return False
            session.cancelled = True
            token = session.cancellation
        token.cancel()
        return True

    def is_cancelled(self, session_id: str, generation: int | None = None) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            return bool(
                session is None
                or session.cancelled
                or (generation is not None and session.generation != generation)
            )

    def count(self) -> int:
        if self._disk is not None:
            return max(self._disk.count(), len(self._sessions))
        with self._lock:
            return len(self._sessions)

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


def check_question(question: str) -> str:
    text = (question or "").strip()
    if not text:
        raise SessionError(
            "the question is empty: nothing to answer, the console offers "
            "suggestion chips instead of sending an empty request"
        )
    if len(text) > MAX_QUESTION_LENGTH:
        raise SessionError(
            f"the question is {len(text)} characters long while the limit is "
            f"{MAX_QUESTION_LENGTH}: shorten it, a long prompt costs latency "
            "without adding precision"
        )
    return text


def summary_request(exchanges: Sequence[Exchange]) -> str:
    lines = [exchange.as_text() for exchange in exchanges]
    return (
        "Сожми эти обмены диалога в короткую справку для памяти: о чём "
        "спрашивали, какие карточки показывали и что было отвечено. Не больше "
        "четырёх фраз, без чисел, которых нет в тексте, без инструментов. "
        "Верни только текст справки.\n\n" + "\n\n".join(lines)
    )


def _memory_excerpt(text: str, limit: int) -> str:
    if len(json.dumps(text, ensure_ascii=False)) - 2 <= limit:
        return text
    prefix = text[:limit - 1]
    while len(json.dumps(prefix, ensure_ascii=False)) - 2 > limit - 1:
        prefix = prefix[:-1]
    boundary = max((index for index, char in enumerate(prefix) if char.isspace()), default=-1)
    return (prefix[:boundary].rstrip() if boundary >= 0 else "") + "…"
