from __future__ import annotations

from typing import Any, Iterator, Sequence

from backend.contexts.assistant.application.answer import split_answer
from backend.contexts.assistant.application.chart_requests import journal_tool_preset
from backend.contexts.assistant.application.journal_explanation import journal_explanation
from backend.contexts.assistant.application.run_series_info import run_series_info
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
    guard_artifact_references,
    guard_delivery_claims,
    guard_chart_availability,
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
from backend.contexts.assistant.domain.session import Exchange, Session
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
    series = result.pop("run_series", None)
    if isinstance(series, dict):
        result["run_series_info"] = run_series_info(series)
    if card.type == "case-proposal":
        result.pop("constraints", None)
        result.pop("base_constraints", None)
        result.pop("request_id", None)
    elif card.type == "alternative-proposal":
        result.pop("request_id", None)
    return result


def provider_failure_journal_reply(cards: Sequence[Card], lang: str, *, timed_out: bool = True) -> tuple[str, str, str] | None:
    journals = [
        card for card in cards
        if card.type == "rule" and isinstance(card.payload.get("decision_summary"), dict)
        and card.payload.get("record_status")
    ]
    if len(journals) != 1:
        return None
    answer = journal_explanation(journals[0].payload, lang)
    if answer is None:
        return None
    caption = (
        "Модель не ответила вовремя; показан разбор записанного журнала."
        if lang == "ru" else
        "The model did not respond in time; the recorded journal facts are shown."
    )
    if not timed_out:
        caption = ("Модель недоступна; показан разбор записанного журнала."
                   if lang == "ru" else "The model is unavailable; the recorded journal facts are shown.")
    return caption, answer, journals[0].provenance


def compose_recorded_journal_failure(
    reply: tuple[str, str, str], store: ArtifactStore, console: ConsoleContext,
    session: Session, scene_id: str, question: str, rounds: int, elapsed_ms: int,
    card_types: tuple[str, ...], *, provider_status: str, provider_error_code: str,
) -> Iterator[Event]:
    """Finish a useful recorded response without another provider request."""
    caption, answer, provenance = reply
    yield Event("warning", {"code": provider_error_code, "fallback": "recorded-journal", "detail": caption})
    yield Event("caption", {"scene_id": scene_id, "text": caption, "guarded": True, "provenance": provenance, "fallback": True})
    yield Event("answer", {"scene_id": scene_id, "text": answer, "guarded": True, "provenance": provenance, "fallback": True})
    session.remember(Exchange(question=question, card_types=card_types, caption=caption, answer=answer))
    yield Event("suggestions", {"items": build_suggestions(console, store, card_types=card_types, history=session.questions())})
    yield Event("done", {
        "scene_id": scene_id, "tool_rounds": rounds, "elapsed_ms": elapsed_ms,
        "completion": "recorded-journal-fallback", "provider_status": provider_status, "provider_error_code": provider_error_code,
    })


def compress_session(disk: SessionDisk | None, session: Session) -> None:
    """Compact prompt memory locally; the full event archive stays unchanged."""
    if not session.pending_summary():
        return
    session.compact_memory()
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
    checked_caption_sources = guard_artifact_references(checked_caption_failure.text, reference_evidence, context.lang)
    checked_caption_delivery = guard_delivery_claims(checked_caption_sources.text, guarded_payloads, context.lang)
    checked_caption_chart = guard_chart_availability(checked_caption_delivery.text, guarded_payloads, context.lang)
    if not checked_caption_sources.ok:
        yield Event("warning", {"code": "artifact-reference-unverified"})
    if not checked_caption_delivery.ok:
        yield Event("warning", {"code": "delivery-claim-conflict"})
    if not checked_caption_chart.ok:
        yield Event("warning", {"code": "chart-availability-conflict"})
    if not status_caption.ok:
        yield Event("warning", {"code": "plan-status-conflict"})
    if not checked_caption.ok:
        yield Event("warning", {"code": "decision-claim-unverified"})
    if not checked_caption_failure.ok:
        yield Event("warning", {"code": "tool-result-unverified"})
    yield Event(
        "caption",
        {"scene_id": scene_id, "text": checked_caption_chart.text, "guarded": True},
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
        checked_answer_sources = guard_artifact_references(checked_answer_failure.text, reference_evidence, context.lang)
        checked_answer_delivery = guard_delivery_claims(checked_answer_sources.text, guarded_payloads, context.lang)
        checked_answer_chart = guard_chart_availability(checked_answer_delivery.text, guarded_payloads, context.lang)
        if not checked_answer_sources.ok:
            yield Event("warning", {"code": "artifact-reference-unverified"})
        if not checked_answer_delivery.ok:
            yield Event("warning", {"code": "delivery-claim-conflict"})
        if not checked_answer_chart.ok:
            yield Event("warning", {"code": "chart-availability-conflict"})
        if not status_answer.ok:
            yield Event("warning", {"code": "plan-status-conflict"})
        if not checked_answer.ok:
            yield Event("warning", {"code": "decision-claim-unverified"})
        if not checked_answer_failure.ok:
            yield Event("warning", {"code": "tool-result-unverified"})
        answer_text = checked_answer_chart.text
        # A generated draft that loses facts to a guard is not a usable
        # explanation. Render the recorded journal fields directly instead of
        # weakening guards or shipping blank measurements to the engineer.
        if checked.warnings or not checked_answer_context.ok or not checked_answer.ok:
            journals = [
                card.payload for card in cards
                if card.type == "rule" and isinstance(card.payload.get("decision_summary"), dict)
                and card.payload.get("record_status")
            ]
            if len(journals) == 1:
                recorded_answer = journal_explanation(journals[0], context.lang)
                if recorded_answer is not None:
                    answer_text = recorded_answer
        if answer_text:
            yield Event(
                "answer",
                {
                    "scene_id": scene_id,
                    "text": answer_text,
                    "guarded": True,
                },
            )
    if not split.answer and journal_tool_preset(question, console):
        journals = [card for card in cards if card.type == "rule"
                    and isinstance(card.payload.get("decision_summary"), dict)
                    and card.payload.get("record_status")]
        if len(journals) == 1:
            answer_text = journal_explanation(journals[0].payload, context.lang) or ""
            if answer_text:
                yield Event("answer", {"scene_id": scene_id, "text": answer_text,
                                       "guarded": True, "provenance": journals[0].provenance})
    session.remember(
        Exchange(
            question=question,
            card_types=tuple(card.type for card in cards),
            caption=checked_caption_chart.text,
            answer=answer_text,
        )
    )
    compress_session(disk, session)
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
