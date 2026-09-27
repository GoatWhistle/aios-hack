from __future__ import annotations
import argparse
import hashlib
import json
import os
import math
import re
import time
from pathlib import Path

from backend.contexts.simulation.infrastructure.preflight import (
    DockerPreflightError,
    ensure_docker_ready,
)
from backend.interfaces.cli.runner import run as run_cli


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _load_source_request(runs_root: Path, run_id: str):
    from backend.contexts.constraints.infrastructure.constraints_io import (
        constraints_from_json,
    )
    from backend.contexts.runs.application.workflow import RunRequest, RunWorkflow
    from backend.contexts.runs.application.workflow_models import (
        MANIFEST_PROVENANCE_FIELDS,
        RunProvenance,
    )
    from backend.contexts.reservoir.domain.horizon import HORIZON, load_horizon
    from backend.shared.json_io import read_json

    if _RUN_ID.fullmatch(run_id) is None or run_id in {".", ".."}:
        raise SystemExit("the source run ID is invalid")
    run_dir = (runs_root / run_id).resolve()
    if run_dir.parent != runs_root.resolve():
        raise SystemExit("the source run path is outside the configured run store")
    horizon_path = run_dir / "inputs" / "horizon.json"
    if horizon_path.is_file() and load_horizon(str(horizon_path)) != HORIZON:
        raise SystemExit(f"the source run {run_id} uses a different process horizon")
    request_path = run_dir / "inputs" / "request.json"
    if not request_path.is_file():
        raise SystemExit(f"the source run request is missing: {request_path}")
    request_data = read_json(request_path)
    if not isinstance(request_data, dict):
        raise SystemExit("the source run request is invalid")
    constraints_path = run_dir / "inputs" / "constraints.json"
    constraints = (
        constraints_from_json(read_json(constraints_path))
        if constraints_path.is_file()
        else None
    )
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    if not isinstance(manifest, dict):
        raise SystemExit("the source run manifest is invalid")
    provenance = RunProvenance(
        **{name: manifest.get(name) for name in MANIFEST_PROVENANCE_FIELDS}
    )
    return RunRequest(
        run_id=run_id,
        schedule=RunWorkflow._read_schedule(run_dir),
        predicted_npv=request_data.get("predicted_npv"),
        constraints=constraints,
        provenance=provenance,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['search', 'verify', 'alternative'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=30)
    args = parser.parse_args()
    root = args.directory.resolve()
    os.environ['AIOS_CONSTRAINTS_PATH'] = str(root / 'constraints.json')
    os.environ['AIOS_SEARCH_DIAGNOSTICS_PATH'] = str(root / 'diagnostics.json')
    if args.mode == 'search':
        import torch
        torch.set_num_threads(2)
    from backend.contexts.runs.application.workflow import RunRequest, RunWorkflow
    workflow = RunWorkflow(root.parent)
    if args.mode == 'search':
        from backend.contexts.optimization.application.search_use_case import run_search
        from backend.interfaces.cli.run import build_provenance, resolve_constraints

        def report_search_progress(stage: str, step: int, total: int) -> None:
            path = root / 'search-progress.json'
            temporary = root / 'search-progress.tmp'
            temporary.write_text(json.dumps({
                'stage': stage, 'step': step, 'total': total,
            }), encoding='utf-8')
            temporary.replace(path)

        outcome = run_search(budget=args.budget, progress_callback=report_search_progress)
        constraints = resolve_constraints(root / 'constraints.json')
        manifest = workflow.search(
            RunRequest(
                root.name,
                outcome.schedule,
                outcome.predicted_npv,
                provenance=build_provenance(outcome, constraints),
                constraints=constraints,
            )
        )
        (root / 'provenance.json').write_text(json.dumps(outcome.provenance, ensure_ascii=False, indent=2))
    elif args.mode == 'verify':
        try:
            ensure_docker_ready()
        except DockerPreflightError as error:
            raise SystemExit(error.report.message) from error
        from backend.contexts.optimization.application.verification_run import (
            verify_schedule,
            persist_observation,
        )
        request = _load_source_request(root.parent, root.name)

        def verify_and_record(schedule, work_root):
            result = verify_schedule(schedule, work_root)
            persist_observation(schedule, result, predicted_npv=request.predicted_npv,
                                observation_root=root / 'observation',
                                metadata={'constraints_path': str(root / 'constraints.json')})
            return result
        manifest = workflow.verify(request, verify_and_record)
    else:
        try:
            ensure_docker_ready()
        except DockerPreflightError as error:
            raise SystemExit(error.report.message) from error
        from backend.contexts.optimization.application.verification_run import (
            persist_observation,
            verify_schedule,
        )
        from backend.contexts.schedule.domain.alternative import (
            set_producer_liquid_target,
        )
        from backend.contexts.constraints.infrastructure.constraints_io import (
            constraints_hash,
        )
        from backend.shared.hashing import hash_schedule
        from backend.shared.json_io import read_json
        job = read_json(root / 'job.json')
        alternative = job.get('alternative_request')
        if not isinstance(alternative, dict):
            raise SystemExit('the fixed-action request is missing from job.json')
        source_run_id = str(alternative['source_run_id'])
        source_dir = root.parent / source_run_id
        source = _load_source_request(root.parent, source_run_id)
        if source.constraints is None:
            raise SystemExit('the source run has no saved case constraints')
        source_manifest_bytes = (source_dir / 'manifest.json').read_bytes()
        source_economics_bytes = (source_dir / 'economics' / 'result.json').read_bytes()
        if (
            hashlib.sha256(source_manifest_bytes).hexdigest()
            != alternative['source_manifest_hash']
            or hashlib.sha256(source_economics_bytes).hexdigest()
            != alternative['source_economics_hash']
        ):
            raise SystemExit('the source verification result changed after confirmation')
        source_manifest = json.loads(source_manifest_bytes)
        source_economics = json.loads(source_economics_bytes)
        (root / 'baseline-manifest.json').write_bytes(source_manifest_bytes)
        (root / 'baseline-economics.json').write_bytes(source_economics_bytes)
        plan = set_producer_liquid_target(
            source.schedule,
            well=alternative['well'],
            control_step=alternative['control_step'],
            target_m3_per_day=alternative['target_m3_per_day'],
        )
        if (
            hash_schedule(source.schedule) != alternative['source_schedule_hash']
            or hash_schedule(plan.schedule) != alternative['alternative_schedule_hash']
            or constraints_hash(source.constraints) != alternative['constraints_hash']
        ):
            raise SystemExit('the source run changed after alternative confirmation')

        evaluation_seconds = [0.0]

        def verify_and_record(schedule, work_root):
            started = time.monotonic()
            result = verify_schedule(
                schedule, work_root, constraints=source.constraints
            )
            evaluation_seconds[0] = time.monotonic() - started
            persist_observation(
                schedule,
                result,
                predicted_npv=None,
                observation_root=root / 'observation',
                metadata={
                    'kind': 'fixed-action-alternative',
                    'source_run_id': source_run_id,
                    'action': plan.action.as_dict(),
                },
            )
            return result

        manifest = workflow.verify(
            RunRequest(
                run_id=root.name,
                schedule=plan.schedule,
                predicted_npv=None,
                constraints=source.constraints,
                provenance=source.provenance,
            ),
            verify_and_record,
        )
        candidate_economics = read_json(root / 'economics' / 'result.json')
        conditions = {
            'constraints_hash': {
                'source': source_manifest.get('constraints_hash'),
                'alternative': manifest.constraints_hash,
            },
            'opm_image': {
                'source': source_manifest.get('opm_image'),
                'alternative': manifest.opm_image,
            },
            'response_hash': {
                'source': source_economics.get('source_response_hash'),
                'alternative': candidate_economics.get('source_response_hash'),
                'both_valid_sha256': all(
                    isinstance(value, str)
                    and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                    for value in (
                        source_economics.get('source_response_hash'),
                        candidate_economics.get('source_response_hash'),
                    )
                ),
                'equal': source_economics.get('source_response_hash')
                == candidate_economics.get('source_response_hash'),
            },
            'methodology_version_hash': {
                'source': source_economics.get('methodology_version_hash'),
                'alternative': candidate_economics.get('methodology_version_hash'),
            },
        }
        equality_checks_match = all(
            conditions[name]['source'] is not None
            and conditions[name]['source'] == conditions[name]['alternative']
            for name in ('constraints_hash', 'opm_image', 'methodology_version_hash')
        )
        conditions_satisfied = (
            equality_checks_match
            and conditions['response_hash']['both_valid_sha256']
        )
        source_npv = source_manifest.get('verified_npv')
        alternative_npv = manifest.verified_npv
        comparable = (
            conditions_satisfied
            and source_manifest.get('sound') is True
            and manifest.sound is True
            and isinstance(source_npv, (int, float))
            and not isinstance(source_npv, bool)
            and isinstance(alternative_npv, (int, float))
            and not isinstance(alternative_npv, bool)
            and math.isfinite(float(source_npv))
            and math.isfinite(float(alternative_npv))
        )
        comparison = {
            'schema_version': '1.0',
            'kind': 'fixed-action-alternative',
            'run_id': root.name,
            'source_run_id': source_run_id,
            'action': plan.action.as_dict(),
            'conditions': {'satisfied': conditions_satisfied, 'checks': conditions},
            'baseline': {
                'run_id': source_run_id,
                'schedule_hash': hash_schedule(source.schedule),
                'sound': source_manifest.get('sound'),
                'verified_npv_rub': source_npv,
                'reused_recorded_result': True,
            },
            'alternative': {
                'run_id': root.name,
                'schedule_hash': hash_schedule(plan.schedule),
                'sound': manifest.sound,
                'verified_npv_rub': alternative_npv,
                'reused_recorded_result': False,
            },
            'comparison': {
                'status': 'comparable' if comparable else 'not-comparable',
                'npv_delta_rub': float(alternative_npv) - float(source_npv)
                if comparable
                else None,
                'reason': None
                if comparable
                else 'both runs must pass OPM verification with matching case, OPM image, and methodology plus valid response hashes; response contents may differ',
                'causal_claim': False,
            },
            'cost': {
                'additional_opm_evaluations': 1,
                'baseline_opm_evaluation_reused': True,
                'alternative_wallclock_seconds': evaluation_seconds[0],
                'baseline_wallclock_seconds': None,
            },
        }
        (root / 'alternative.json').write_text(
            json.dumps(plan.action.as_dict(), ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        (root / 'comparison.json').write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8',
        )
    print(json.dumps(manifest.as_dict(), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
