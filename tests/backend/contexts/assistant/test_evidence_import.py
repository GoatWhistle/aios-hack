from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.contexts.assistant.infrastructure.artifacts.runs import (
    EVIDENCE_INDEX_FILE,
    import_decision_evidence,
)
from backend.contexts.assistant.domain.errors import RunError
from backend.shared.hashing import canonical_schedule_hash


def _run_directory(root: Path, response_hash: str) -> Path:
    run = root / "run-a"
    run.mkdir(parents=True)
    schedule = {
        "initial_state": {"wells": {}},
        "fixed_deck_events": [],
        "control_events": [],
        "meta": {"n_intervals": 1, "n_control_dates": 2, "t0": "2000-01-01"},
    }
    schedule_hash = canonical_schedule_hash(
        schedule["initial_state"],
        schedule["fixed_deck_events"],
        schedule["control_events"],
    )
    (run / "manifest.json").write_text(
        json.dumps({"run_id": "run-a", "schedule_hash": schedule_hash}), encoding="utf-8"
    )
    schedule_dir = run / "schedule"
    schedule_dir.mkdir()
    (schedule_dir / "schedule.json").write_text(json.dumps(schedule), encoding="utf-8")
    (run / "well-explanations.json").write_text(
        json.dumps({
            "run_id": "run-a",
            "schedule_hash": schedule_hash,
            "explanations": [{
                "well": "19",
                "step": 0,
                "input_observation": {},
                "rule_facts": [],
                "hierarchy_proposed_events": [],
                "final_schedule_events": [],
                "group_allocations": [],
                "journal_line": 0,
                "note": "",
            }],
        }),
        encoding="utf-8",
    )
    (run / "economics").mkdir()
    (run / "economics" / "result.json").write_text(
        json.dumps({"source_response_hash": response_hash}), encoding="utf-8"
    )
    observation = run / "observation" / schedule_hash
    observation.mkdir(parents=True)
    (observation / "response.json").write_text(
        json.dumps({
            "response_hash": response_hash,
            "interval_response": [{"well": "19", "control_step": 0}],
        }),
        encoding="utf-8",
    )
    deck = run / "opm" / "deck"
    deck.mkdir(parents=True)
    (deck / "Model_Z_sch.inc").write_text("1 JAN 2000 /\n1 FEB 2000 /\n", encoding="utf-8")
    return run


def test_import_index_records_verified_response_provenance(tmp_path: Path) -> None:
    response_hash = "a" * 64
    run = _run_directory(tmp_path, response_hash)

    assert import_decision_evidence(run) == 1
    index = json.loads((run / EVIDENCE_INDEX_FILE).read_text(encoding="utf-8"))
    assert index["response_status"] == "verified"
    assert index["response_hash"] == response_hash
    assert index["date_axis_status"] == "verified"
    assert index["dates"] == ["2000-01-01"]
    evidence = (run / "decision-evidence.jsonl").read_text(encoding="utf-8")
    assert '"date":"2000-01-01"' in evidence
    assert '"date_axis_status":"verified"' in evidence


def test_import_rejects_response_that_does_not_match_economics(tmp_path: Path) -> None:
    run = _run_directory(tmp_path, "a" * 64)
    response_path = next(run.glob("observation/*/response.json"))
    response_path.write_text(json.dumps({"response_hash": "b" * 64}), encoding="utf-8")

    with pytest.raises(RunError, match="source response hash does not match"):
        import_decision_evidence(run)


def test_import_rejects_malformed_decision_schema(tmp_path: Path) -> None:
    run = _run_directory(tmp_path, "a" * 64)
    source = run / "well-explanations.json"
    packed = json.loads(source.read_text(encoding="utf-8"))
    del packed["explanations"][0]["input_observation"]
    source.write_text(json.dumps(packed), encoding="utf-8")

    with pytest.raises(RunError, match="invalid decision evidence schema"):
        import_decision_evidence(run)


def test_import_accepts_recorded_alternative_only_with_recorded_pairwise_evidence(tmp_path: Path) -> None:
    run = _run_directory(tmp_path, "a" * 64)
    source = run / "well-explanations.json"
    packed = json.loads(source.read_text(encoding="utf-8"))
    packed["explanations"][0]["alternative_status"] = "recorded-comparison"
    packed["explanations"][0]["alternative_comparison"] = {"recorded": True, "source": "decision-log"}
    source.write_text(json.dumps(packed), encoding="utf-8")

    assert import_decision_evidence(run) == 1
    record = json.loads((run / "decision-evidence.jsonl").read_text(encoding="utf-8"))
    assert record["alternative_status"] == "recorded-comparison"


def test_import_rejects_alternative_status_without_supporting_evidence(tmp_path: Path) -> None:
    run = _run_directory(tmp_path, "a" * 64)
    source = run / "well-explanations.json"
    packed = json.loads(source.read_text(encoding="utf-8"))
    packed["explanations"][0]["alternative_status"] = "state-comparison-only"
    source.write_text(json.dumps(packed), encoding="utf-8")

    with pytest.raises(RunError, match="supporting evidence"):
        import_decision_evidence(run)
