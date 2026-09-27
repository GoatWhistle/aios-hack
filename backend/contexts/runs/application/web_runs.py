from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.contexts.constraints.application.cases import INFRASTRUCTURE_KEYS
from backend.contexts.assistant.infrastructure.artifacts import ArtifactStore
from backend.contexts.constraints.infrastructure.constraints_io import (
    constraints_from_json,
    constraints_to_json,
)
from backend.contexts.runs.application.run_projection import project_run, project_runs
from backend.contexts.runs.domain.errors import RunBusyError, RunRequestError
from backend.contexts.runs.infrastructure.job_store import JobStore
from backend.contexts.runs.application.case_request import draft_case_request
from backend.contexts.runs.infrastructure.worker_process import WORKER_CANCELLED, run_worker
from backend.contexts.constraints.domain.constraints import compensation_policy, water_supply_policy
from backend.contexts.constraints.infrastructure.constraints_io import constraints_hash
from backend.contexts.schedule.domain.alternative import set_producer_liquid_target
from backend.contexts.runs.application.workflow import RunWorkflow
from backend.shared.i18n.catalog import translate
from backend.shared.hashing import hash_schedule
from backend.shared.json_io import read_json

PARAMETERS = frozenset(INFRASTRUCTURE_KEYS)
MODES: tuple[str, ...] = ("search", "verify", "alternative")
BUDGETS: tuple[int, ...] = (10, 30, 120)
DEFAULT_MODE = "search"
DEFAULT_BUDGET = 30
RUN_ID_PREFIX = "web-"
RUN_ID_FORMAT = "web-%Y%m%d-%H%M%S-"
RUN_ID_SUFFIX_LENGTH = 8

UNKNOWN_MODE = "runs.request.unknown_mode"
UNKNOWN_BUDGET = "runs.request.unknown_budget"
UNSUPPORTED_PARAMETER = "runs.request.unsupported_parameter"
BUSY = "runs.status.busy"
BAD_RUN_ID = "runs.request.bad_run_id"
NO_PLAN_YET = "runs.request.no_plan_yet"
SEARCH_RUNNING = "runs.status.searching"
VERIFY_RUNNING = "runs.status.verifying"
SEARCH_FAILED = "runs.status.failed_infeasible"
VERIFY_FAILED = "runs.status.failed_verify"
SEARCH_DONE = "runs.status.completed_search"
VERIFY_DONE_SOUND = "runs.status.completed_verify_sound"
VERIFY_DONE_UNSOUND = "runs.status.completed_verify_unsound"
EXECUTION_FAILED = "runs.status.failed"
RUN_CANCELLED = "runs.status.cancelled"
_CANCEL_REQUESTED = "runs.status.cancel_requested"
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SOURCE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _message(key: str) -> dict[str, str]:
    return {"message": translate(key), "message_key": key}


def validated_mode(payload: Mapping[str, Any]) -> str:
    mode = payload.get("mode", DEFAULT_MODE)
    if mode not in MODES:
        raise RunRequestError(translate(UNKNOWN_MODE), message_key=UNKNOWN_MODE)
    return str(mode)


def validated_budget(payload: Mapping[str, Any]) -> int:
    budget = payload.get("budget", DEFAULT_BUDGET)
    if type(budget) is not int or budget not in BUDGETS:
        raise RunRequestError(translate(UNKNOWN_BUDGET), message_key=UNKNOWN_BUDGET)
    return budget


def validated_constraints(payload: Mapping[str, Any]):
    try:
        constraints = constraints_from_json(payload.get("constraints", {}))
    except ValueError as error:
        raise RunRequestError(str(error)) from error
    if set(constraints.infrastructure) - PARAMETERS:
        raise RunRequestError(translate(UNSUPPORTED_PARAMETER), message_key=UNSUPPORTED_PARAMETER)
    try:
        water_supply_policy(constraints)
        compensation_policy(constraints)
    except ValueError as error:
        raise RunRequestError(str(error)) from error
    return constraints


def validated_run_id(payload: Mapping[str, Any]) -> str:
    run_id = payload.get("run_id", "")
    if (
        not isinstance(run_id, str)
        or not run_id.startswith(RUN_ID_PREFIX)
        or Path(run_id).name != run_id
    ):
        raise RunRequestError(translate(BAD_RUN_ID), message_key=BAD_RUN_ID)
    return run_id


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime(RUN_ID_FORMAT)
    return stamp + uuid.uuid4().hex[:RUN_ID_SUFFIX_LENGTH]


class WebRuns:
    def __init__(self, root: Path):
        self.store = JobStore(root)
        self.lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._cancel_events: dict[str, threading.Event] = {}

    @property
    def root(self) -> Path:
        return self.store.root

    def recover_interrupted(self) -> None:
        self.store.recover_interrupted()

    def _write(self, directory: Path, data: Mapping[str, Any]) -> None:
        self.store.write(directory, data)

    def comparison(self, run_id: str) -> Mapping[str, Any] | None:
        directory = self.store.run_directory(run_id)
        if directory is None:
            return None
        return self.store.artifact(directory, "comparison.json")

    def draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        request = payload.get("request")
        if not isinstance(request, str) or not request.strip() or len(request) > 600:
            raise RunRequestError("request must contain 1 to 600 characters")
        constraints = payload.get("constraints")
        if not isinstance(constraints, Mapping):
            raise RunRequestError("constraints must be an object")
        scenario = payload.get("scenario", "base")
        if not isinstance(scenario, str) or not scenario:
            raise RunRequestError("scenario must be a non-empty identifier")
        try:
            index = ArtifactStore().scenario(scenario)
            return draft_case_request(
                request,
                base_constraints=constraints,
                dates=index.dates,
                available_wells=index.by_well,
            )
        except (ValueError, OSError) as error:
            raise RunRequestError(str(error)) from error

    def draft_alternative(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Preview a fixed producer target change against a saved run schedule."""
        source_run_id = payload.get("source_run_id")
        if (
            not isinstance(source_run_id, str)
            or _SOURCE_RUN_ID.fullmatch(source_run_id) is None
            or source_run_id in {".", ".."}
        ):
            raise RunRequestError("source_run_id must name one saved run")
        source_dir = self.store.run_directory(source_run_id)
        if source_dir is None:
            raise RunRequestError(f"source run {source_run_id!r} was not found")
        constraints_path = source_dir / "inputs" / "constraints.json"
        manifest_path = source_dir / "manifest.json"
        economics_path = source_dir / "economics" / "result.json"
        if (
            not constraints_path.is_file()
            or not manifest_path.is_file()
            or not economics_path.is_file()
        ):
            raise RunRequestError(
                "the source run must have a saved manifest, case constraints, "
                "and OPM economics"
            )
        try:
            manifest = read_json(manifest_path)
            economics = read_json(economics_path)
            constraints = constraints_from_json(read_json(constraints_path))
            if not isinstance(manifest, Mapping) or not isinstance(economics, Mapping):
                raise ValueError("the source run manifest or economics is invalid")
            if manifest.get("sound") is not True:
                raise ValueError(
                    "the source run must have passed OPM verification before an "
                    "alternative can be compared"
                )
            source_npv = economics.get("npv_methodology")
            if (
                isinstance(source_npv, bool)
                or not isinstance(source_npv, (int, float))
                or not (float("-inf") < float(source_npv) < float("inf"))
            ):
                raise ValueError("the source run has no finite verified OPM NPV")
            source_constraints_hash = constraints_hash(constraints)
            if manifest.get("constraints_hash") != source_constraints_hash:
                raise ValueError("the source run constraints do not match its manifest")
            schedule = RunWorkflow._read_schedule(source_dir)
            plan = set_producer_liquid_target(
                schedule,
                well=payload.get("well"),
                control_step=payload.get("control_step"),
                target_m3_per_day=payload.get("target_m3_per_day"),
            )
        except (OSError, TypeError, ValueError) as error:
            raise RunRequestError(str(error)) from error
        return {
            "source_run_id": source_run_id,
            "source_manifest_hash": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "source_economics_hash": hashlib.sha256(economics_path.read_bytes()).hexdigest(),
            "source_schedule_hash": hash_schedule(schedule),
            "alternative_schedule_hash": hash_schedule(plan.schedule),
            "constraints_hash": source_constraints_hash,
            "source_npv_rub": float(source_npv),
            "action": plan.action.as_dict(),
            # Reuse the verified source result; only the alternative needs OPM.
            "additional_opm_evaluations": 1,
        }

    def list(self) -> list[dict[str, Any]]:
        return project_runs(self.store)

    def by_request_id(self, request_id: str) -> dict[str, Any] | None:
        """Resolve a confirmed conversational proposal across page reloads."""
        if _REQUEST_ID.fullmatch(request_id) is None:
            raise RunRequestError("request_id is invalid")
        for path in self.store.job_paths(newest_first=True):
            directory = path.parent
            saved = self.store.read(directory)
            for key in ("case_request", "alternative_request"):
                request = saved.get(key)
                if isinstance(request, Mapping) and request.get("request_id") == request_id:
                    return project_run(self.store, directory, saved)
        return None

    def cancel(self, run_id: str) -> dict[str, Any]:
        validated_run_id({"run_id": run_id})
        directory = self.store.run_directory(run_id)
        if directory is None:
            raise RunRequestError(translate(BAD_RUN_ID), message_key=BAD_RUN_ID)
        with self._state_lock:
            data = self.store.read(directory)
            if data.get("status") != "running":
                raise RunRequestError("only a running job can be cancelled")
            event = self._cancel_events.get(run_id)
            if event is None:
                raise RunRequestError("the running job cannot be cancelled right now")
            event.set()
            data.update(cancel_requested=True, **_message(_CANCEL_REQUESTED))
            self._write(directory, data)
            return data

    def start(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        mode = validated_mode(payload)
        budget = validated_budget(payload)
        constraints = validated_constraints(payload) if mode == "search" else None
        alternative_request: dict[str, Any] | None = None
        if mode == "alternative":
            raw_request = payload.get("alternative_request")
            if not isinstance(raw_request, Mapping):
                raise RunRequestError("alternative_request must be an object")
            request_id = raw_request.get("request_id")
            if not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None:
                raise RunRequestError("alternative request_id is invalid")
            preview_input = {
                key: raw_request.get(key)
                for key in (
                    "source_run_id",
                    "well",
                    "control_step",
                    "target_m3_per_day",
                )
            }
            preview = self.draft_alternative(preview_input)
            for field in (
                "source_manifest_hash",
                "source_economics_hash",
                "source_schedule_hash",
                "alternative_schedule_hash",
                "constraints_hash",
            ):
                if raw_request.get(field) != preview[field]:
                    raise RunRequestError(
                        "the source run changed after preview; create a new preview"
                    )
            alternative_request = {
                "request_id": request_id,
                **preview_input,
                "source_manifest_hash": preview["source_manifest_hash"],
                "source_economics_hash": preview["source_economics_hash"],
                "source_schedule_hash": preview["source_schedule_hash"],
                "alternative_schedule_hash": preview["alternative_schedule_hash"],
                "constraints_hash": preview["constraints_hash"],
            }
            for path in self.store.job_paths():
                saved = self.store.read(path.parent)
                saved_request = saved.get("alternative_request")
                if (
                    isinstance(saved_request, Mapping)
                    and saved_request.get("request_id") == request_id
                ):
                    if dict(saved_request) != alternative_request:
                        raise RunRequestError("request_id was already used for another alternative")
                    return saved
            source_dir = self.store.run_directory(str(preview["source_run_id"]))
            if source_dir is None:
                raise RunRequestError("the source run disappeared after preview")
            constraints = constraints_from_json(
                read_json(source_dir / "inputs" / "constraints.json")
            )
        case_request = payload.get("case_request")
        if case_request is not None:
            if mode != "search" or not isinstance(case_request, Mapping):
                raise RunRequestError("case_request is only supported for a search run")
            request_id = case_request.get("request_id")
            request_text = case_request.get("request")
            scenario = case_request.get("scenario")
            if (
                not isinstance(request_id, str)
                or _REQUEST_ID.fullmatch(request_id) is None
                or not isinstance(request_text, str)
                or not request_text.strip()
                or len(request_text) > 600
                or not isinstance(scenario, str)
                or not scenario
                or len(scenario) > 64
            ):
                raise RunRequestError("case_request metadata is invalid")
            case_request = {
                "request_id": request_id,
                "request": request_text,
                "scenario": scenario,
            }
            base_constraints = payload["case_request"].get("base_constraints")
            if base_constraints is not None:
                if not isinstance(base_constraints, Mapping):
                    raise RunRequestError("base_constraints must be an object")
                preview = self.draft({
                    "request": request_text,
                    "scenario": scenario,
                    "constraints": base_constraints,
                })
                if constraints_hash(constraints) != constraints_hash(
                    constraints_from_json(preview["constraints"])
                ):
                    raise RunRequestError("the confirmed constraints differ from the reviewed case draft")
                case_request["base_constraints"] = dict(base_constraints)
            for path in self.store.job_paths():
                saved = self.store.read(path.parent)
                saved_case = saved.get("case_request")
                if isinstance(saved_case, Mapping) and saved_case.get("request_id") == request_id:
                    if dict(saved_case) != case_request:
                        raise RunRequestError("request_id was already used for another case")
                    saved_constraints = constraints_from_json(
                        read_json(path.parent / "constraints.json")
                    )
                    if constraints_hash(saved_constraints) != constraints_hash(constraints):
                        raise RunRequestError("request_id was already used with other constraints")
                    return saved
        if not self.lock.acquire(blocking=False):
            raise RunBusyError(translate(BUSY), message_key=BUSY)
        try:
            cancellation = threading.Event()
            if mode in {"search", "alternative"}:
                run_id = new_run_id()
                directory = self.root / run_id
                directory.mkdir(parents=True)
                write_json_document(
                    directory / "constraints.json", constraints_to_json(constraints)
                )
                data: dict[str, Any] = {
                    "run_id": run_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "budget": budget,
                }
                if case_request is not None:
                    data["case_request"] = dict(case_request)
                if alternative_request is not None:
                    data["alternative_request"] = alternative_request
            else:
                run_id = validated_run_id(payload)
                directory = self.root / run_id
                if (
                    not (directory / "manifest.json").is_file()
                    or not (directory / "constraints.json").is_file()
                ):
                    raise RunRequestError(translate(NO_PLAN_YET), message_key=NO_PLAN_YET)
                data = dict(self.store.read(directory))
            data.update(
                status="running",
                mode=mode,
                **_message(SEARCH_RUNNING if mode == "search" else VERIFY_RUNNING),
            )
            self._write(directory, data)
            with self._state_lock:
                self._cancel_events[run_id] = cancellation
            threading.Thread(
                target=self._execute,
                args=(directory, data, mode, budget, cancellation),
                daemon=True,
            ).start()
            return data
        except BaseException:
            if "run_id" in locals():
                with self._state_lock:
                    self._cancel_events.pop(run_id, None)
            self.lock.release()
            raise

    def _execute(
        self,
        directory: Path,
        data: dict[str, Any],
        mode: str,
        budget: int,
        cancellation: threading.Event | None = None,
    ) -> None:
        try:
            failed = run_worker(directory, mode, budget, cancel_event=cancellation)
            if cancellation is not None and cancellation.is_set() or failed == WORKER_CANCELLED:
                data.update(status="cancelled", **_message(RUN_CANCELLED))
            elif failed:
                data.update(
                    status="failed",
                    **_message(SEARCH_FAILED if mode == "search" else VERIFY_FAILED),
                )
            else:
                data.update(status="completed", **_message(self._done_message(directory, mode)))
        except Exception:
            data.update(status="failed", **_message(EXECUTION_FAILED))
        finally:
            try:
                with self._state_lock:
                    try:
                        if cancellation is not None and cancellation.is_set():
                            data.update(status="cancelled", **_message(RUN_CANCELLED))
                        self._write(directory, data)
                    finally:
                        self._cancel_events.pop(str(data.get("run_id", "")), None)
            finally:
                self.lock.release()

    def _done_message(self, directory: Path, mode: str) -> str:
        if mode == "search":
            return SEARCH_DONE
        manifest = read_json(directory / "manifest.json")
        return VERIFY_DONE_SOUND if manifest["sound"] else VERIFY_DONE_UNSOUND


def write_json_document(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )


__all__ = [
    "BUDGETS",
    "BUSY",
    "DEFAULT_BUDGET",
    "DEFAULT_MODE",
    "EXECUTION_FAILED",
    "MODES",
    "PARAMETERS",
    "RUN_ID_FORMAT",
    "RUN_ID_PREFIX",
    "SEARCH_DONE",
    "SEARCH_FAILED",
    "SEARCH_RUNNING",
    "UNKNOWN_BUDGET",
    "UNKNOWN_MODE",
    "UNSUPPORTED_PARAMETER",
    "VERIFY_DONE_SOUND",
    "VERIFY_DONE_UNSOUND",
    "VERIFY_FAILED",
    "VERIFY_RUNNING",
    "WebRuns",
    "new_run_id",
    "validated_budget",
    "validated_constraints",
    "validated_mode",
    "validated_run_id",
]
