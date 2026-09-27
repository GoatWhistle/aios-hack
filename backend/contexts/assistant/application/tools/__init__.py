from __future__ import annotations


from typing import Any, Callable, Mapping

from backend.contexts.assistant.application.tools import (
    cases,
    connectivity as connectivity_module,
    council,
    decisions,
    docs,
    fields,
    knowledge as knowledge_module,
    patterns,
    ranking,
    run_proposals,
    rules,
    run_history as run_history_module,
    runs,
    scenarios,
    system as system_module,
    wells,
)
from backend.contexts.assistant.application.tools.actions import build_action
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.decisions import NoTraceEntry
from backend.contexts.assistant.application.tools.labels import TOOL_NAMES, pick, title
from backend.contexts.assistant.application.tools.registry import (
    JOURNAL_TOOL,
    NO_TRACE_ENTRY,
    ToolInputError,
    definition,
    tool_specs,
    validate_arguments,
)

ToolFn = Callable[[ToolContext, Mapping[str, Any]], Card]

HANDLERS: Mapping[str, ToolFn] = {
    "draft_case": run_proposals.draft_case,
    "draft_alternative": run_proposals.draft_alternative,
    "well_snapshot": wells.well_snapshot,
    "well_series": wells.well_series,
    "compare_wells": wells.compare_wells,
    "field_metrics": fields.field_metrics,
    "field_events": fields.field_events,
    "explain_decision": rules.explain_decision,
    "decision_journal": decisions.explain_decision,
    "rank_wells": ranking.rank_wells,
    "rule_impact": rules.rule_impact,
    "connectivity": connectivity_module.connectivity,
    "compare_scenarios": scenarios.compare_scenarios,
    "find_patterns": patterns.find_patterns,
    "explain_term": knowledge_module.explain_term,
    "platform_guide": knowledge_module.platform_guide,
    "run_status": runs.run_status,
    "submission_summary": runs.submission_summary,
    "search_docs": docs.search_docs,
    "system_map": system_module.system_map,
    "system_status": system_module.system_status,
    "run_history": run_history_module.run_history,
    "run_detail": run_history_module.run_detail,
    "compare_runs": run_history_module.compare_runs,
    "case_constraints": cases.case_constraints,
    "council_step": council.council_step,
    "physics_report": run_history_module.physics_report,
}


def run_tool(
    name: str, context: ToolContext, arguments: Mapping[str, Any]
) -> Card:
    context.check_cancelled()
    handler = HANDLERS.get(name)
    if handler is None:
        raise ToolFailure(
            f"Jarvis has no tool named {name}: available tools are "
            f"{', '.join(sorted(HANDLERS))}"
        )
    checked = validate_arguments(name, arguments)
    card = handler(context, checked)
    context.check_cancelled()
    action = build_action(card.type, card.payload, context.scenario_name, card.provenance)
    if action is None:
        return card
    return Card(
        type=card.type,
        title=card.title,
        payload=card.payload,
        provenance=card.provenance,
        action=action,
    )


def error_card(name: str, message: str, lang: str = "ru") -> Card:
    try:
        card_type = definition(name).card_type
    except ToolInputError:
        card_type = "error"
    next_step = _error_next_step(name, lang, message)
    return Card(
        type="error",
        title=title("tool_failed", lang, tool=pick(TOOL_NAMES, name, lang)),
        payload={
            "tool": name,
            "message": message,
            "expected_card": card_type,
            "next_step": next_step,
        },
        provenance="none",
    )


def _error_next_step(name: str, lang: str, message: str = "") -> str:
    if name == "find_patterns" and "no anomaly" in message.casefold():
        return (
            "Расширьте интервал шагов или выберите другой поддержанный тип диагностики."
            if lang == "ru"
            else "Widen the step interval or choose another supported diagnostic pattern."
        )
    if name in {"well_snapshot", "well_series", "compare_wells", "rank_wells", "connectivity", "find_patterns", "explain_decision", "decision_journal", "council_step"}:
        return (
            "Проверьте выбранный сценарий, скважину и шаг в доступных данных; для записанных команд можно запросить журнал решений."
            if lang == "ru"
            else "Check the selected scenario, well and step against available data; use the decision journal for recorded commands."
        )
    if name in {"run_status", "submission_summary", "run_history", "run_detail", "compare_runs", "physics_report"}:
        return (
            "Запросите историю прогонов и выберите run ID из списка с доступными артефактами."
            if lang == "ru"
            else "Request run history and choose a run ID with available artifacts."
        )
    if name in {"search_docs", "explain_term", "platform_guide"}:
        return (
            "Уточните тему или переформулируйте запрос по документам и терминам проекта."
            if lang == "ru"
            else "Narrow the topic or rephrase the query using project documents and terminology."
        )
    if name == "system_map":
        return (
            "Запросите карту системы без фокуса, чтобы увидеть доступные компоненты."
            if lang == "ru"
            else "Request the system map without a focus to see available components."
        )
    if name in {"case_constraints", "draft_case", "draft_alternative"}:
        return (
            "Запросите список доступных кейсов или выберите известное имя кейса."
            if lang == "ru"
            else "Request the available cases or choose a known case name."
        )
    return (
        "Проверьте параметры запроса и доступность источников данных, затем уточните вопрос."
        if lang == "ru"
        else "Check the request parameters and data sources, then refine the question."
    )


__all__ = [
    "Card",
    "HANDLERS",
    "JOURNAL_TOOL",
    "NO_TRACE_ENTRY",
    "NoTraceEntry",
    "ToolContext",
    "ToolFailure",
    "ToolInputError",
    "error_card",
    "run_tool",
    "tool_specs",
]
