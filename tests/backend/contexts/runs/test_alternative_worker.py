from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from backend.contexts.constraints.infrastructure.constraints_io import (
    constraints_from_json,
    constraints_hash,
    constraints_to_json,
)
from backend.contexts.runs.application.workflow import RunRequest, RunWorkflow
from backend.contexts.runs.application.workflow_models import RunProvenance
from backend.contexts.schedule.domain.alternative import set_producer_liquid_target
from backend.contexts.schedule.domain.canonical import canonicalize
from backend.contexts.schedule.domain.schedule import (
    Availability,
    ControlEvent,
    EventKind,
    OperatingStatus,
    Role,
    Schedule,
    ScheduleMeta,
    WellState,
)
from backend.shared.hashing import hash_schedule
from backend.interfaces.cli import web_run_worker


def _schedule() -> Schedule:
    return canonicalize(Schedule(
        meta=ScheduleMeta(n_control_dates=4, n_intervals=3, wells=("13",)),
        initial_state={
            "13": WellState(
                availability=Availability.AVAILABLE,
                role=Role.PROD,
                operating_status=OperatingStatus.OPEN,
                setpoint=100.0,
            )
        },
        fixed_deck_events=(),
        control_events=(ControlEvent(0, "13", EventKind.SET_LRAT, 100.0),),
    ))


@pytest.mark.parametrize(
    ("alternative_response_hash", "expected_status"),
    [("b" * 64, "comparable"), ("invalid-response-hash", "not-comparable")],
)
def test_alternative_worker_records_comparison_and_explicit_cost(
    tmp_path: Path, monkeypatch, alternative_response_hash: str, expected_status: str
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    source_id = "verified-source"
    constraints = constraints_from_json({})
    provenance = RunProvenance(
        constraints_hash=constraints_hash(constraints), opm_image="opm:test"
    )
    RunWorkflow(runs_root).search(
        RunRequest(source_id, _schedule(), None, provenance=provenance, constraints=constraints)
    )
    source = runs_root / source_id
    source_manifest = json.loads((source / "manifest.json").read_text())
    source_manifest.update(sound=True, verified_npv=100.0, status="verified")
    (source / "manifest.json").write_text(json.dumps(source_manifest))
    (source / "economics").mkdir(exist_ok=True)
    (source / "economics" / "result.json").write_text(json.dumps({
        "npv_methodology": 100.0,
        "source_response_hash": "a" * 64,
        "methodology_version_hash": "method-hash",
    }))

    plan = set_producer_liquid_target(
        _schedule(), well="13", control_step=1, target_m3_per_day=80.0
    )
    request = {
        "request_id": "alt-123",
        "source_run_id": source_id,
        "well": "13",
        "control_step": 1,
        "target_m3_per_day": 80.0,
        "source_manifest_hash": hashlib.sha256(
            (source / "manifest.json").read_bytes()
        ).hexdigest(),
        "source_economics_hash": hashlib.sha256(
            (source / "economics" / "result.json").read_bytes()
        ).hexdigest(),
        "source_schedule_hash": hash_schedule(_schedule()),
        "alternative_schedule_hash": hash_schedule(plan.schedule),
        "constraints_hash": constraints_hash(constraints),
    }
    candidate = runs_root / "web-alternative"
    candidate.mkdir()
    (candidate / "constraints.json").write_text(
        json.dumps(constraints_to_json(constraints))
    )
    (candidate / "job.json").write_text(json.dumps({
        "run_id": candidate.name,
        "alternative_request": request,
    }))

    class FakeWorkflow:
        _read_schedule = staticmethod(RunWorkflow._read_schedule)

        def __init__(self, _runs_root: Path) -> None:
            pass

        def verify(self, run_request, verify_fn):
            verify_fn(run_request.schedule, candidate / "opm")
            economics = candidate / "economics"
            economics.mkdir()
            (economics / "result.json").write_text(json.dumps({
                "npv_methodology": 120.0,
                "source_response_hash": alternative_response_hash,
                "methodology_version_hash": "method-hash",
            }))
            manifest = {
                "sound": True,
                "verified_npv": 120.0,
                "constraints_hash": constraints_hash(constraints),
                "opm_image": "opm:test",
            }
            (candidate / "manifest.json").write_text(json.dumps(manifest))
            return SimpleNamespace(
                sound=True,
                verified_npv=120.0,
                constraints_hash=constraints_hash(constraints),
                opm_image="opm:test",
                as_dict=lambda: manifest,
            )

    monkeypatch.setitem(sys.modules, "torch", None)
    fake_verification = ModuleType(
        "backend.contexts.optimization.application.verification_run"
    )
    fake_verification.verify_schedule = lambda *_args, **_kwargs: object()  # type: ignore[attr-defined]
    fake_verification.persist_observation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    fake_verification.compare_baseline_to_candidate = lambda *_args, **_kwargs: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "backend.contexts.optimization.application.verification_run",
        fake_verification,
    )
    monkeypatch.setattr(web_run_worker, "ensure_docker_ready", lambda: None)
    monkeypatch.setattr("backend.contexts.runs.application.workflow.RunWorkflow", FakeWorkflow)
    monkeypatch.setattr(
        sys,
        "argv",
        ["web_run_worker", "alternative", "--directory", str(candidate)],
    )

    assert web_run_worker.main() == 0
    comparison = json.loads((candidate / "comparison.json").read_text())
    assert comparison["comparison"]["status"] == expected_status
    assert comparison["comparison"]["npv_delta_rub"] == (20.0 if expected_status == "comparable" else None)
    assert (comparison["comparison"]["reason"] is None) == (expected_status == "comparable")
    assert comparison["comparison"]["causal_claim"] is False
    assert comparison["cost"]["additional_opm_evaluations"] == 1
    assert comparison["cost"]["baseline_opm_evaluation_reused"] is True
    assert comparison["conditions"]["satisfied"] is (expected_status == "comparable")
    assert comparison["conditions"]["checks"]["response_hash"]["both_valid_sha256"] is (expected_status == "comparable")
    if expected_status == "comparable":
        assert comparison["conditions"]["checks"]["response_hash"]["equal"] is False
    assert (candidate / "alternative.json").is_file()
