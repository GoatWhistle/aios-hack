from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from backend.contexts.assistant.infrastructure.artifacts import (
    ALTERNATIVE_STATUSES,
    ArtifactError,
    RunError,
    ScenarioIndex,
)
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.labels import RULE_NAMES, pick, title
from backend.contexts.assistant.application.tools.registry import NO_TRACE_ENTRY
from backend.contexts.assistant.application.tools.rules import rule_statement

TRACE_META_KEY = "__meta__"


class NoTraceEntry(ToolFailure):
    default_code = NO_TRACE_ENTRY


def _finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def _feedback_comparison(
    context: ToolContext, run: Any, well: str, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    origin = run.origin or {}
    economics = run.economics or {}
    feedback_hash = origin.get("feedback_response_hash")
    feedback_run_id = origin.get("feedback_source_run_id")
    date = evidence.get("date")
    unavailable = {
        "status": "unavailable",
        "reason": "feedback-source-or-date-not-recorded",
        "well": well,
        "date": date,
    }
    if not isinstance(feedback_hash, str) or not isinstance(feedback_run_id, str) or not isinstance(date, str):
        return unavailable
    try:
        baseline = context.index()
        baseline_meta = baseline.timeline.get("meta") or {}
        if not isinstance(baseline_meta, Mapping):
            return {**unavailable, "reason": "feedback-source-provenance-is-unavailable"}
        if (
            baseline_meta.get("response_hash") != feedback_hash
            or baseline_meta.get("source_run_id") != feedback_run_id
        ):
            return {**unavailable, "reason": "active-scenario-is-not-the-recorded-feedback-source"}
        baseline_step = baseline.step_for_date(date)
        baseline_rows = baseline.require_step(baseline_step).get("wells", ())
        baseline_row = next(
            (row for row in baseline_rows if isinstance(row, Mapping) and str(row.get("well")) == well),
            None,
        )
        result_row = run.response_state_at_date(well, date)
    except (ArtifactError, RunError):
        return {**unavailable, "reason": "feedback-or-evaluation-row-is-unavailable"}
    if not isinstance(baseline_row, Mapping) or result_row is None:
        return {**unavailable, "reason": "feedback-or-evaluation-row-is-unavailable"}

    feedback_liquid = _finite_number(baseline_row.get("liquid_rate"))
    feedback_watercut = _finite_number(baseline_row.get("watercut"))
    result_oil = _finite_number(result_row.get("oil_rate"))
    feedback_injection = _finite_number(baseline_row.get("injection_rate"))
    result_injection = _finite_number(result_row.get("injection_rate"))
    metrics: dict[str, Any] = {}
    if feedback_liquid is not None and feedback_watercut is not None and result_oil is not None:
        feedback_oil = feedback_liquid * (1.0 - feedback_watercut)
        metrics["oil_rate_m3_per_day"] = {
            "feedback": feedback_oil,
            "evaluation": result_oil,
            "delta_evaluation_minus_feedback": result_oil - feedback_oil,
        }
    if feedback_injection is not None and result_injection is not None:
        metrics["injection_rate_m3_per_day"] = {
            "feedback": feedback_injection,
            "evaluation": result_injection,
            "delta_evaluation_minus_feedback": result_injection - feedback_injection,
        }
    if not metrics:
        return {**unavailable, "reason": "no-common-measured-metrics"}
    return {
        "status": "pointwise-state-comparison",
        "well": well,
        "date": date,
        "control_step": evidence.get("step"),
        "feedback_source_run_id": feedback_run_id,
        "feedback_response_hash": feedback_hash,
        "evaluation_run_id": run.run_id,
        "evaluation_response_hash": economics.get("source_response_hash"),
        "metrics": metrics,
        "interpretation": "descriptive comparison at the same well and date; not a causal effect or plan recommendation",
    }


def _target(context: ToolContext, arguments: Mapping[str, Any], run: Any = None) -> tuple[str, int]:
    requested_well = arguments.get("well")
    well = str(requested_well if requested_well is not None else context.console.selected_well or "")
    if not well:
        raise ToolFailure("select a well or specify the well number before requesting decision evidence")
    requested_step = arguments.get("step")
    if requested_step is not None:
        step = int(requested_step)
    elif context.console.step is not None:
        step = context.console.step
    elif context.console.date is not None:
        if run is not None:
            step = run.step_for_date(context.console.date)
        else:
            try:
                step = context.index().step_for_date(context.console.date)
            except ArtifactError as error:
                raise ToolFailure(str(error)) from error
    else:
        raise ToolFailure("select a control step or date before requesting decision evidence")
    return well, step


def _trace_provenance(index: ScenarioIndex) -> str:
    meta = index.trace.get(TRACE_META_KEY)
    if isinstance(meta, Mapping):
        value = meta.get("provenance")
        if isinstance(value, str):
            return value
    return index.provenance()


def _records(index: ScenarioIndex, well: str, step: int) -> Sequence[Mapping[str, Any]]:
    by_step = index.trace.get(well)
    if not isinstance(by_step, Mapping):
        raise NoTraceEntry(
            f"{NO_TRACE_ENTRY}: the journal of scenario {index.scenario} holds no "
            f"records for well {well}, so there is nothing to explain and nothing "
            "may be invented in their place"
        )
    found = by_step.get(str(step))
    if found is None:
        found = by_step.get(step)
    if not isinstance(found, Sequence) or isinstance(found, (str, bytes)) or not found:
        known = sorted((int(key) for key in by_step if str(key).isdigit()))
        listed = ", ".join(str(value) for value in known[:12]) if known else "none"
        raise NoTraceEntry(
            f"{NO_TRACE_ENTRY}: well {well} has no journal record at control step "
            f"{step} in scenario {index.scenario}: the available journal steps are "
            f"{listed}. The absence of a row does not establish why no record is available, "
            "so no reason is inferred"
        )
    return found


def _fact(record: Mapping[str, Any], lang: str, well: str, step: int) -> dict[str, Any]:
    rule = record.get("rule")
    if not isinstance(rule, str) or not rule:
        raise NoTraceEntry(
            f"{NO_TRACE_ENTRY}: a journal record of well {well} at step {step} "
            "carries no rule, so the decision cannot be attributed"
        )
    decision = record.get("decision")
    if not isinstance(decision, str) or not decision:
        raise NoTraceEntry(
            f"{NO_TRACE_ENTRY}: the record of rule {rule} for well {well} at step "
            f"{step} carries no decision, so there is nothing to report"
        )
    raw = record.get("inputs")
    inputs: dict[str, float] = {}
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            inputs[str(key)] = float(value)
    return {
        "rule": rule,
        "name": pick(RULE_NAMES, rule, lang),
        "statement": rule_statement(rule),
        "inputs": inputs,
        "decision": decision,
    }


def explain_decision(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    requested_run = arguments.get("run_id") or context.console.run_id
    if requested_run is not None:
        run_store = context.run_store()
        try:
            run = run_store.read(str(requested_run))
            well, step = _target(context, arguments, run)
            evidence = run.decision_evidence(well, step)
        except RunError as error:
            registered = run_store.registered_scenario(str(requested_run))
            reasons = registered.get("generation_reasons") if registered is not None else None
            if isinstance(reasons, Mapping) and reasons.get("available") is False:
                raise NoTraceEntry(
                    f"{NO_TRACE_ENTRY}: {requested_run} is registered as {registered.get('role')}; "
                    "its result is available, but no original run manifest or generation journal "
                    "is present locally, so no decision cause can be recovered"
                ) from error
            raise ToolFailure(str(error)) from error
        if evidence is None:
            if not (run.directory / "decision-evidence-index.json").is_file():
                raise NoTraceEntry(
                    f"{NO_TRACE_ENTRY}: run {run.run_id} has no imported recorded decision journal; "
                    "the calculation result may be available, but its generation reasons are not"
                )
            raise NoTraceEntry(
                f"{NO_TRACE_ENTRY}: run {run.run_id} has no input observation or decision evidence "
                f"for well {well} at step {step}; this does not establish whether an action was absent, "
                "so no reason is inferred"
            )
        meta = run.manifest
        validation = run.validation or {}
        opm = (run.opm_result or {}).get("run", {})
        status = {
            "opm_status": opm.get("status") if isinstance(opm, Mapping) else None,
            "run_status": meta.get("status"),
            "sound": validation.get("sound", meta.get("sound")),
            "dynamic_violations": validation.get("dynamic_violations"),
            "blocking_dynamic_violations": validation.get("blocking_dynamic_violations"),
        }
        observation = evidence.get("input_observation")
        observation = observation if isinstance(observation, Mapping) else {}
        proposals = evidence.get("hierarchy_proposed_events")
        proposals = proposals if isinstance(proposals, list) else []
        final_events = evidence.get("final_schedule_events")
        final_events = final_events if isinstance(final_events, list) else []
        run_series = run.decision_series(well)
        feedback_comparison = _feedback_comparison(context, run, well, evidence)
        connectivity_source: dict[str, Any] = {"available": False}
        try:
            map_index = context.index()
            edges = map_index.edges_by_well.get(well, ())
            graph_meta = map_index.graph.get("meta") or {}
            if graph_meta.get("lambda_measured") is True and edges:
                connectivity_source = {
                    "available": True,
                    "scenario": map_index.scenario,
                    "provenance": graph_meta.get("provenance", "unknown"),
                    "edge_count": len(edges),
                }
        except ArtifactError:
            pass
        payload = {
            "schema_version": evidence.get("schema_version", 1),
            "run_id": run.run_id,
            "scenario": evidence.get("scenario"),
            "well": well,
            "step": step,
            "date": evidence.get("date"),
            "date_source": evidence.get("date_source"),
            "date_status": "recorded" if evidence.get("date") else "control-date-axis-unavailable",
            "input_observation": evidence.get("input_observation"),
            "decision_summary": {
                "observed_setpoint_m3_per_day": observation.get("setpoint_m3_per_day"),
                "proposal_events": proposals,
                "final_events": final_events,
                "basis": "recorded-events; no causal inference",
            },
            "run_series": run_series,
            "connectivity_source": connectivity_source,
            "rule_facts": evidence.get("rule_facts", []),
            "hierarchy_proposed_events": evidence.get("hierarchy_proposed_events", []),
            "final_schedule_events": evidence.get("final_schedule_events", []),
            "record_status": "observation-and-evidence-recorded",
            "rule_activity_status": (
                "rules-recorded" if evidence.get("rule_facts") else "no-rules-fired-recorded"
            ),
            "hierarchy_action_status": (
                "proposal-recorded" if evidence.get("hierarchy_proposed_events") else "no-proposal-recorded"
            ),
            "final_action_status": (
                "final-events-recorded" if evidence.get("final_schedule_events") else "no-final-event-recorded"
            ),
            "projection_status": "not-recorded-separately",
            "group_allocations": evidence.get("group_allocations", []),
            "field_injection_limit_m3_per_day": evidence.get("field_injection_limit_m3_per_day"),
            "plan_check": status,
            "origin": run.origin,
            "evaluation_sources": {
                "surrogate_prediction": run.prediction,
                "economic_evaluation": run.economics,
                "opm_result": run.opm_result,
                "feedback_source_run_id": (run.origin or {}).get("feedback_source_run_id"),
                "feedback_response_hash": (run.origin or {}).get("feedback_response_hash"),
                "feedback_response_matches_evaluation": (
                    (run.origin or {}).get("feedback_response_hash") == (run.economics or {}).get("source_response_hash")
                    if (run.origin or {}).get("feedback_response_hash") and (run.economics or {}).get("source_response_hash")
                    else None
                ),
            },
            "feedback_comparison": feedback_comparison,
            "alternative_status": (
                evidence.get("alternative_status")
                if evidence.get("alternative_status") in ALTERNATIVE_STATUSES
                else "separate-calculation-required"
            ),
            "alternative_comparison": evidence.get("alternative_comparison"),
            "source": str(run.directory / "decision-evidence.jsonl"),
            "schedule_hash": meta.get("schedule_hash"),
            "journal_line": evidence.get("journal_line"),
            "note": evidence.get("note"),
        }
        return Card(
            type="rule",
            title=title("decision_evidence", context.lang, well=well, step=step),
            payload=payload,
            provenance="recorded-generation-journal",
        )
    well, step = _target(context, arguments)
    try:
        index = context.index()
        index.require_well(well)
        index.require_step(step)
    except ArtifactError as error:
        raise ToolFailure(str(error)) from error
    records = _records(index, well, step)
    facts = [_fact(record, context.lang, well, step) for record in records]
    head = facts[0]
    payload: dict[str, Any] = {
        "well": well,
        "step": step,
        "date": index.dates[step],
        "rule": head["rule"],
        "name": head["name"],
        "statement": head["statement"],
        "inputs": head["inputs"],
        "decision": head["decision"],
        "why": None,
        "facts": facts,
        "source": "trace.json",
    }
    return Card(
        type="rule",
        title=title("rule", context.lang, rule=head["rule"], well=well),
        payload=payload,
        provenance=_trace_provenance(index),
    )
