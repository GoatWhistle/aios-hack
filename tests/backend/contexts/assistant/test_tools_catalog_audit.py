from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.contexts.assistant.application.tools import cases, error_card, system as system_tools
from backend.contexts.assistant.application.tools.context import ConsoleContext, ToolContext, ToolFailure
from backend.contexts.assistant.application.tools import council as council_tools
from backend.contexts.assistant.application.tools.system import system_map
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore


def test_case_constraints_returns_source_and_unit_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: ArtifactStore
) -> None:
    (tmp_path / "competition-constraints.json").write_text(
        json.dumps({"infrastructure": {"bhp_producer_min_bar": 120}, "oil_limits": [{"well": "W1"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cases, "_config_root", lambda: tmp_path)
    context = ToolContext(store=store, console=ConsoleContext(lang="en"))

    card = cases.case_constraints(context, {})

    assert card.type == "constraints"
    assert card.provenance == "config"
    assert card.payload["source"].endswith("competition-constraints.json")
    pressure = next(item for item in card.payload["items"] if item["key"] == "bhp_producer_min_bar")
    assert pressure["value"] == 120
    assert pressure["unit"] == "bar"
    assert pressure["source"] == "competition-constraints.json"


def test_case_constraints_refuses_to_invent_missing_constraint_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: ArtifactStore
) -> None:
    monkeypatch.setattr(cases, "_config_root", lambda: tmp_path)
    with pytest.raises(ToolFailure, match="limits must not be invented"):
        cases.case_constraints(ToolContext(store=store), {})


def test_system_map_returns_nodes_and_rejects_unknown_focus(store: ArtifactStore) -> None:
    context = ToolContext(store=store)
    card = system_map(context, {})

    assert card.type == "system-map"
    assert card.payload["nodes"]
    assert card.payload["source"]
    with pytest.raises(ToolFailure, match="must not be invented"):
        system_map(context, {"focus": "made-up-component"})


def test_council_step_returns_recorded_hierarchy(
    monkeypatch: pytest.MonkeyPatch, store: ArtifactStore
) -> None:
    context = ToolContext(store=store, console=ConsoleContext(scenario="base", step=0))
    monkeypatch.setattr(council_tools, "_step_entry", lambda _index, _step: {
        "field": {"water_available_m3_per_day": 50, "injection_limit_m3_per_day": 40},
        "groups": [],
        "decisions": [],
        "agents_fired": ["FieldCoordinator"],
        "trace_entries_by_level": {},
    })

    card = council_tools.council_step(context, {})

    assert card.type == "council"
    assert card.payload["step"] == 0
    assert card.payload["date"] == store.scenario("base").dates[0]
    assert card.payload["source"] == "hierarchy.json"

def test_council_step_refuses_when_hierarchy_data_is_unavailable(store: ArtifactStore) -> None:
    context = ToolContext(store=store, console=ConsoleContext(scenario="base", step=0))
    with pytest.raises(ToolFailure, match="no-council-step"):
        council_tools.council_step(context, {})


def test_system_status_exposes_scenario_and_generation_time(store: ArtifactStore) -> None:
    context = ToolContext(store=store, console=ConsoleContext(scenario="base", step=0))

    card = system_tools.system_status(context, {})

    assert card.type == "status-board"
    assert card.payload["scenario"] == "base"
    assert card.payload["generated_at"]
    assert "champion" in card.payload and "last_run" in card.payload


def test_tool_failure_card_keeps_specific_reason_and_suggests_next_step() -> None:
    card = error_card("find_patterns", "the detectors found no anomaly", "en")

    assert card.type == "error"
    assert card.payload["message"] == "the detectors found no anomaly"
    assert card.payload["next_step"] == (
        "Widen the step interval or choose another supported diagnostic pattern."
    )
