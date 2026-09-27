from __future__ import annotations

from typing import Any, Iterator, Sequence

from backend.contexts.assistant.application.answer import split_answer
from backend.contexts.assistant.application.caption import (
    code_sources,
    doc_numbers,
    guard_answer_text,
    guard_with_retry,
)
from backend.contexts.assistant.domain.guard import (
    guard_decision_claims,
    guard_context_references,
    guard_plan_status,
    guard_run_references,
    guard_tool_failure_claims,
)
from backend.contexts.assistant.application.orchestrator_events import Event
from backend.contexts.assistant.application.suggestions import build_suggestions
from backend.contexts.assistant.application.tools import error_card, run_tool
from backend.contexts.assistant.application.tools.context import (
    Card,
    ConsoleContext,
    ToolContext,
    ToolFailure,
)
from backend.contexts.assistant.application.tools.registry import ToolInputError
from backend.contexts.assistant.domain.session import Exchange, Session, summary_request
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore, RunError
from backend.contexts.assistant.infrastructure.llm.chat import ChatClient
from backend.contexts.assistant.infrastructure.llm.chat_events import (
    ChatMessage,
    Done,
    TextDelta,
    ToolCall,
)
from backend.contexts.assistant.infrastructure.session_store import SessionDisk


def live_status(context: ToolContext) -> dict[str, Any] | None:
    try:
        card = run_tool("system_status", context, {})
    except Exception:
        return None
    return dict(card.payload)


def evidence_of(context: ToolContext) -> tuple[Any, ...]:
    if context.console.run_id is None:
        return ()
    try:
        record = context.run_store().read(context.console.run_id)
    except (ToolFailure, RunError):
        return ()
    return record.documents()


def call_tool(context: ToolContext, call: ToolCall) -> tuple[Card, Any]:
    try:
        card = run_tool(call.name, context, call.args)
    except TimeoutError:
        raise
    except (ToolFailure, ToolInputError) as error:
        return error_card(call.name, str(error), context.lang), {
            "error": str(error)
        }
    except Exception as error:
        return error_card(call.name, str(error), context.lang), {
            "error": str(error)
        }
    result = _model_payload(card)
    return card, result


def _model_payload(card: Card) -> dict[str, Any]:
    """Keep UI-only and confirmation data out of model prose and claim guards."""
    result = dict(card.payload)
    result.pop("run_series", None)
    if card.type == "case-proposal":
        result.pop("constraints", None)
        result.pop("base_constraints", None)
        result.pop("request_id", None)
    elif card.type == "alternative-proposal":
        result.pop("request_id", None)
    return result


def compress_session(
    client: ChatClient, disk: SessionDisk | None, session: Session, system: str
) -> None:
    pending = session.pending_summary()
    if not pending:
        return
    request = summary_request(pending)
    if session.summary_text:
        request = (
            f"Прежняя справка: {session.summary_text}\n\n{request}"
        )
    collected: list[str] = []
    try:
        for event in client.stream(
            [ChatMessage(role="user", content=request)], (), system
        ):
            if isinstance(event, TextDelta):
                collected.append(event.text)
            elif isinstance(event, Done):
                break
    except Exception:
        session.absorb_summary(session.summary_text)
        return
    session.absorb_summary("".join(collected).strip())
    if disk is not None and session.summary_text:
        try:
            disk.set_summary(session.session_id, session.summary_text)
        except Exception:
            return


def compose(
    client: ChatClient,
    store: ArtifactStore,
    disk: SessionDisk | None,
    context: ToolContext,
    console: ConsoleContext,
    session: Session,
    scene_id: str,
    question: str,
    messages: list[ChatMessage],
    system: str,
    cards: Sequence[Card],
    deltas: Sequence[str],
    rounds: int,
    elapsed_ms: int,
) -> Iterator[Event]:
    yield Event("status", {"state": "composing"})
    guarded_payloads = [_model_payload(card) for card in cards]
    evidence = tuple(doc_numbers(guarded_payloads))
    reference_evidence: tuple[Any, ...] = (*guarded_payloads, *evidence)
    try:
        active_index = context.index()
        reference_evidence += ({
            "known_wells": tuple(active_index.by_well),
            "known_steps": tuple(range(active_index.step_count())),
            "known_dates": active_index.dates,
        },)
    except Exception:
        pass
    split = split_answer("".join(deltas))
    guarded = guard_with_retry(
        client, messages, system, split.caption, guarded_payloads, evidence
    )
    if guarded.warning is not None:
        yield Event("warning", guarded.warning)
    checked_caption_refs = guard_run_references(
        guarded.result.text, reference_evidence, context.lang
    )
    if not checked_caption_refs.ok:
        yield Event("warning", {"code": "run-reference-unverified"})
    checked_caption_context = guard_context_references(
        checked_caption_refs.text, reference_evidence, context.lang
    )
    if not checked_caption_context.ok:
        yield Event("warning", {"code": "context-reference-unverified"})
    status_caption = guard_plan_status(checked_caption_context.text, guarded_payloads, context.lang)
    checked_caption = guard_decision_claims(status_caption.text, guarded_payloads, context.lang)
    checked_caption_failure = guard_tool_failure_claims(checked_caption.text, cards, context.lang)
    if not status_caption.ok:
        yield Event("warning", {"code": "plan-status-conflict"})
    if not checked_caption.ok:
        yield Event("warning", {"code": "decision-claim-unverified"})
    if not checked_caption_failure.ok:
        yield Event("warning", {"code": "tool-result-unverified"})
    yield Event(
        "caption",
        {"scene_id": scene_id, "text": checked_caption_failure.text, "guarded": True},
    )
    answer_text = ""
    if split.answer:
        checked = guard_answer_text(
            split.answer, guarded_payloads, evidence, code_sources(guarded_payloads)
        )
        for warning in checked.warnings:
            yield Event("warning", warning)
        checked_answer_refs = guard_run_references(
            checked.text, reference_evidence, context.lang
        )
        if not checked_answer_refs.ok:
            yield Event("warning", {"code": "run-reference-unverified"})
        checked_answer_context = guard_context_references(
            checked_answer_refs.text, reference_evidence, context.lang
        )
        if not checked_answer_context.ok:
            yield Event("warning", {"code": "context-reference-unverified"})
        answer_text = checked_answer_context.text
        status_answer = guard_plan_status(answer_text, guarded_payloads, context.lang)
        checked_answer = guard_decision_claims(status_answer.text, guarded_payloads, context.lang)
        checked_answer_failure = guard_tool_failure_claims(checked_answer.text, cards, context.lang)
        if not status_answer.ok:
            yield Event("warning", {"code": "plan-status-conflict"})
        if not checked_answer.ok:
            yield Event("warning", {"code": "decision-claim-unverified"})
        if not checked_answer_failure.ok:
            yield Event("warning", {"code": "tool-result-unverified"})
        answer_text = checked_answer_failure.text
        if answer_text:
            yield Event(
                "answer",
                {
                    "scene_id": scene_id,
                    "text": answer_text,
                    "guarded": True,
                },
            )
    session.remember(
        Exchange(
            question=question,
            card_types=tuple(card.type for card in cards),
            caption=checked_caption_failure.text,
            answer=answer_text,
        )
    )
    compress_session(client, disk, session, system)
    yield Event(
        "suggestions",
        {
            "items": build_suggestions(
                console,
                store,
                card_types=tuple(card.type for card in cards),
                history=session.questions(),
            )
        },
    )
    yield Event(
        "done",
        {
            "scene_id": scene_id,
            "tool_rounds": rounds,
            "elapsed_ms": elapsed_ms,
        },
    )
