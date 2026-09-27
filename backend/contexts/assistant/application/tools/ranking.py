from __future__ import annotations

from typing import Any, Mapping

from backend.contexts.assistant.infrastructure.artifacts import ArtifactError
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools.labels import (
    METRIC_LABELS,
    METRIC_UNITS,
    pick,
    title,
)

RANK_METRICS: tuple[str, ...] = (
    "npv",
    "watercut",
    "liquid_rate",
    "injection_rate",
)
DEFAULT_LIMIT = 10


def rank_wells(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    by = str(arguments["by"])
    if by not in RANK_METRICS:
        raise ToolFailure(
            f"wells cannot be ranked by {by}: available ranking metrics are "
            f"{', '.join(RANK_METRICS)}"
        )
    order = str(arguments.get("order") or ("asc" if by == "npv" else "desc"))
    if order not in ("asc", "desc"):
        raise ToolFailure(f"sort order {order} is not supported: use asc or desc")
    limit = int(arguments.get("limit") or DEFAULT_LIMIT)
    try:
        index = context.index()
        step = context.resolve_step(arguments.get("step"))
    except ArtifactError as error:
        raise ToolFailure(str(error)) from error
    values: list[tuple[str, float]] = []
    if by == "npv":
        for position, (well, row) in enumerate(index.npv_by_well.items()):
            if position % 256 == 0:
                context.check_cancelled()
            values.append((well, float(row["with_allocated_tax"])))
    else:
        for position, row in enumerate(index.timeline["steps"][step]["wells"]):
            if position % 256 == 0:
                context.check_cancelled()
            value = row.get(by)
            if value is None:
                continue
            values.append((str(row["well"]), float(value)))
    if not values:
        raise ToolFailure(
            f"metric {by} has no measurement at step {step} in scenario "
            f"{index.scenario}: the ranking cannot be built"
        )
    values.sort(key=lambda pair: pair[1], reverse=order == "desc")
    selected = values[:limit]
    total = sum(abs(value) for _, value in values)
    rows = [
        {
            "well": well,
            "value": value,
            "share": (abs(value) / total) if total > 0 else None,
        }
        for well, value in selected
    ]
    label = pick(METRIC_LABELS, by, context.lang)
    payload = {
        "by": by,
        "label": label,
        "unit": METRIC_UNITS[by],
        "order": order,
        # Per-well NPV is the recorded whole-horizon result, while operating
        # metrics are snapshots at the selected control step. Do not attach a
        # misleading step date to the horizon-wide ranking.
        "period": "whole_horizon" if by == "npv" else "control_step",
        "step": None if by == "npv" else step,
        "date": None if by == "npv" else index.dates[step],
        "total_count": len(values),
        "rows": rows,
    }
    provenance = index.provenance()
    if by == "npv":
        meta = index.npv.get("meta") or {}
        provenance = str(meta.get("provenance", "unknown"))
    return Card(
        type="well-list",
        title=title(
            f"rank_{order}", context.lang, count=len(rows), label=label
        ),
        payload=payload,
        provenance=provenance,
    )
