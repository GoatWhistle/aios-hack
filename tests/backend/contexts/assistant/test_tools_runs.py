from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore, RunStore
from backend.contexts.assistant.domain.errors import RunError
from backend.shared.hashing import canonical_hash
from backend.contexts.assistant.infrastructure.knowledge import Knowledge
from backend.contexts.assistant.application.orchestrator import Orchestrator
from backend.contexts.assistant.application.tools import run_tool, tool_specs
from backend.contexts.assistant.application.tools.context import (
    ConsoleContext,
    ToolContext,
    ToolFailure,
)
from backend.contexts.assistant.application.tools.runs import NO_SUBMISSION
from backend.contexts.assistant.application.tools.run_history import (
    Located,
    _production_injection_breakdown,
)
from backend.contexts.runs.application.workflow import (
    RunProvenance,
    RunRequest,
    RunWorkflow,
    SUBMISSION_BUNDLE_FIELDS,
)
from backend.contexts.schedule.domain.schedule import (
    Availability,
    OperatingStatus,
    Role,
    Schedule,
    ScheduleMeta,
    WellState,
)
from backend.contexts.runs.domain.run_result import SubmissionBundle
from backend.contexts.assistant.infrastructure.llm.chat_events import ToolCall
from backend.contexts.assistant.infrastructure.llm.fake_chat import FakeChatClient

RUN_ID = "jarvis-run"
PREDICTED_NPV = 12_345_678.5
VERIFIED_NPV = 11_873_122_324.91
CLAIMED_NPV = 11_873_122_324.91
SEARCH_STRATEGY = "cmaes-restart"


@dataclass(frozen=True)
class FakeVerification:
    sound: bool
    npv_methodology: float | None


def sample_schedule() -> Schedule:
    return Schedule(
        meta=ScheduleMeta(wells=("W1",)),
        initial_state={
            "W1": WellState(
                Availability.AVAILABLE, Role.PROD, OperatingStatus.OPEN, 10.0
            )
        },
        fixed_deck_events=(),
        control_events=(),
    )


def make_run(
    runs_root: Path,
    run_id: str = RUN_ID,
    *,
    sound: bool = True,
    search_strategy: str | None = SEARCH_STRATEGY,
) -> Path:
    workflow = RunWorkflow(runs_root)
    workflow.verify(
        RunRequest(
            run_id,
            sample_schedule(),
            predicted_npv=PREDICTED_NPV,
            provenance=RunProvenance(
                deck_hash="c" * 64,
                constraints_hash="b" * 64,
                opm_image="openporousmedia/opmreleases:latest",
                git_commit="e" * 40,
                search_strategy=search_strategy,
                seed="7",
                iterations=240,
                self_consistent=True,
            ),
        ),
        lambda _schedule, _opm: FakeVerification(
            sound, VERIFIED_NPV if sound else None
        ),
    )
    return runs_root / run_id


def write_submission(run_dir: Path, claimed: float = CLAIMED_NPV) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    bundle = SubmissionBundle(
        canonical_schedule_hash=str(manifest["schedule_hash"]),
        content_hash_submission="d" * 64,
        claimed_npv_rub=claimed,
        source_run_id=str(manifest["run_id"]),
        response_hash="f" * 64,
        deck_hash=str(manifest["deck_hash"]),
        economics_config_hash="a" * 64,
        methodology_version_hash="9" * 64,
        constraints_hash=str(manifest["constraints_hash"]),
        opm_image=str(manifest["opm_image"]),
        git_commit=str(manifest["git_commit"]),
        created_at="2026-09-09T10:00:00+00:00",
    )
    document = {name: getattr(bundle, name) for name in SUBMISSION_BUNDLE_FIELDS}
    submission_dir = run_dir / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / "claimed_npv.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (submission_dir / "well_schedule.inc").write_bytes(b"SCHEDULE\n/\n")
    manifest["status"] = "ready_to_submit"
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document


def make(store: ArtifactStore, runs_root: Path, **console: object) -> ToolContext:
    return ToolContext(
        store=store,
        console=ConsoleContext(**console),
        runs=RunStore(runs_root),
    )


@pytest.fixture()
def runs_root(tmp_path: Path) -> Path:
    return tmp_path / "runs"


def test_both_run_tools_are_registered() -> None:
    names = {spec.name for spec in tool_specs()}
    assert "run_status" in names
    assert "submission_summary" in names
    assert "compare_wells" in names


def test_run_history_lists_manifest_runs_and_rejects_empty_status_filter(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root)
    context = make(store, runs_root)

    card = run_tool("run_history", context, {"limit": 10})

    assert card.type == "run-list"
    row = next(row for row in card.payload["rows"] if row["run_id"] == RUN_ID)
    assert row["source"]
    assert row["schedule_hash"]
    with pytest.raises(ToolFailure, match="there are no runs with status"):
        run_tool("run_history", context, {"status": "not-a-recorded-status"})


def test_physics_report_reads_recorded_checks_and_refuses_missing_report(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    context = make(store, runs_root)

    with pytest.raises(ToolFailure, match="there is no physics report"):
        run_tool("physics_report", context, {"run_id": RUN_ID})

    validation = run_dir / "validation"
    validation.mkdir(exist_ok=True)
    source = validation / "physics-report.json"
    source.write_text(
        json.dumps({
            "admissible": False,
            "checks": [
                {"id": "mass-balance", "status": "blocking", "detail": "mass mismatch"},
                {"id": "pressure", "status": "warning", "detail": "near limit"},
            ],
        }),
        encoding="utf-8",
    )

    card = run_tool("physics_report", context, {"run_id": RUN_ID})

    assert card.type == "physics"
    assert card.payload["admissible"] is False
    assert card.payload["blocking"] == 1
    assert card.payload["warnings"] == 1
    assert card.payload["checks"][0]["detail"] == "mass mismatch"
    assert card.payload["source"].endswith("physics-report.json")


def test_compare_wells_reports_same_step_states_without_claiming_preference(
    store: ArtifactStore,
) -> None:
    context = ToolContext(store=store, console=ConsoleContext(scenario="base", step=0))

    card = run_tool("compare_wells", context, {"a": "1", "b": "10"})

    assert card.type == "well-comparison"
    assert card.payload["step"] == 0
    assert card.payload["date"] == store.scenario("base").dates[0]
    assert card.payload["a"]["well"] == "1"
    assert card.payload["b"]["well"] == "10"
    assert card.payload["npv_provenance"] == store.scenario("base").npv["meta"]["provenance"]
    assert card.payload["npv_source_run_id"] == store.scenario("base").npv["meta"]["source_run_id"]
    assert card.payload["alternative_status"] == "state-comparison-only"
    assert card.payload["decision_evidence"]["pairwise_preference"] == "not-recorded"
    assert "causal effect" in card.payload["comparison_note"]


def test_compare_wells_reports_when_feedback_response_differs_from_showcase(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    origin_path = run_dir / "inputs" / "origin.json"
    origin_path.parent.mkdir(exist_ok=True)
    origin = {"feedback_response_hash": "f" * 64}
    origin_path.write_text(json.dumps(origin), encoding="utf-8")
    context = make(store, runs_root)

    card = run_tool("compare_wells", context, {"a": "1", "b": "10", "step": 0, "run_id": RUN_ID})

    assert card.payload["decision_evidence"]["source_alignment"] == "different-response"
    assert card.payload["decision_evidence"]["state_source_run_id"] == store.scenario("base").timeline["meta"]["source_run_id"]
    assert card.payload["decision_evidence"]["state_response_hash"] == store.scenario("base").timeline["meta"]["response_hash"]
    assert card.payload["decision_evidence"]["decision_response_hash"] == "f" * 64


def test_compare_wells_confirms_matching_response_sources(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    origin_path = run_dir / "inputs" / "origin.json"
    origin_path.parent.mkdir(exist_ok=True)
    response_hash = store.scenario("base").timeline["meta"]["response_hash"]
    origin = {"feedback_response_hash": response_hash}
    origin_path.write_text(json.dumps(origin), encoding="utf-8")

    card = run_tool(
        "compare_wells",
        make(store, runs_root, scenario="base", step=0, run_id=RUN_ID),
        {"a": "1", "b": "10", "step": 0, "run_id": RUN_ID},
    )

    assert card.payload["decision_evidence"]["source_alignment"] == "same-response"


def test_run_constraints_are_returned_only_with_matching_manifest_hash(
    runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    constraints = {"well_outages": [{"well": "W1", "control_step_from": 1, "control_step_to": 2}]}
    inputs = run_dir / "inputs"
    inputs.mkdir(exist_ok=True)
    (inputs / "constraints.json").write_text(json.dumps(constraints), encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["constraints_hash"] = canonical_hash(constraints)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    run = RunStore(runs_root).read(RUN_ID)
    assert run.verified_constraints() == constraints

    (inputs / "constraints.json").write_text(json.dumps({"well_outages": []}), encoding="utf-8")
    with pytest.raises(RunError, match="constraints provenance"):
        run.verified_constraints()


def test_run_status_reports_the_numbers_of_the_manifest(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    assert card.type == "run-status"
    assert card.payload["run_id"] == RUN_ID
    assert card.payload["status"] == manifest["status"] == "verified"
    assert card.payload["predicted_npv"] == manifest["predicted_npv"] == PREDICTED_NPV
    assert card.payload["verified_npv"] == manifest["verified_npv"] == VERIFIED_NPV
    assert card.payload["sound"] is True
    assert card.payload["search_strategy"] == SEARCH_STRATEGY
    assert card.payload["schedule_hash"] == manifest["schedule_hash"]
    assert card.provenance == "run-manifest"


def test_run_status_reports_the_recorded_violations(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    recorded = json.loads(
        (run_dir / "validation" / "result.json").read_text(encoding="utf-8")
    )

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    violations = card.payload["violations"]
    assert violations["recorded"] is True
    assert violations["dynamic"] == recorded["dynamic_violations"]
    assert violations["blocking"] == recorded["blocking_dynamic_violations"]


def test_run_status_exposes_well_and_step_for_recorded_violation(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    (run_dir / "validation" / "violations.json").write_text(json.dumps([
        {"kind": "WATERCUT_LIMIT_EXCEEDED", "control_step": 4, "well": "W1",
         "region": None, "value": 0.97, "detail": "water cut high", "blocking": True}
    ]))

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    locations = card.payload["violation_locations"]
    assert locations["recorded"] is True
    assert locations["rows"][0]["well"] == "W1"
    assert locations["rows"][0]["control_step"] == 4
    assert locations["rows"][0]["blocking"] is True


def test_run_status_does_not_claim_malformed_violation_locations_are_recorded(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    (run_dir / "validation" / "violations.json").write_text(json.dumps([
        {"kind": "WATERCUT_LIMIT_EXCEEDED", "control_step": True, "well": "W1"}
    ]))

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    locations = card.payload["violation_locations"]
    assert locations["recorded"] is False
    assert locations["rows"] == []
    assert "invalid control_step" in locations["reason"]


def test_run_status_reads_the_latest_run_without_an_identifier(
    store: ArtifactStore, runs_root: Path
) -> None:
    older = make_run(runs_root, "older")
    newer = make_run(runs_root, "newer")
    stamp = time.time()
    os.utime(older / "manifest.json", (stamp - 100.0, stamp - 100.0))
    os.utime(newer / "manifest.json", (stamp, stamp))

    card = run_tool("run_status", make(store, runs_root), {})

    assert card.payload["run_id"] == "newer"
    assert card.payload["status"] == "verified"


def test_run_status_refuses_a_run_that_does_not_exist(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root)

    with pytest.raises(ToolFailure) as error:
        run_tool("run_status", make(store, runs_root), {"run_id": "no-such-run"})

    message = str(error.value)
    assert "no-such-run" in message
    assert "was not found" in message
    assert RUN_ID in message


def test_run_status_refuses_when_no_run_was_ever_made(
    store: ArtifactStore, runs_root: Path
) -> None:
    runs_root.mkdir(parents=True)

    with pytest.raises(ToolFailure) as error:
        run_tool("run_status", make(store, runs_root), {})

    assert "no run with a manifest" in str(error.value)


def test_unrecorded_manifest_field_is_reported_as_not_recorded(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root, search_strategy=None)

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    assert card.payload["search_strategy"] is None
    assert "search_strategy" in card.payload["not_recorded"]
    assert "model_version" in card.payload["not_recorded"]
    assert card.payload["not_recorded_marker"] == "not-recorded"


def test_recorded_field_is_not_listed_as_missing(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root)

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    assert "search_strategy" not in card.payload["not_recorded"]
    assert "deck_hash" not in card.payload["not_recorded"]
    assert card.payload["provenance_fields"]["iterations"] == 240
    assert card.payload["provenance_fields"]["self_consistent"] is True


def test_unsound_run_reports_no_verified_npv_instead_of_zero(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root, "rejected-run", sound=False)

    card = run_tool("run_status", make(store, runs_root), {"run_id": "rejected-run"})

    assert card.payload["status"] == "rejected"
    assert card.payload["sound"] is False
    assert card.payload["verified_npv"] is None
    assert "verified_npv" in card.payload["not_recorded"]


def test_run_status_never_approves_a_rejected_plan_even_when_opm_ran(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root, "rejected-plan", sound=False)
    card = run_tool("run_status", make(store, runs_root), {"run_id": "rejected-plan"})

    acceptance = card.payload["acceptance"]
    assert acceptance["verdict"] == "rejected"
    assert acceptance["sound"] is False
    assert acceptance["npv_sources"]["predicted"]["source"].endswith("surrogate prediction")
    assert acceptance["npv_sources"]["verified"]["value"] is None


def test_run_status_marks_missing_constraint_checks_unknown(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root)
    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    acceptance = card.payload["acceptance"]
    assert acceptance["verdict"] == "unknown"
    assert acceptance["checks_recorded"] is False
    assert "not a single case constraint was checked" in acceptance["unverified_reason"]


def test_run_status_does_not_treat_empty_constraint_list_as_passed_checks(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    path = run_dir / "validation" / "constraints_report.json"
    path.write_text(json.dumps({"checks": []}), encoding="utf-8")
    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    assert card.payload["acceptance"]["verdict"] == "unknown"
    assert card.payload["acceptance"]["checks_recorded"] is False


def test_run_status_requires_successful_opm_for_recorded_check_acceptance(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    validation_path = run_dir / "validation" / "result.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["opm_status"] = "OK"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    constraints_path = run_dir / "validation" / "constraints_report.json"
    constraints_path.write_text(json.dumps({"checks": [
        {"constraint": "water_supply", "status": "checked", "n_violations": 0, "blocking": True}
    ]}), encoding="utf-8")

    accepted = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})
    assert accepted.payload["acceptance"]["verdict"] == "accepted_for_recorded_checks"

    validation["opm_status"] = "FAILED"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    rejected = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})
    assert rejected.payload["acceptance"]["verdict"] == "rejected"


def test_run_status_does_not_accept_when_opm_status_is_missing(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    (run_dir / "validation" / "constraints_report.json").write_text(json.dumps({"checks": [
        {"constraint": "water_supply", "status": "checked", "n_violations": 0, "blocking": True}
    ]}), encoding="utf-8")

    card = run_tool("run_status", make(store, runs_root), {"run_id": RUN_ID})

    assert card.payload["acceptance"]["verdict"] == "unknown"


def test_run_detail_conclusion_contains_recorded_plan_checks_and_sources(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    validation_path = run_dir / "validation" / "result.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["opm_status"] = "OK"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    (run_dir / "validation" / "constraints_report.json").write_text(json.dumps({
        "checks": [{
            "constraint": "watercut_limits", "status": "checked",
            "n_violations": 0, "blocking": True,
            "enforcement": "blocking", "detail": "watercut was checked on every step"
        }]
    }), encoding="utf-8")

    card = run_tool("run_detail", make(store, runs_root), {"run_id": RUN_ID})
    conclusion = card.payload["conclusion_markdown"]

    assert "## План" in conclusion
    assert "Стратегия: `cmaes-restart`" in conclusion
    assert "Происхождение/основание выбора: не записано" in conclusion
    assert "## Расчёт и допуск" in conclusion
    assert "OPM: `OK`" in conclusion
    assert "Прогноз суррогата" in conclusion and str(PREDICTED_NPV) in conclusion
    assert "ЧДД после проверки OPM" in conclusion and str(VERIFIED_NPV) in conclusion
    assert "## Физические проверки" in conclusion
    assert "watercut_limits: checked" in conclusion
    assert "watercut was checked on every step" in conclusion
    assert "## Источники" in conclusion and "/api/jarvis/run-artifacts/jarvis-run/manifest" in conclusion


def test_compare_runs_marks_missing_conditions_unverified_and_does_not_claim_causality(
    store: ArtifactStore, runs_root: Path
) -> None:
    left = make_run(runs_root, "compare-a")
    right = make_run(runs_root, "compare-b")
    for directory in (left, right):
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["case_id"] = "case-a"
        manifest["horizon"] = "2007-01-01/2024-07-01"
        manifest["normatives_sha256"] = "n" * 64
        manifest["model_version"] = "model-a"
        manifest["opm_image"] = "opm-a"
        (directory / "economics").mkdir(exist_ok=True)
        (directory / "economics" / "result.json").write_text(
            json.dumps({"economics_config_hash": "e" * 64, "methodology_version_hash": "m" * 64}),
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    right_manifest_path = right / "manifest.json"
    right_manifest = json.loads(right_manifest_path.read_text(encoding="utf-8"))
    right_manifest["constraints_hash"] = "x" * 64
    right_manifest_path.write_text(json.dumps(right_manifest), encoding="utf-8")

    card = run_tool("compare_runs", make(store, runs_root), {"a": "compare-a", "b": "compare-b"})

    assert card.payload["comparability"]["status"] == "incomparable"
    assert card.payload["comparability"]["mismatched_fields"] == ["constraints"]
    assert "причинный вклад" in card.payload["comparability"]["note"]


def test_compare_runs_never_subtracts_predicted_npv_from_verified_npv(
    store: ArtifactStore, runs_root: Path
) -> None:
    left = make_run(runs_root, "predicted-a")
    right = make_run(runs_root, "verified-b")
    manifest_path = left / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["verified_npv"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    card = run_tool(
        "compare_runs", make(store, runs_root), {"a": "predicted-a", "b": "verified-b"}
    )

    assert card.payload["a"]["npv_basis"] == "predicted"
    assert card.payload["b"]["npv_basis"] == "verified"
    assert card.payload["delta_npv"] is None
    assert "sources differ" in card.payload["delta_npv_reason"]
    assert "не вычислена" in card.payload["conclusion_markdown"]


def test_compare_runs_sums_recorded_annual_economic_line_items(
    store: ArtifactStore, runs_root: Path
) -> None:
    left = make_run(runs_root, "economics-a")
    right = make_run(runs_root, "economics-b")
    for directory, revenue, fcf in ((left, 100.0, 30.0), (right, 140.0, 50.0)):
        (directory / "economics").mkdir(exist_ok=True)
        (directory / "economics" / "npv-table.json").write_text(
            json.dumps({"by_year": {"2024": {"revenue": revenue, "fcf": fcf, "discounted_fcf": fcf}}}),
            encoding="utf-8",
        )

    card = run_tool("compare_runs", make(store, runs_root), {"a": "economics-a", "b": "economics-b"})

    breakdown = card.payload["economic_breakdown"]
    assert breakdown["recorded"] is True
    assert breakdown["deltas_b_minus_a"] == {"discounted_fcf": 20.0, "fcf": 20.0, "revenue": 40.0}


def test_compare_runs_compares_recorded_opm_oil_and_injection_by_well_and_step(
    store: ArtifactStore, runs_root: Path
) -> None:
    left = make_run(runs_root, "response-a")
    right = make_run(runs_root, "response-b")
    for directory, oil, injection, extra in ((left, 10.0, 4.0, False), (right, 15.0, 7.0, True)):
        manifest = json.loads((directory / "manifest.json").read_text())
        observation = directory / "observation" / manifest["schedule_hash"]
        observation.mkdir(parents=True)
        rows = [
            {"control_step": 3, "well": "W1", "oil_mass_delta": oil,
             "liquid_volume_delta": oil + 1, "injection_volume_delta": injection}
        ]
        if extra:
            rows.append({"control_step": 4, "well": "W2", "oil_mass_delta": 99,
                         "liquid_volume_delta": 100, "injection_volume_delta": 99})
        (observation / "response.json").write_text(json.dumps({"interval_response": rows}))

    card = run_tool("compare_runs", make(store, runs_root), {"a": "response-a", "b": "response-b"})

    assert card.action is not None
    assert card.action["run_id"] == "response-b"
    assert card.action["scenario"] == "base"
    comparison = card.payload["production_injection"]
    assert comparison["recorded"] is True
    assert comparison["matched_rows"] == 1
    assert comparison["unmatched_rows"] == 1
    assert comparison["totals_delta_b_minus_a"] == {
        "oil_mass_delta": 5.0,
        "injection_volume_delta": 3.0,
    }
    assert comparison["top_diff_wells_steps"][0]["well"] == "W1"
    assert comparison["top_diff_wells_steps"][0]["control_step"] == 3
    conclusion = card.payload["conclusion_markdown"]
    assert "Сравнительное инженерное заключение" in conclusion
    assert "Сопоставимость" in conclusion
    assert "арифметическим сравнением" in conclusion
    assert "/api/jarvis/run-artifacts/response-a/manifest" in conclusion
    assert "/api/jarvis/run-artifacts/response-b/opm-response" in conclusion


def test_opm_comparison_checks_deadline_during_large_response_scan(
    tmp_path: Path,
) -> None:
    def located(run_id: str) -> Located:
        root = tmp_path / run_id
        response = root / "observation" / "schedule" / "response.json"
        response.parent.mkdir(parents=True)
        response.write_text(
            json.dumps(
                {
                    "interval_response": [
                        {
                            "control_step": step,
                            "well": "W1",
                            "oil_mass_delta": float(step),
                            "injection_volume_delta": float(step + 1),
                        }
                        for step in range(300)
                    ]
                }
            )
        )
        return Located(run_id, root, {"schedule_hash": "schedule"}, 0.0)

    class Deadline:
        checks = 0

        def check_cancelled(self) -> None:
            self.checks += 1
            if self.checks == 2:
                raise TimeoutError("deadline reached")

    context = Deadline()
    with pytest.raises(TimeoutError, match="deadline reached"):
        _production_injection_breakdown(located("left"), located("right"), context)
    assert context.checks == 2


def test_compare_runs_builds_english_conclusion(store: ArtifactStore, runs_root: Path) -> None:
    make_run(runs_root, "english-a")
    make_run(runs_root, "english-b")

    card = run_tool(
        "compare_runs", make(store, runs_root, lang="en"), {"a": "english-a", "b": "english-b"}
    )

    assert "Comparative engineering conclusion" in card.payload["conclusion_markdown"]
    assert "do not establish a causal contribution" in card.payload["conclusion_markdown"]


def test_run_detail_builds_an_evidence_linked_rejection_conclusion(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root, "rejected-conclusion", sound=False)

    card = run_tool("run_detail", make(store, runs_root), {"run_id": "rejected-conclusion"})

    report = card.payload["conclusion_markdown"]
    assert "не рекомендован к применению" in report
    assert "Прогноз суррогата" in report
    assert "ЧДД после проверки OPM" in report
    assert f"/api/jarvis/run-artifacts/rejected-conclusion/manifest" in report
    assert "constraints_report" in report


@pytest.mark.parametrize("run_id", ["jarvis-policy-20260926", "candidate-018"])
def test_run_manifest_takes_precedence_over_registry(
    store: ArtifactStore, runs_root: Path, run_id: str
) -> None:
    make_run(runs_root, run_id, sound=False)

    card = run_tool("run_detail", make(store, runs_root), {"run_id": run_id})

    assert card.provenance == "runs"
    assert card.payload["sound"] is False
    assert "ограниченное заключение" not in card.payload["conclusion_markdown"].lower()
    assert "availability_note" not in card.payload


def test_registered_scenario_without_manifest_gets_limited_registry_conclusion(
    store: ArtifactStore, runs_root: Path
) -> None:
    card = run_tool("run_detail", make(store, runs_root), {"run_id": "candidate-018"})

    report = card.payload["conclusion_markdown"]
    assert card.provenance == "scenario-registry"
    assert "ограниченное заключение" in report.lower()
    assert "оригинальный run manifest отсутствует" in report.lower()
    assert "2763840887.814991 RUB" in report
    assert "допуск к применению не установлен" in report.lower()
    assert "artifacts/jarvis-scenario-registry.json" in report
    assert "причины генерации, полный manifest" in report.lower()


@pytest.mark.parametrize("sound", [True, False])
def test_run_detail_carries_the_same_recorded_acceptance_as_run_status(
    store: ArtifactStore, runs_root: Path, sound: bool
) -> None:
    make_run(runs_root, sound=sound)
    context = make(store, runs_root)
    detail = run_tool("run_detail", context, {"run_id": RUN_ID})
    status = run_tool("run_status", context, {"run_id": RUN_ID})
    assert detail.payload.get("acceptance") == status.payload["acceptance"]


def test_submission_summary_says_plainly_that_no_package_exists(
    store: ArtifactStore, runs_root: Path
) -> None:
    make_run(runs_root)

    card = run_tool("submission_summary", make(store, runs_root), {"run_id": RUN_ID})

    assert card.type == "submission"
    assert card.payload["assembled"] is False
    assert card.payload["code"] == NO_SUBMISSION
    assert card.payload["claimed_npv_rub"] is None
    assert card.payload["hashes"] is None
    assert "is not assembled" in card.payload["reason"]


def test_submission_summary_reports_the_numbers_of_the_package(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    document = write_submission(run_dir)

    card = run_tool("submission_summary", make(store, runs_root), {"run_id": RUN_ID})

    assert card.payload["assembled"] is True
    assert card.payload["claimed_npv_rub"] == document["claimed_npv_rub"] == CLAIMED_NPV
    for name in SUBMISSION_BUNDLE_FIELDS:
        if name == "claimed_npv_rub":
            continue
        assert card.payload["hashes"][name] == document[name]
    assert card.payload["status"] == "ready_to_submit"


def test_submission_summary_checks_the_package_against_the_manifest(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    write_submission(run_dir)

    card = run_tool("submission_summary", make(store, runs_root), {"run_id": RUN_ID})

    checks = card.payload["checks"]
    assert checks["status_ready_to_submit"] is True
    assert checks["schedule_include_present"] is True
    assert checks["source_run_matches"] is True
    assert checks["schedule_hash_matches"] is True
    assert checks["missing_fields"] == []


def test_submission_summary_refuses_a_package_without_a_number(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    write_submission(run_dir)
    path = run_dir / "submission" / "claimed_npv.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["claimed_npv_rub"] = None
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ToolFailure) as error:
        run_tool("submission_summary", make(store, runs_root), {"run_id": RUN_ID})

    assert "claimed_npv_rub" in str(error.value)


def test_the_scene_carries_the_claimed_number_through_the_guard(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    write_submission(run_dir)
    call = ToolCall(id="c", name="submission_summary", args={"run_id": RUN_ID})
    client = FakeChatClient(
        rounds=[[call]], caption="Заявленный ЧДД пакета — 11 873 676 460 руб."
    )
    orchestrator = Orchestrator(
        client=client,
        store=store,
        knowledge=Knowledge(),
        runs=RunStore(runs_root),
    )

    events = list(orchestrator.ask("s", "что с пакетом сдачи", ConsoleContext()))

    caption = [event for event in events if event.type == "caption"][0]
    assert "11 873 676 460" in caption.body["text"]
    assert not [event for event in events if event.type == "warning"]


def test_the_guard_still_cuts_an_invented_number_in_a_run_scene(
    store: ArtifactStore, runs_root: Path
) -> None:
    run_dir = make_run(runs_root)
    write_submission(run_dir)
    call = ToolCall(id="c", name="submission_summary", args={"run_id": RUN_ID})
    client = FakeChatClient(rounds=[[call]], caption="Запас составил 777 555 руб.")
    orchestrator = Orchestrator(
        client=client,
        store=store,
        knowledge=Knowledge(),
        runs=RunStore(runs_root),
    )

    events = list(orchestrator.ask("s", "что с пакетом сдачи", ConsoleContext()))

    caption = [event for event in events if event.type == "caption"][0]
    assert "777 555" not in caption.body["text"]


@pytest.mark.parametrize("retrieved", [False, True])
def test_manifest_numbers_require_a_retrieved_run_card(
    store: ArtifactStore, runs_root: Path, retrieved: bool,
) -> None:
    make_run(runs_root)
    call = (
        ToolCall(id="c", name="run_detail", args={"run_id": RUN_ID})
        if retrieved else ToolCall(id="c", name="field_metrics", args={"step": 96})
    )
    client = FakeChatClient(rounds=[[call]], caption="Прогноз прогона — 12 345 679 руб.")
    orchestrator = Orchestrator(
        client=client,
        store=store,
        knowledge=Knowledge(),
        runs=RunStore(runs_root),
    )

    events = list(orchestrator.ask("s", "что с последним расчётом", ConsoleContext()))

    caption = [event for event in events if event.type == "caption"][0]
    assert ("12 345 679" in caption.body["text"]) is retrieved
