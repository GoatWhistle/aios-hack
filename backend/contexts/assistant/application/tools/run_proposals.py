"""Read-only previews for calculations requested in the Jarvis conversation.

The model can prepare a proposal, but only a person pressing the proposal card's
confirmation control may send it to the existing web-run API.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from backend.contexts.assistant.application.tools import cases
from backend.contexts.assistant.application.tools.context import Card, ToolContext, ToolFailure
from backend.contexts.runs.domain.errors import RunRequestError
from backend.shared.paths import repository_root
from backend.shared.settings import Settings


def _runs() -> Any:
    # WebRuns imports ArtifactStore, whose package imports the assistant. Keep
    # this boundary lazy so either service can be imported first.
    from backend.contexts.runs.application.web_runs import WebRuns

    configured = Settings.from_env().jarvis_web_runs
    root = configured or repository_root(Path.cwd()) / "out" / "web-runs"
    return WebRuns(root)


def draft_case(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    context.check_cancelled()
    request = str(arguments["request"])
    path = cases._config_root() / cases.COMPETITION_FILE
    constraints = cases._read(path)
    try:
        draft = _runs().draft({
            "request": request,
            "scenario": context.scenario_name,
            "constraints": constraints,
        })
    except RunRequestError as error:
        raise ToolFailure(str(error)) from error
    context.check_cancelled()
    rate_facts: dict[str, Any] = {}
    if draft.get("operation") == "set_annual_rate_limit":
        metric = "injection" if draft.get("section") == "injection_limits" else "production"
        rate_facts["proposed_rate"] = {
            "metric": metric,
            "value": draft["after"],
            "unit": "m3/day",
        }
        if draft.get("before") is not None:
            rate_facts["current_rate"] = {
                "metric": metric,
                "value": draft["before"],
                "unit": "m3/day",
            }
    return Card(
        type="case-proposal",
        title=("Черновик нового кейса" if context.lang == "ru" else "New case proposal"),
        payload={
            **draft,
            **rate_facts,
            "request_id": uuid.uuid4().hex,
            "request": request,
            "scenario": context.scenario_name,
            "base_source": str(path),
            "base_constraints": constraints,
            "budget_options": [10, 30, 120],
            "requires_confirmation": True,
        },
        provenance="config",
    )


def draft_alternative(context: ToolContext, arguments: Mapping[str, Any]) -> Card:
    context.check_cancelled()
    source_run_id = arguments.get("source_run_id") or context.console.run_id
    well = arguments.get("well") or context.console.selected_well
    control_step = arguments.get("control_step", context.console.step)
    if not source_run_id or not well or control_step is None:
        raise ToolFailure(
            "choose a saved sound source run, a producer well and a control step "
            "before requesting an alternative"
        )
    try:
        preview = _runs().draft_alternative({
            "source_run_id": source_run_id,
            "well": well,
            "control_step": control_step,
            "target_m3_per_day": arguments["target_m3_per_day"],
        })
    except RunRequestError as error:
        raise ToolFailure(str(error)) from error
    context.check_cancelled()
    return Card(
        type="alternative-proposal",
        title=("Черновик альтернативного действия" if context.lang == "ru" else "Alternative action proposal"),
        payload={
            **preview,
            "request_id": uuid.uuid4().hex,
            "requires_confirmation": True,
        },
        provenance="run-manifest",
    )
