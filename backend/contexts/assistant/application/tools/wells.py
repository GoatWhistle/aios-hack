from __future__ import annotations

import re
from typing import Any, Mapping

from backend.contexts.assistant.infrastructure.artifacts import ArtifactError, RunError
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.schemas.wells import MAX_SERIES_STEP
from backend.contexts.assistant.application.tools.labels import (
    METRIC_LABELS,
    METRIC_UNITS,
    pick,
    title,
)

SPARK_WINDOW = 24
SERIES_METRICS: tuple[str, ...] = (
    "liquid_rate",
    "injection_rate",
    "watercut",
    "bhp",
)


def _spark(context: ToolContext, well: str, step: int) -> list[dict[str, Any]]:
    rows = context.index().require_well(well)
    start = max(0, step - SPARK_WINDOW + 1)
    points: list[dict[str, Any]] = []
    for value in range(start, step + 1):
        row = rows.steps.get(value)
        if row is None:
            continue
        points.append({"step": value, "value": row["liquid_rate"]})
    return points


def well_snapshot(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    well = str(arguments["well"])
    try:
        index = context.index()
        step = context.resolve_step(arguments.get("step"))
        rows = index.require_well(well)
    except ArtifactError as error:
        raise ToolFailure(str(error)) from error
    row = rows.steps.get(step)
    if row is None:
        raise ToolFailure(
            f"well {well} has no row at step {step}: there is nothing to build a "
            "snapshot from"
        )
    npv_row = index.npv_by_well.get(well)
    payload: dict[str, Any] = {
        "well": well,
        "step": step,
        "date": index.dates[step],
        "role": row["role"],
        "availability": row["availability"],
        "operating_status": row["operating_status"],
        "liquid_rate": row["liquid_rate"],
        "injection_rate": row["injection_rate"],
        "watercut": row["watercut"],
        "bhp": row["bhp"],
        "setpoint": row["setpoint"],
        "npv": None if npv_row is None else npv_row["with_allocated_tax"],
        "npv_provenance": str((index.npv.get("meta") or {}).get("provenance", "unknown")),
        "npv_source_run_id": (index.npv.get("meta") or {}).get("source_run_id"),
        "spark": _spark(context, well, step),
    }
    return Card(
        type="well",
        title=title("well", context.lang, well=well),
        payload=payload,
        provenance=index.provenance(),
    )


def well_series(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    well = str(arguments["well"])
    metric = str(arguments["metric"])
    if metric not in SERIES_METRICS:
        raise ToolFailure(
            f"metric {metric} is not present in the showcase: available metrics "
            f"are {', '.join(SERIES_METRICS)}"
        )
    try:
        index = context.index()
        rows = index.require_well(well)
    except ArtifactError as error:
        raise ToolFailure(str(error)) from error
    # Bound default as well as explicit queries: the schema caps requested
    # indices, but a future showcase artifact may contain a longer horizon.
    last = min(index.step_count() - 1, MAX_SERIES_STEP)
    from_step = int(arguments.get("from_step") or 0)
    to_step = int(arguments["to_step"]) if arguments.get("to_step") is not None else last
    if from_step < 0 or to_step > last or from_step > to_step:
        raise ToolFailure(
            f"the step interval {from_step} to {to_step} does not fit the horizon "
            f"of scenario {index.scenario}: the available steps are 0 to {last}"
        )
    window = arguments.get("window")
    if window is not None:
        window_from, window_to = int(window[0]), int(window[1])
        if window_from > window_to or window_from < from_step or window_to > to_step:
            raise ToolFailure(
                f"highlight window {window_from} to {window_to} must fit inside the "
                f"requested series interval {from_step} to {to_step}"
            )
    series: list[dict[str, Any]] = []
    for step in range(from_step, to_step + 1):
        row = rows.steps.get(step)
        if row is None:
            continue
        series.append({"step": step, "date": index.dates[step], "value": row[metric]})
    if not series:
        raise ToolFailure(
            f"well {well} has no rows over the interval {from_step} to {to_step}: "
            "the series cannot be built"
        )
    label = pick(METRIC_LABELS, metric, context.lang)
    payload: dict[str, Any] = {
        "well": well,
        "metric": metric,
        "label": label,
        "unit": METRIC_UNITS[metric],
        "rows": series,
    }
    if window is not None:
        payload["window"] = [window_from, window_to]
    return Card(
        type="series",
        title=title("series", context.lang, label=label.capitalize(), well=well),
        payload=payload,
        provenance=index.provenance(),
    )


def compare_wells(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    a, b = str(arguments["a"]), str(arguments["b"])
    if a == b:
        raise ToolFailure("a well cannot be compared with itself; provide two different well identifiers")
    try:
        index = context.index()
        step = context.resolve_step(arguments.get("step"))
        step_row = index.require_step(step)
    except ArtifactError as error:
        raise ToolFailure(str(error)) from error
    rows = {
        str(row.get("well")): row
        for row in step_row.get("wells", ())
        if isinstance(row, Mapping) and row.get("well") is not None
    }
    missing = [well for well in (a, b) if well not in rows]
    if missing:
        raise ToolFailure(
            f"well(s) {', '.join(missing)} have no recorded state at step {step} in scenario {index.scenario}"
        )

    def side(well: str) -> dict[str, Any]:
        row = rows[well]
        npv_row = index.npv_by_well.get(well)
        return {
            "well": well,
            "role": row.get("role"),
            "availability": row.get("availability"),
            "operating_status": row.get("operating_status"),
            "liquid_rate": row.get("liquid_rate"),
            "injection_rate": row.get("injection_rate"),
            "watercut": row.get("watercut"),
            "bhp": row.get("bhp"),
            "setpoint": row.get("setpoint"),
            "npv_whole_horizon": None if npv_row is None else npv_row.get("with_allocated_tax"),
        }

    connection = None
    graph_meta = index.graph.get("meta") or {}
    if graph_meta.get("lambda_measured") is True:
        for edge in index.edges_by_well.get(a, ()):
            neighbour = edge.get("producer") if edge.get("injector") == a else edge.get("injector")
            if str(neighbour) == b:
                connection = {
                    "measured": True,
                    "weight": edge.get("weight"),
                    "lag_months": graph_meta.get("lag_months"),
                    "provenance": graph_meta.get("provenance", "unknown"),
                }
                break
    run_id = arguments.get("run_id") or context.console.run_id
    timeline_meta = index.timeline.get("meta") or {}
    state_response_hash = timeline_meta.get("response_hash") if isinstance(timeline_meta, Mapping) else None
    recorded: dict[str, Any] = {
        "run_id": run_id,
        "status": "not-checked" if run_id is None else "checked",
        "source_alignment": "not-checked" if run_id is None else "unverified",
        "state_source_run_id": timeline_meta.get("source_run_id") if isinstance(timeline_meta, Mapping) else None,
        "state_response_hash": state_response_hash,
        "decision_response_hash": None,
        "pairwise_preference": "not-recorded",
        "wells": {},
        "well_constraints": {"status": "not-checked", "outages": {}},
    }
    if isinstance(run_id, str):
        try:
            run = context.run_store().read(run_id)
            decision_response_hash = (run.origin or {}).get("feedback_response_hash")
            evaluation_response_hash = (run.economics or {}).get("source_response_hash")
            recorded["decision_response_hash"] = decision_response_hash
            recorded["evaluation_response_hash"] = evaluation_response_hash
            if (
                isinstance(state_response_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", state_response_hash)
                and isinstance(decision_response_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", decision_response_hash)
            ):
                recorded["source_alignment"] = (
                    "same-response"
                    if state_response_hash == decision_response_hash
                    else "different-response"
                )
            constraints = run.verified_constraints()
            if constraints is None:
                recorded["well_constraints"]["status"] = "not-recorded"
            else:
                recorded["well_constraints"] = {
                    "status": "verified",
                    "constraints_hash": run.manifest.get("constraints_hash"),
                    "outages": {
                        well: [
                            outage for outage in constraints.get("well_outages", [])
                            if isinstance(outage, Mapping)
                            and outage.get("well") == well
                            and isinstance(outage.get("control_step_from"), int)
                            and isinstance(outage.get("control_step_to"), int)
                            and outage["control_step_from"] <= step <= outage["control_step_to"]
                        ]
                        for well in (a, b)
                    },
                }
            for well in (a, b):
                evidence = run.decision_evidence(well, step)
                recorded["wells"][well] = {
                    "recorded": evidence is not None,
                    "rule_facts": evidence.get("rule_facts", []) if evidence else [],
                    "hierarchy_proposed_events": evidence.get("hierarchy_proposed_events", []) if evidence else [],
                    "final_events": evidence.get("final_schedule_events", []) if evidence else [],
                    "group_allocations": evidence.get("group_allocations", []) if evidence else [],
                    "field_injection_limit_m3_per_day": evidence.get("field_injection_limit_m3_per_day") if evidence else None,
                }
        except (RunError, ToolFailure):
            recorded["status"] = "run-evidence-unavailable"
    delta_values = {
        metric: (
            float(rows[b][metric]) - float(rows[a][metric])
            if isinstance(rows[b].get(metric), (int, float))
            and not isinstance(rows[b].get(metric), bool)
            and isinstance(rows[a].get(metric), (int, float))
            and not isinstance(rows[a].get(metric), bool)
            else None
        )
        for metric in ("liquid_rate", "injection_rate", "watercut", "bhp", "setpoint")
    }
    npv_a, npv_b = index.npv_by_well.get(a), index.npv_by_well.get(b)
    delta_values["npv_whole_horizon"] = (
        float(npv_b["with_allocated_tax"]) - float(npv_a["with_allocated_tax"])
        if npv_a is not None and npv_b is not None else None
    )
    payload = {
        "scenario": index.scenario,
        "step": step,
        "date": index.dates[step],
        "a": side(a),
        "b": side(b),
        "deltas_b_minus_a": delta_values,
        "npv_provenance": str((index.npv.get("meta") or {}).get("provenance", "unknown")),
        "npv_source_run_id": (index.npv.get("meta") or {}).get("source_run_id"),
        "direct_connection": connection,
        "decision_evidence": recorded,
        "alternative_status": "state-comparison-only",
        "comparison_note": "Recorded state comparison only. No pairwise algorithm preference or causal effect is established.",
    }
    return Card(
        type="well-comparison",
        title=title("well_comparison", context.lang, a=a, b=b),
        payload=payload,
        provenance=index.provenance(),
    )
