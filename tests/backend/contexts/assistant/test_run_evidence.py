from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.contexts.assistant.domain.errors import RunError
from backend.contexts.assistant.application.tools import run_tool
from backend.contexts.assistant.application.tools.decisions import _feedback_comparison
from backend.contexts.assistant.application.tools.context import ConsoleContext, ToolContext
from backend.contexts.assistant.infrastructure.artifacts.runs import (
    EVIDENCE_FILE,
    EVIDENCE_INDEX_FILE,
    RunRecord,
    RunStore,
)
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore


def make_record(directory: Path) -> RunRecord:
    directory.mkdir(parents=True)
    records: list[dict[str, Any]] = [
        {
            "schema_version": 1,
            "run_id": "run-a",
            "well": "19",
            "step": 0,
            "date": "2020-01-01",
            "input_observation": {
                "role": "PROD",
                "liquid_rate_m3_per_day": 30.0,
                "setpoint_m3_per_day": 25.0,
            },
            "final_schedule_events": [{"well": "19", "kind": "SET_LRAT", "value": 24.0}],
        },
        {
            "schema_version": 1,
            "run_id": "run-a",
            "well": "19",
            "step": 1,
            "date": "2020-02-01",
            "input_observation": {
                "role": "PROD",
                "liquid_rate_m3_per_day": 28.5,
                "setpoint_m3_per_day": 24.0,
            },
            "final_schedule_events": [],
        },
    ]
    offsets: dict[str, int] = {}
    encoded_records: list[bytes] = []
    position = 0
    for row in records:
        encoded = (json.dumps(row, separators=(",", ":")) + "\n").encode()
        offsets[f"{row['well']}:{row['step']}"] = position
        encoded_records.append(encoded)
        position += len(encoded)
    (directory / EVIDENCE_FILE).write_bytes(b"".join(encoded_records))
    (directory / EVIDENCE_INDEX_FILE).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-a",
                "schedule_hash": "schedule-hash",
                "control_steps": 2,
                "dates": ["2020-01-01", "2020-02-01"],
                "record_count": len(offsets),
                "offsets": offsets,
            }
        ),
        encoding="utf-8",
    )
    return RunRecord(
        run_id="run-a",
        directory=directory,
        manifest={"run_id": "run-a", "schedule_hash": "schedule-hash"},
        validation=None,
        constraints_report=None,
        submission=None,
        schedule_include=False,
    )


def test_indexed_decision_and_series_keep_recorded_sources(tmp_path: Path) -> None:
    run = make_record(tmp_path / "run-a")

    evidence = run.decision_evidence("19", 1)
    series = run.decision_series("19")

    assert evidence is not None
    assert evidence["date"] == "2020-02-01"
    assert series is not None
    assert series["input_source"] == "input_observation"
    assert series["schedule_source"] == "final_schedule_events"
    assert series["rows"] == [
        {"step": 0, "date": "2020-01-01", "input_rate": 30.0, "scheduled_rate": 24.0},
        {"step": 1, "date": "2020-02-01", "input_rate": 28.5, "scheduled_rate": 24.0},
    ]


def test_terminal_control_date_is_not_a_decision_step(tmp_path: Path) -> None:
    run = make_record(tmp_path / "run-a")
    with pytest.raises(RunError, match="terminal"):
        run.decision_evidence("19", 2)


def test_missing_journal_is_unavailable_not_an_empty_decision(tmp_path: Path) -> None:
    run = RunRecord(
        run_id="run-without-journal",
        directory=tmp_path / "run-without-journal",
        manifest={"run_id": "run-without-journal", "schedule_hash": "schedule-hash"},
        validation=None,
        constraints_report=None,
        submission=None,
        schedule_include=False,
    )
    assert run.decision_evidence("19", 0) is None
    assert run.decision_series("19") is None


def test_unindexed_step_is_not_reported_as_an_absent_action(tmp_path: Path) -> None:
    run = make_record(tmp_path / "run-a")
    path = run.directory / EVIDENCE_INDEX_FILE
    index = json.loads(path.read_text(encoding="utf-8"))
    del index["offsets"]["19:1"]
    path.write_text(json.dumps(index), encoding="utf-8")

    assert run.decision_evidence("19", 1) is None


def test_index_from_another_run_is_rejected(tmp_path: Path) -> None:
    run = make_record(tmp_path / "run-a")
    path = run.directory / EVIDENCE_INDEX_FILE
    index = json.loads(path.read_text(encoding="utf-8"))
    index["run_id"] = "run-b"
    path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(RunError, match="provenance"):
        run.decision_evidence("19", 0)


def test_run_backed_card_exposes_series_and_only_measured_map_action(
    tmp_path: Path, store: ArtifactStore
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-a"
    make_record(run_dir)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run-a", "schedule_hash": "schedule-hash", "sound": False}),
        encoding="utf-8",
    )
    context = ToolContext(
        store=store,
        console=ConsoleContext(scenario="base", step=1, selected_well="19", run_id="run-a"),
        runs=RunStore(runs_root),
    )

    card = run_tool("decision_journal", context, {})

    assert card.payload["run_id"] == "run-a"
    assert card.payload["plan_check"]["sound"] is False
    assert card.payload["run_series"]["rows"][1]["input_rate"] == 28.5
    assert card.payload["connectivity_source"]["available"] is True
    assert card.payload["connectivity_source"]["scenario"] == "base"
    assert card.action["companion_only"] is True
    assert card.action["run_id"] == "run-a"
    assert card.action["connections_available"] is True


def test_feedback_comparison_joins_matching_opm_responses_at_well_and_date(
    tmp_path: Path, store: ArtifactStore
) -> None:
    baseline = store.scenario("base")
    baseline_meta = baseline.timeline["meta"]
    step_row = baseline.require_step(0)["wells"][0]
    well = str(step_row["well"])
    date = baseline.dates[0]
    run_dir = tmp_path / "evaluation"
    run_dir.mkdir()
    schedule_hash = "a" * 64
    response_hash = "b" * 64
    run = RunRecord(
        run_id="evaluation",
        directory=run_dir,
        manifest={"run_id": "evaluation", "schedule_hash": schedule_hash},
        validation=None,
        constraints_report=None,
        submission=None,
        schedule_include=False,
        origin={
            "feedback_response_hash": baseline_meta["response_hash"],
            "feedback_source_run_id": baseline_meta["source_run_id"],
        },
        economics={"source_response_hash": response_hash},
    )
    response_dir = run_dir / "observation" / schedule_hash
    response_dir.mkdir(parents=True)
    (response_dir / "response.json").write_text(
        json.dumps({
            "response_hash": response_hash,
            "state_at_date": [{
                "deck_date_index": 0,
                "well": well,
                "oil_rate": 8.0,
                "injection_rate": 3.0,
            }],
        }),
        encoding="utf-8",
    )
    deck = run_dir / "opm" / "deck"
    deck.mkdir(parents=True)
    year, month, day = date.split("-")
    month_name = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()[int(month) - 1]
    (deck / "Model_Z_sch.inc").write_text(
        f"{int(day)} {month_name} {year} /\n", encoding="utf-8"
    )

    assert run.response_state_at_date(well, date) is not None
    comparison = _feedback_comparison(
        ToolContext(store=store), run, well, {"date": date, "step": 0}
    )

    assert comparison["status"] == "pointwise-state-comparison", comparison
    assert comparison["feedback_response_hash"] == baseline_meta["response_hash"]
    assert comparison["metrics"]["oil_rate_m3_per_day"]["evaluation"] == 8.0
    assert "not a causal effect" in comparison["interpretation"]
